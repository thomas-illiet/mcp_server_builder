"""Static Python/TOML diagnostics without importing submitted code."""
import ast
import tomllib
from pathlib import PurePosixPath

from mcp_builder import BUILDER_VERSION, FASTMCP_VERSION, SCHEMA_VERSION

REFERENCE = "https://gofastmcp.com/servers/tools"
DIAGNOSTIC_HELP = {
    "invalid_path": ("Use a unique relative POSIX path without '..'.", REFERENCE),
    "toml_syntax": ("Fix the TOML document identified by the parser.",
                    "https://packaging.python.org/en/latest/guides/writing-pyproject-toml/"),
    "python_syntax": ("Fix the Python syntax before any other validation.",
                      "https://docs.python.org/3/reference/"),
    "todo_skeleton": ("Implement the business logic and update the focused test.", REFERENCE),
    "legacy_import": ("Replace this import with `from fastmcp import FastMCP`.", REFERENCE),
    "unverified_import": ("Verify this import in the targeted FastMCP documentation.", REFERENCE),
    "duplicate_component": ("Rename or remove one of the declarations.", REFERENCE),
    "missing_description": ("Add a docstring or `description=` to the decorator.", REFERENCE),
    "missing_annotation": ("Add a Python annotation or a bounded Pydantic model.", REFERENCE),
    "missing_return_type": ("Declare a serializable return type.", REFERENCE),
    "multiple_tools_in_file": ("Move each tool into its own module.", REFERENCE),
    "tool_file_layout": ("Move the tool to the indicated path and update imports.",
                         REFERENCE),
    "component_file_layout": ("Move the component to its dedicated package.", REFERENCE),
    "component_not_exported": ("Add an explicit relative import to __init__.py.", REFERENCE),
    "secret_argument": ("Provide secrets through server-side configuration, never through MCP.",
                        "https://gofastmcp.com/servers/tools"),
    "blocking_call_in_async": ("Use an asynchronous client or move the blocking work.",
                               "https://gofastmcp.com/servers/tools"),
    "dangerous_process_call": ("Avoid external processes or use a fixed argument list "
                               "without a shell.", REFERENCE),
    "network_without_timeout": ("Set an explicit bounded timeout for every network call.",
                                REFERENCE),
}


