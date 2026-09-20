"""Static project mapping for existing FastMCP code, without imports or execution."""

import ast
import re
import tomllib
from pathlib import PurePosixPath

from .schemas import ComponentInspection, InspectionResult
from .validation import ValidationProfile, _has_targeted_test, validate_project


def _normalized_annotation(node: ast.AST | None) -> str | None:
    """Return the business type beneath Annotated/Optional syntax."""
    if node is None:
        return None
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        left = _normalized_annotation(node.left)
        right = _normalized_annotation(node.right)
        if left == "None":
            return right
        if right == "None":
            return left
    if isinstance(node, ast.Subscript):
        target = ast.unparse(node.value)
        if target in {"Annotated", "typing.Annotated"}:
            value = node.slice.elts[0] if isinstance(node.slice, ast.Tuple) else node.slice
            return _normalized_annotation(value)
        if target in {"Optional", "typing.Optional"}:
            return _normalized_annotation(node.slice)
    return ast.unparse(node)


def _parameter_contracts(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[dict]:
    """Extract ordered parameter type and requiredness without importing code."""
    positional = [*node.args.posonlyargs, *node.args.args]
    first_default = len(positional) - len(node.args.defaults)
    contracts = [
        {
            "name": argument.arg,
            "annotation": _normalized_annotation(argument.annotation),
            "required": index < first_default,
        }
        for index, argument in enumerate(positional)
        if argument.arg not in {"self", "cls"}
    ]
    contracts.extend(
        {
            "name": argument.arg,
            "annotation": _normalized_annotation(argument.annotation),
            "required": node.args.kw_defaults[index] is None,
        }
        for index, argument in enumerate(node.args.kwonlyargs)
        if argument.arg not in {"self", "cls"}
    )
    return contracts


def _tool_annotations(decorator: ast.AST, kind: str) -> dict[str, bool]:
    """Read literal FastMCP tool hints while ignoring dynamic expressions."""
    if kind != "tool" or not isinstance(decorator, ast.Call):
        return {}
    value = next(
        (item.value for item in decorator.keywords if item.arg == "annotations"),
        None,
    )
    if value is None:
        return {}
    try:
        parsed = ast.literal_eval(value)
    except (ValueError, TypeError, SyntaxError):
        return {}
    if not isinstance(parsed, dict):
        return {}
    return {
        key: item
        for key, item in parsed.items()
        if isinstance(key, str) and isinstance(item, bool)
    }


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


def inspect_project(
    files: list[dict], profile: ValidationProfile = "recommended"
) -> InspectionResult:
    """Map components, models, dependencies and tests through bounded static parsing."""
    validation = validate_project(files, profile=profile)
    if any(item["code"] == "invalid_path" for item in validation["diagnostics"]):
        raise ValueError("The project contains an invalid or duplicate path")
    file_map = {item["path"]: item["content"] for item in files}
    exports: dict[str, set[str]] = {}
    trees: dict[str, ast.AST] = {}
    dependencies: list[str] = []
    declared_fastmcp_version = None
    pydantic_models: list[dict] = []
    enums: list[dict] = []
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
                field_contracts = [
                    {
                        "name": child.target.id,
                        "annotation": _normalized_annotation(child.annotation),
                        "required": child.value is None,
                    }
                    for child in node.body
                    if isinstance(child, ast.AnnAssign)
                    and isinstance(child.target, ast.Name)
                ]
                pydantic_models.append({"name": node.name, "path": path,
                                        "line": node.lineno,
                                        "fields": [item["name"] for item in field_contracts],
                                        "field_contracts": field_contracts})
            if isinstance(node, ast.ClassDef) and any(
                (isinstance(base, ast.Name) and base.id == "Enum")
                or (isinstance(base, ast.Attribute) and base.attr == "Enum")
                for base in node.bases
            ):
                values = []
                for child in node.body:
                    if not isinstance(child, ast.Assign) or len(child.targets) != 1:
                        continue
                    if not isinstance(child.targets[0], ast.Name):
                        continue
                    try:
                        value = ast.literal_eval(child.value)
                    except (ValueError, TypeError, SyntaxError):
                        continue
                    if isinstance(value, str):
                        values.append(value)
                enums.append({
                    "name": node.name,
                    "path": path,
                    "line": node.lineno,
                    "values": values,
                })

    test_trees = {path: tree for path, tree in trees.items() if path.startswith("tests/")}
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
                name = _component_name(node, decorator, kind)
                parameter_contracts = _parameter_contracts(node)
                components.append(ComponentInspection(
                    kind=kind,
                    name=name,
                    function=node.name,
                    path=path,
                    line=node.lineno,
                    is_async=isinstance(node, ast.AsyncFunctionDef),
                    parameters=[item["name"] for item in parameter_contracts],
                    parameter_types=[item["annotation"] for item in parameter_contracts],
                    required_parameters=[
                        item["name"] for item in parameter_contracts if item["required"]
                    ],
                    return_annotation=_normalized_annotation(node.returns),
                    exported=module in exports.get(package, set()),
                    targeted_test=_has_targeted_test(
                        test_trees,
                        kind=kind,
                        name=name,
                        function=node.name,
                        module=module,
                    ),
                    tool_annotations=_tool_annotations(decorator, kind),
                ))

    counts = {kind: sum(item.kind == kind for item in components)
              for kind in ("tool", "resource", "prompt")}
    return InspectionResult(
        components=sorted(components, key=lambda item: (item.kind, item.path, item.line)),
        pydantic_models=sorted(pydantic_models, key=lambda item: (item["path"], item["line"])),
        enums=sorted(enums, key=lambda item: (item["path"], item["line"])),
        dependencies=dependencies,
        declared_fastmcp_version=declared_fastmcp_version,
        architecture={"component_counts": counts, "python_files": len(trees),
                      "test_files": sum(path.startswith("tests/") and path.endswith(".py")
                                        for path in file_map)},
        validation=validation,
    )
