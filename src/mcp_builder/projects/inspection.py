"""Static project mapping for existing FastMCP code, without imports or execution."""

import ast
import re
import tomllib
from pathlib import PurePosixPath

from .schemas import ComponentInspection, InspectionResult
from .validation import validate_project


def _component_name(node, decorator, kind: str) -> str:
    """Return a statically declared component name, falling back to the function name."""
    name = node.name
    if not isinstance(decorator, ast.Call):
        return name
    key = "uri" if kind == "resource" else "name"
    literal = next((item.value for item in decorator.keywords if item.arg == key), None)
    if literal is None and decorator.args:
        literal = decorator.args[0]
    if isinstance(literal, ast.Constant) and isinstance(literal.value, str):
        return literal.value
    return name


def inspect_project(files: list[dict]) -> InspectionResult:
    """Map components, models, dependencies and tests through bounded static parsing."""
    validation = validate_project(files)
    if any(item["code"] == "invalid_path" for item in validation["diagnostics"]):
        raise ValueError("Le projet contient un chemin invalide ou dupliqué")
    file_map = {item["path"]: item["content"] for item in files}
    exports: dict[str, set[str]] = {}
    trees: dict[str, ast.AST] = {}
    dependencies: list[str] = []
    declared_fastmcp_version = None
    pydantic_models: list[dict] = []
    components: list[ComponentInspection] = []

    pyproject = file_map.get("pyproject.toml")
    if pyproject:
        try:
            project = tomllib.loads(pyproject).get("project", {})
            dependencies = sorted(project.get("dependencies", []))
            dependency = next((item for item in dependencies
                               if re.match(r"fastmcp(?:\W|$)", item, re.IGNORECASE)), None)
            if dependency:
                match = re.search(r"(?:==|>=|~=|<=|>|<)\s*([^,; ]+)", dependency)
                declared_fastmcp_version = match.group(1) if match else "unbounded"
        except tomllib.TOMLDecodeError:
            pass

    for path, content in file_map.items():
        if not path.endswith(".py"):
            continue
        try:
            tree = ast.parse(content)
        except (SyntaxError, ValueError, RecursionError):
            continue
        trees[path] = tree
        if path.endswith("/__init__.py"):
            package = path.rsplit("/", 1)[0]
            exports[package] = set()
            for statement in tree.body:
                if isinstance(statement, ast.ImportFrom) and statement.level == 1:
                    if statement.module:
                        exports[package].add(statement.module.split(".", 1)[0])
                    else:
                        exports[package].update(alias.name for alias in statement.names)
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and any(
                (isinstance(base, ast.Name) and base.id == "BaseModel")
                or (isinstance(base, ast.Attribute) and base.attr == "BaseModel")
                for base in node.bases
            ):
                fields = [child.target.id for child in node.body
                          if isinstance(child, ast.AnnAssign)
                          and isinstance(child.target, ast.Name)]
                pydantic_models.append({"name": node.name, "path": path,
                                        "line": node.lineno, "fields": fields})

    for path, tree in trees.items():
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                target = decorator.func if isinstance(decorator, ast.Call) else decorator
                if not isinstance(target, ast.Attribute) or target.attr not in {
                    "tool", "resource", "prompt"
                }:
                    continue
                kind = target.attr
                package = f"app/{kind}s"
                module = PurePosixPath(path).stem
                test_path = f"tests/test_{module}.py"
                components.append(ComponentInspection(
                    kind=kind,
                    name=_component_name(node, decorator, kind),
                    function=node.name,
                    path=path,
                    line=node.lineno,
                    is_async=isinstance(node, ast.AsyncFunctionDef),
                    parameters=[argument.arg for argument in (
                        *node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs
                    ) if argument.arg not in {"self", "cls"}],
                    return_annotation=(ast.unparse(node.returns) if node.returns else None),
                    exported=module in exports.get(package, set()),
                    targeted_test=test_path in file_map,
                ))

    counts = {kind: sum(item.kind == kind for item in components)
              for kind in ("tool", "resource", "prompt")}
    return InspectionResult(
        components=sorted(components, key=lambda item: (item.kind, item.path, item.line)),
        pydantic_models=sorted(pydantic_models, key=lambda item: (item["path"], item["line"])),
        dependencies=dependencies,
        declared_fastmcp_version=declared_fastmcp_version,
        architecture={"component_counts": counts, "python_files": len(trees),
                      "test_files": sum(path.startswith("tests/") and path.endswith(".py")
                                        for path in file_map)},
        validation=validation,
    )