def _call_name(call: ast.Call) -> str:
    """Return a dotted static call name when it can be determined safely."""
    parts: list[str] = []
    node = call.func
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def validate_project(files: list[dict]) -> dict:
    """Inspect at most 100 supplied files (1 MB combined) using AST and TOML parsers.

    Return valid, diagnostics with file/line/severity, executed=False and
    limitations. Syntax/path errors invalidate the project; incomplete type
    annotations or duplicate MCP declarations produce warnings. Oversized input
    raises ValueError. No imports, dependency resolution or submitted code run.
    """
    if not 1 <= len(files) <= 100:
        raise ValueError("Between 1 and 100 files are required")
    if sum(len(f.get("content", "").encode()) for f in files) > 1_000_000:
        raise ValueError("Project size is limited to 1 MB")
    diagnostics, seen_paths, components = [], set(), {}
    modules_by_package: dict[str, set[str]] = {}
    declared_by_file: dict[str, list[tuple[str, str, int]]] = {}

    def report(path, line, code, message, severity="warning"):
        """Append one located diagnostic without retaining files outside this request."""
        suggestion, documentation = DIAGNOSTIC_HELP.get(
            code, ("Review and fix this diagnostic.", REFERENCE)
        )
        diagnostics.append({"path": path, "line": line, "code": code,
                            "message": message, "severity": severity,
                            "suggestion": suggestion, "documentation": documentation})

    for item in files:
        path, content = item["path"], item["content"]
        parts = PurePosixPath(path).parts
        if (not path or "\\" in path or ":" in path or path.startswith("/")
                or ".." in parts or path in seen_paths):
            report(path, 1, "invalid_path", "Invalid or duplicate relative path", "error")
            continue
        seen_paths.add(path)
        if path.endswith(".toml"):
            try:
                tomllib.loads(content)
            except tomllib.TOMLDecodeError as exc:
                report(path, getattr(exc, "lineno", 1), "toml_syntax", str(exc), "error")
        if not path.endswith(".py"):
            continue
        try:
            tree = ast.parse(content)
        except (SyntaxError, ValueError, RecursionError) as exc:
            report(path, getattr(exc, "lineno", 1), "python_syntax", str(exc), "error")
            continue
        if "TODO" in content:
            report(path, 1, "todo_skeleton", "Replace the TODO skeleton before use")
        if path.endswith("/__init__.py"):
            imported = modules_by_package.setdefault(path.rsplit("/", 1)[0], set())
            for statement in tree.body:
                if isinstance(statement, ast.ImportFrom) and statement.level == 1:
                    if statement.module:
                        imported.add(statement.module.split(".", 1)[0])
                    else:
                        imported.update(alias.name for alias in statement.names)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module == "mcp.server.fastmcp":
                    report(path, node.lineno, "legacy_import", "Use from fastmcp import FastMCP")
                if node.module == "fastmcp":
                    for alias in node.names:
                        if alias.name not in {"FastMCP", "Client", "Context"}:
                            report(path, node.lineno, "unverified_import",
                                   f"Import {alias.name} is not verified by this validator")
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                target = decorator.func if isinstance(decorator, ast.Call) else decorator
                if not isinstance(target, ast.Attribute) or target.attr not in {"tool", "resource", "prompt"}:
                    continue
                name = node.name
                if isinstance(decorator, ast.Call):
                    key = "uri" if target.attr == "resource" else "name"
                    literal = next((kw.value for kw in decorator.keywords if kw.arg == key), None)
                    if literal is None and decorator.args:
                        literal = decorator.args[0]
                    if isinstance(literal, ast.Constant) and isinstance(literal.value, str):
                        name = literal.value
                identity = (target.attr, name)
                declared_by_file.setdefault(path, []).append((target.attr, node.name, node.lineno))
                if identity in components:
                    report(path, node.lineno, "duplicate_component",
                           f"{target.attr} {name} is already declared in {components[identity]}")
                components[identity] = path
                has_description = isinstance(decorator, ast.Call) and any(
                    kw.arg == "description" for kw in decorator.keywords
                )
                if not ast.get_docstring(node) and not has_description:
                    report(path, node.lineno, "missing_description", "Add a description")
                args = [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
                for arg in args:
                    if arg.annotation is None and arg.arg not in {"self", "cls"}:
                        report(path, node.lineno, "missing_annotation", f"Add a type to parameter {arg.arg}")
                    if any(token in arg.arg.lower() for token in (
                        "secret", "password", "passwd", "api_key", "token"
                    )):
                        report(path, node.lineno, "secret_argument",
                               f"Parameter {arg.arg} appears to carry a secret")
                if node.returns is None:
                    report(path, node.lineno, "missing_return_type", "Add a return type")
                for call in (child for child in ast.walk(node) if isinstance(child, ast.Call)):
                    call_name = _call_name(call)
                    if call_name in {"os.system", "subprocess.call", "subprocess.run",
                                     "subprocess.Popen"}:
                        report(path, call.lineno, "dangerous_process_call",
                               f"Sensitive process call detected: {call_name}")
                    if isinstance(node, ast.AsyncFunctionDef) and (
                        call_name == "time.sleep" or call_name.startswith("requests.")
                    ):
                        report(path, call.lineno, "blocking_call_in_async",
                               f"Blocking call in an async function: {call_name}")
                    if (call_name.startswith(("requests.", "httpx."))
                            and not any(keyword.arg == "timeout" for keyword in call.keywords)):
                        report(path, call.lineno, "network_without_timeout",
                               f"Network call without an explicit timeout: {call_name}")
    for path, declarations in declared_by_file.items():
        public_tools = [item for item in declarations if item[0] == "tool"]
        if len(public_tools) > 1:
            report(path, public_tools[1][2], "multiple_tools_in_file",
                   "Only one public tool is allowed per file", "error")
        for kind, name, line in declarations:
            package = f"app/{kind}s"
            module = PurePosixPath(path).stem
            if (PurePosixPath(path).parent.as_posix() != package or module != name):
                code = "tool_file_layout" if kind == "tool" else "component_file_layout"
                report(path, line, code,
                       f"The {kind} {name} must be in {package}/{name}.py", "error")
            if PurePosixPath(path).parent.as_posix() == package:
                if module not in modules_by_package.get(package, set()):
                    report(path, line, "component_not_exported",
                           f"Import {module} explicitly from {package}/__init__.py",
                           "error")
    return {"schema_version": SCHEMA_VERSION, "generator_version": BUILDER_VERSION,
            "fastmcp_version": FASTMCP_VERSION,
            "valid": not any(d["severity"] == "error" for d in diagnostics),
            "diagnostics": diagnostics, "executed": False,
            "limitations": "Static analysis only: no dynamic resolution, imports, installed "
                           "dependency checks, or functional guarantees. Duplicate declarations "
                           "are reported without resolving server instances."}


def review_project_security(files: list[dict]) -> dict:
    """Return focused high-confidence security diagnostics from the static validator."""
    result = validate_project(files)
    security_codes = {"secret_argument", "blocking_call_in_async", "dangerous_process_call",
                      "network_without_timeout", "invalid_path"}
    diagnostics = [item for item in result["diagnostics"] if item["code"] in security_codes]
    return {"schema_version": SCHEMA_VERSION, "generator_version": BUILDER_VERSION,
            "fastmcp_version": FASTMCP_VERSION,
            "passed": not diagnostics, "diagnostics": diagnostics, "executed": False,
            "limitations": "Focused AST analysis only: data flows, dependencies, dynamic imports, "
                           "and runtime behavior are not evaluated."}
