"""Static Python/TOML diagnostics without importing submitted code."""

import ast
import re
import tomllib
from pathlib import PurePosixPath
from typing import Literal

from mcp_builder import BUILDER_VERSION, FASTMCP_VERSION, SCHEMA_VERSION

ValidationProfile = Literal["framework", "recommended", "strict"]

REFERENCE = "https://gofastmcp.com/servers/tools"
DIAGNOSTIC_HELP = {
    "invalid_path": ("Use a unique relative POSIX path without '..'.", REFERENCE),
    "toml_syntax": (
        "Fix the TOML document identified by the parser.",
        "https://packaging.python.org/en/latest/guides/writing-pyproject-toml/",
    ),
    "python_syntax": (
        "Fix the Python syntax before any other validation.",
        "https://docs.python.org/3/reference/",
    ),
    "todo_skeleton": ("Implement the business logic and focused assertions.", REFERENCE),
    "incomplete_component": (
        "Replace pass, Ellipsis, or NotImplementedError with business logic.",
        REFERENCE,
    ),
    "missing_targeted_test": (
        "Add a test that invokes this component and asserts its business result.",
        "https://gofastmcp.com/servers/testing",
    ),
    "legacy_import": ("Replace this import with `from fastmcp import FastMCP`.", REFERENCE),
    "unverified_import": ("Verify this import in the targeted FastMCP documentation.", REFERENCE),
    "duplicate_component": ("Rename or remove one of the declarations.", REFERENCE),
    "missing_description": ("Add a docstring or `description=` to the decorator.", REFERENCE),
    "missing_annotation": ("Add a Python annotation or a bounded Pydantic model.", REFERENCE),
    "missing_return_type": ("Declare a serializable return type.", REFERENCE),
    "multiple_tools_in_file": ("Move each tool into its own module.", REFERENCE),
    "tool_file_layout": ("Move the tool to the indicated path and update imports.", REFERENCE),
    "component_file_layout": ("Move the component to its dedicated package.", REFERENCE),
    "component_not_exported": (
        "Add an explicit relative import to __init__.py.",
        REFERENCE,
    ),
    "secret_argument": (
        "Provide secrets through server-side configuration, never through MCP.",
        "https://gofastmcp.com/servers/tools",
    ),
    "blocking_call_in_async": (
        "Use an asynchronous client or move the blocking work.",
        "https://gofastmcp.com/servers/tools",
    ),
    "dangerous_process_call": (
        "Avoid external processes or use a fixed argument list without a shell.",
        REFERENCE,
    ),
    "network_without_timeout": (
        "Set an explicit bounded timeout for every network call.",
        REFERENCE,
    ),
}

CONVENTION_CODES = {
    "missing_description",
    "missing_annotation",
    "missing_return_type",
    "multiple_tools_in_file",
    "tool_file_layout",
    "component_file_layout",
    "component_not_exported",
}
READINESS_CODES = {"todo_skeleton", "incomplete_component", "missing_targeted_test"}
SECURITY_CODES = {
    "secret_argument",
    "blocking_call_in_async",
    "dangerous_process_call",
    "network_without_timeout",
    "invalid_path",
}


def _scope_nodes(tree: ast.AST):
    """Yield one lexical scope without descending into nested definitions."""
    pending = [tree]
    while pending:
        node = pending.pop()
        yield node
        children = list(ast.iter_child_nodes(node))
        if node is not tree and isinstance(
            node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)
        ):
            continue
        pending.extend(reversed(children))


def _import_bindings(tree: ast.AST) -> dict[str, str]:
    """Map local import names to their canonical absolute names."""
    bindings: dict[str, str] = {}
    for node in _scope_nodes(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                local = alias.asname or alias.name.split(".", 1)[0]
                canonical = alias.name if alias.asname else alias.name.split(".", 1)[0]
                bindings[local] = canonical
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            for alias in node.names:
                if alias.name != "*":
                    bindings[alias.asname or alias.name] = f"{node.module}.{alias.name}"
    return bindings


def _qualified_name(
    node: ast.AST,
    imports: dict[str, str] | None = None,
    clients: dict[str, tuple[str, bool]] | None = None,
) -> str:
    """Resolve a dotted expression through import aliases and known HTTP clients."""
    if isinstance(node, ast.Name):
        if clients and node.id in clients:
            return clients[node.id][0]
        return imports.get(node.id, node.id) if imports else node.id
    if isinstance(node, ast.Attribute):
        owner = _qualified_name(node.value, imports, clients)
        return f"{owner}.{node.attr}" if owner else node.attr
    if isinstance(node, ast.Call):
        return _qualified_name(node.func, imports, clients)
    return ""


def _call_name(
    call: ast.Call,
    imports: dict[str, str] | None = None,
    clients: dict[str, tuple[str, bool]] | None = None,
) -> str:
    """Return a canonical dotted call name when it can be determined safely."""
    return _qualified_name(call.func, imports, clients)


SYNC_HTTP_CLIENTS = {"httpx.Client", "requests.Session", "requests.sessions.Session"}
ASYNC_HTTP_CLIENTS = {"httpx.AsyncClient"}
HTTP_CLIENTS = SYNC_HTTP_CLIENTS | ASYNC_HTTP_CLIENTS
NETWORK_METHODS = {"delete", "get", "head", "options", "patch", "post", "put", "request", "send"}


def _client_bindings(
    tree: ast.AST, imports: dict[str, str]
) -> dict[str, tuple[str, bool]]:
    """Find simple variables and context targets bound to supported HTTP clients."""
    bindings: dict[str, tuple[str, bool]] = {}

    def bind(target: ast.AST | None, value: ast.AST | None) -> None:
        if not isinstance(target, ast.Name) or not isinstance(value, ast.Call):
            return
        constructor = _call_name(value, imports)
        if constructor not in HTTP_CLIENTS:
            return
        has_timeout = any(keyword.arg == "timeout" for keyword in value.keywords)
        bindings[target.id] = (constructor, has_timeout)

    for node in _scope_nodes(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                bind(target, node.value)
        elif isinstance(node, ast.AnnAssign):
            bind(node.target, node.value)
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            for item in node.items:
                bind(item.optional_vars, item.context_expr)
    return bindings


def _is_network_call(call_name: str) -> bool:
    """Return whether a canonical call performs or configures an HTTP request."""
    if call_name in HTTP_CLIENTS:
        return False
    if call_name == "urllib.request.urlopen":
        return True
    root = call_name.split(".", 1)[0]
    method = call_name.rsplit(".", 1)[-1]
    return root in {"httpx", "requests"} and method in NETWORK_METHODS


def _client_timeout(call: ast.Call, clients: dict[str, tuple[str, bool]]) -> bool:
    """Return whether a client method inherits a constructor-level timeout."""
    owner = call.func.value if isinstance(call.func, ast.Attribute) else None
    if isinstance(owner, ast.Name) and owner.id in clients:
        return clients[owner.id][1]
    if isinstance(owner, ast.Call):
        return any(keyword.arg == "timeout" for keyword in owner.keywords)
    return False


def _network_without_timeout(
    call: ast.Call,
    call_name: str,
    clients: dict[str, tuple[str, bool]],
) -> bool:
    """Require a per-call or inherited explicit timeout for recognized HTTP I/O."""
    if not _is_network_call(call_name):
        return False
    if any(keyword.arg == "timeout" for keyword in call.keywords):
        return False
    return not _client_timeout(call, clients)


def _blocking_in_async(call_name: str) -> bool:
    """Identify known synchronous blocking calls used from an async function."""
    if call_name == "time.sleep" or call_name == "urllib.request.urlopen":
        return True
    if call_name.startswith("requests."):
        return call_name.rsplit(".", 1)[-1] in NETWORK_METHODS
    if call_name.startswith("httpx.AsyncClient."):
        return False
    if call_name.startswith("httpx.Client."):
        return call_name.rsplit(".", 1)[-1] in NETWORK_METHODS
    return call_name in {f"httpx.{method}" for method in NETWORK_METHODS}


def _is_incomplete_function(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Detect real placeholders without flagging a legitimate nested ``pass``."""
    body = list(node.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        if isinstance(body[0].value.value, str):
            body = body[1:]
    if len(body) == 1 and (
        isinstance(body[0], ast.Pass)
        or (
            isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and body[0].value.value is Ellipsis
        )
    ):
        return True
    return any(
        isinstance(child, ast.Raise)
        and (
            isinstance(child.exc, ast.Name)
            and child.exc.id == "NotImplementedError"
            or isinstance(child.exc, ast.Call)
            and _call_name(child.exc) == "NotImplementedError"
        )
        for child in ast.walk(node)
    )


def _dangerous_process_call(call: ast.Call, call_name: str) -> bool:
    """Reject shells and dynamic argv while allowing a literal argument vector."""
    if call_name == "os.system":
        return True
    if call_name not in {"subprocess.call", "subprocess.run", "subprocess.Popen"}:
        return False
    shell = next((item.value for item in call.keywords if item.arg == "shell"), None)
    if isinstance(shell, ast.Constant) and shell.value is True:
        return True
    if not call.args or not isinstance(call.args[0], (ast.List, ast.Tuple)):
        return True
    return not all(
        isinstance(item, ast.Constant) and isinstance(item.value, str)
        for item in call.args[0].elts
    )


def _literal_string(node: ast.AST | None) -> str | None:
    """Return a literal string without evaluating submitted syntax."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _component_name(node: ast.FunctionDef | ast.AsyncFunctionDef, decorator: ast.AST,
                    kind: str) -> str:
    """Return a static MCP name or URI, falling back to the Python function name."""
    if not isinstance(decorator, ast.Call):
        return node.name
    key = "uri" if kind == "resource" else "name"
    literal = next((item.value for item in decorator.keywords if item.arg == key), None)
    if literal is None and decorator.args:
        literal = decorator.args[0]
    return _literal_string(literal) or node.name


def _resource_matches(template: str, value: str) -> bool:
    """Match one literal resource request against a static URI template."""
    pattern = re.escape(template)
    pattern = re.sub(r"\\\{[A-Za-z_][A-Za-z0-9_]*\\\}", r"[^/]+", pattern)
    return re.fullmatch(pattern, value) is not None


def _test_import_bindings(
    tree: ast.AST, *, kind: str, module: str, function: str
) -> tuple[set[str], set[str], set[str], set[str]]:
    """Resolve explicit component and FastMCP Client imports used by one test module."""
    component_module = f"app.{kind}s.{module}"
    component_package = f"app.{kind}s"
    direct_names: set[str] = set()
    module_names: set[str] = set()
    client_names: set[str] = set()
    server_names: set[str] = set()
    for statement in getattr(tree, "body", []):
        if isinstance(statement, ast.ImportFrom):
            if statement.module == component_module:
                direct_names.update(
                    alias.asname or alias.name
                    for alias in statement.names
                    if alias.name == function
                )
            elif statement.module == component_package:
                module_names.update(
                    alias.asname or alias.name
                    for alias in statement.names
                    if alias.name == module
                )
            elif statement.module == "fastmcp":
                client_names.update(
                    alias.asname or alias.name
                    for alias in statement.names
                    if alias.name == "Client"
                )
            elif statement.module == "app.server":
                server_names.update(
                    alias.asname or alias.name
                    for alias in statement.names
                    if alias.name == "mcp"
                )
        elif isinstance(statement, ast.Import):
            for alias in statement.names:
                if alias.name == component_module:
                    module_names.add(alias.asname or alias.name)
                elif alias.name == "fastmcp":
                    client_names.add(f"{alias.asname or alias.name}.Client")
    return direct_names, module_names, client_names, server_names


def _names_in(node: ast.AST) -> set[str]:
    """Return referenced local names below one expression without evaluating it."""
    return {child.id for child in ast.walk(node) if isinstance(child, ast.Name)}


def _test_function_targets(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    *,
    kind: str,
    name: str,
    function: str,
    module: str,
    direct_names: set[str],
    module_names: set[str],
    client_names: set[str],
    server_names: set[str],
) -> bool:
    """Return whether one test imports, invokes, and asserts the selected component."""
    if not node.name.startswith("test_"):
        return False

    client_method = {"tool": "call_tool", "resource": "read_resource", "prompt": "get_prompt"}[
        kind
    ]
    client_variables: set[str] = set()
    for context in (
        child
        for child in ast.walk(node)
        if isinstance(child, (ast.With, ast.AsyncWith))
    ):
        for item in context.items:
            if not isinstance(item.context_expr, ast.Call):
                continue
            if _call_name(item.context_expr) not in client_names:
                continue
            if (
                not item.context_expr.args
                or not isinstance(item.context_expr.args[0], ast.Name)
                or item.context_expr.args[0].id not in server_names
            ):
                continue
            if isinstance(item.optional_vars, ast.Name):
                client_variables.add(item.optional_vars.id)

    def targets(call: ast.Call) -> bool:
        """Recognize a resolved direct invocation or a bound FastMCP client call."""
        call_name = _call_name(call)
        if call_name in direct_names or any(
            call_name == f"{module_name}.{function}" for module_name in module_names
        ):
            return True
        if not isinstance(call.func, ast.Attribute) or call.func.attr != client_method:
            return False
        if not isinstance(call.func.value, ast.Name) or call.func.value.id not in client_variables:
            return False
        if not call.args:
            return False
        requested = _literal_string(call.args[0])
        if requested is None:
            return False
        return requested == name or (kind == "resource" and _resource_matches(name, requested))

    result_names: set[str] = set()
    for assignment in ast.walk(node):
        value = None
        targets_to_bind: list[ast.expr] = []
        if isinstance(assignment, (ast.Assign, ast.AnnAssign)):
            value = assignment.value
            targets_to_bind = (
                assignment.targets if isinstance(assignment, ast.Assign) else [assignment.target]
            )
        if value is None or not any(
            targets(call) for call in ast.walk(value) if isinstance(call, ast.Call)
        ):
            continue
        for target in targets_to_bind:
            if isinstance(target, ast.Name):
                result_names.add(target.id)

    for assertion in ast.walk(node):
        expression: ast.AST | None = None
        if isinstance(assertion, ast.Assert):
            expression = assertion.test
        elif (
            isinstance(assertion, ast.Call)
            and isinstance(assertion.func, ast.Attribute)
            and assertion.func.attr.startswith("assert")
        ):
            expression = assertion
        if expression is None:
            continue
        if any(targets(call) for call in ast.walk(expression) if isinstance(call, ast.Call)):
            return True
        if result_names & _names_in(expression):
            return True

    for context in (
        child
        for child in ast.walk(node)
        if isinstance(child, (ast.With, ast.AsyncWith))
    ):
        raises = False
        for item in context.items:
            expression = item.context_expr
            if (
                not isinstance(expression, ast.Call)
                or not _call_name(expression).endswith(".raises")
                or not expression.args
            ):
                continue
            expected = expression.args[0]
            broad = isinstance(expected, ast.Name) and expected.id in {
                "Exception", "BaseException",
            }
            if not broad:
                raises = True
                break
        if raises and any(
            targets(call)
            for statement in context.body
            for call in ast.walk(statement)
            if isinstance(call, ast.Call)
        ):
            return True
    return False


def _has_targeted_test(
    test_trees: dict[str, ast.AST],
    *,
    kind: str,
    name: str,
    function: str,
    module: str,
) -> bool:
    """Find a focused test by semantic invocation and assertion, not filename."""
    for tree in test_trees.values():
        direct_names, module_names, client_names, server_names = _test_import_bindings(
            tree, kind=kind, module=module, function=function
        )
        if any(
            _test_function_targets(
                node,
                kind=kind,
                name=name,
                function=function,
                module=module,
                direct_names=direct_names,
                module_names=module_names,
                client_names=client_names,
                server_names=server_names,
            )
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ):
            return True
    return False


def validate_project(
    files: list[dict], profile: ValidationProfile = "recommended"
) -> dict:
    """Inspect a bounded project with framework, recommended, or strict policy.

    ``framework`` validates portable Python/FastMCP and essential security only.
    ``recommended`` also reports MCP Builder conventions as warnings. ``strict``
    promotes those convention findings to errors. TODOs and missing focused tests
    block ``ready`` without invalidating an otherwise valid project.
    """
    if profile not in {"framework", "recommended", "strict"}:
        raise ValueError("Expected validation profile: framework, recommended, or strict")
    if not 1 <= len(files) <= 100:
        raise ValueError("Between 1 and 100 files are required")
    if sum(len(item.get("content", "").encode()) for item in files) > 1_000_000:
        raise ValueError("Project size is limited to 1 MB")

    diagnostics: list[dict] = []
    seen_paths: set[str] = set()
    identities: dict[tuple[str, str], str] = {}
    modules_by_package: dict[str, set[str]] = {}
    declared_by_file: dict[str, list[tuple[str, str, str, int]]] = {}
    python_trees: dict[str, ast.AST] = {}

    def report(
        path: str,
        line: int,
        code: str,
        message: str,
        severity: Literal["warning", "error"] = "warning",
    ) -> None:
        """Append a profile-aware located diagnostic."""
        if code in CONVENTION_CODES:
            if profile == "framework":
                return
            severity = "error" if profile == "strict" else "warning"
        suggestion, documentation = DIAGNOSTIC_HELP.get(
            code, ("Review and fix this diagnostic.", REFERENCE)
        )
        diagnostics.append(
            {
                "path": path,
                "line": max(1, line),
                "code": code,
                "message": message,
                "severity": severity,
                "suggestion": suggestion,
                "documentation": documentation,
            }
        )

    for item in files:
        path, content = item["path"], item["content"]
        parts = PurePosixPath(path).parts
        if (
            not path
            or "\\" in path
            or ":" in path
            or path.startswith("/")
            or ".." in parts
            or path in seen_paths
        ):
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
        python_trees[path] = tree
        import_bindings = _import_bindings(tree)
        client_bindings = _client_bindings(tree, import_bindings)
        if "TODO" in content:
            report(path, 1, "todo_skeleton", "Replace the TODO skeleton before use")
        if path.startswith("app/"):
            call_scopes: dict[
                int, tuple[dict[str, str], dict[str, tuple[str, bool]]]
            ] = {}
            for function_node in (
                child
                for child in ast.walk(tree)
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
            ):
                function_imports = {
                    **import_bindings,
                    **_import_bindings(function_node),
                }
                function_clients = {
                    **client_bindings,
                    **_client_bindings(function_node, function_imports),
                }
                function_calls = [
                    child
                    for child in _scope_nodes(function_node)
                    if isinstance(child, ast.Call)
                ]
                call_scopes.update(
                    (id(call), (function_imports, function_clients))
                    for call in function_calls
                )
                if _is_incomplete_function(function_node):
                    report(
                        path,
                        function_node.lineno,
                        "incomplete_component",
                        f"Function {function_node.name} still contains placeholder behavior",
                    )
                if isinstance(function_node, ast.AsyncFunctionDef):
                    for call in function_calls:
                        call_name = _call_name(call, function_imports, function_clients)
                        if _blocking_in_async(call_name):
                            report(
                                path,
                                call.lineno,
                                "blocking_call_in_async",
                                f"Blocking call in an async function: {call_name}",
                                "error",
                            )
            for call in (
                child for child in ast.walk(tree) if isinstance(child, ast.Call)
            ):
                scoped_imports, scoped_clients = call_scopes.get(
                    id(call), (import_bindings, client_bindings)
                )
                call_name = _call_name(call, scoped_imports, scoped_clients)
                if _dangerous_process_call(call, call_name):
                    report(
                        path,
                        call.lineno,
                        "dangerous_process_call",
                        f"Sensitive process call detected: {call_name}",
                        "error",
                    )
                if _network_without_timeout(call, call_name, scoped_clients):
                    report(
                        path,
                        call.lineno,
                        "network_without_timeout",
                        f"Network call without an explicit timeout: {call_name}",
                        "error",
                    )
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
                    report(
                        path,
                        node.lineno,
                        "legacy_import",
                        "Use from fastmcp import FastMCP",
                        "error",
                    )
                if node.module == "fastmcp":
                    for alias in node.names:
                        if alias.name not in {"FastMCP", "Client", "Context"}:
                            report(
                                path,
                                node.lineno,
                                "unverified_import",
                                f"Import {alias.name} is not verified by this validator",
                            )
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                target = decorator.func if isinstance(decorator, ast.Call) else decorator
                if not isinstance(target, ast.Attribute) or target.attr not in {
                    "tool",
                    "resource",
                    "prompt",
                }:
                    continue
                kind = target.attr
                name = _component_name(node, decorator, kind)
                identity = (kind, name)
                declared_by_file.setdefault(path, []).append(
                    (kind, name, node.name, node.lineno)
                )
                if identity in identities:
                    report(
                        path,
                        node.lineno,
                        "duplicate_component",
                        f"{kind} {name} is already declared in {identities[identity]}",
                        "error",
                    )
                identities[identity] = path
                has_description = isinstance(decorator, ast.Call) and any(
                    keyword.arg == "description" for keyword in decorator.keywords
                )
                if not ast.get_docstring(node) and not has_description:
                    report(path, node.lineno, "missing_description", "Add a description")
                args = [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
                for argument in args:
                    if argument.annotation is None and argument.arg not in {"self", "cls"}:
                        report(
                            path,
                            node.lineno,
                            "missing_annotation",
                            f"Add a type to parameter {argument.arg}",
                        )
                    if any(
                        token in argument.arg.lower()
                        for token in ("secret", "password", "passwd", "api_key", "token")
                    ):
                        report(
                            path,
                            node.lineno,
                            "secret_argument",
                            f"Parameter {argument.arg} appears to carry a secret",
                            "error",
                        )
                if node.returns is None:
                    report(path, node.lineno, "missing_return_type", "Add a return type")

    test_trees = {
        path: tree
        for path, tree in python_trees.items()
        if path.startswith("tests/")
    }
    for path, declarations in declared_by_file.items():
        public_tools = [item for item in declarations if item[0] == "tool"]
        if len(public_tools) > 1:
            report(
                path,
                public_tools[1][3],
                "multiple_tools_in_file",
                "Only one public tool is allowed per file",
            )
        for kind, name, function, line in declarations:
            package = f"app/{kind}s"
            module = PurePosixPath(path).stem
            if PurePosixPath(path).parent.as_posix() != package or module != function:
                code = "tool_file_layout" if kind == "tool" else "component_file_layout"
                report(
                    path,
                    line,
                    code,
                    f"The {kind} {function} should be in {package}/{function}.py",
                )
            if PurePosixPath(path).parent.as_posix() == package:
                if module not in modules_by_package.get(package, set()):
                    report(
                        path,
                        line,
                        "component_not_exported",
                        f"Import {module} explicitly from {package}/__init__.py",
                    )
            if not _has_targeted_test(
                test_trees,
                kind=kind,
                name=name,
                function=function,
                module=module,
            ):
                report(
                    path,
                    line,
                    "missing_targeted_test",
                    f"No test invokes and asserts the {kind} {name}",
                )

    valid = not any(item["severity"] == "error" for item in diagnostics)
    readiness_issues = [
        item
        for item in diagnostics
        if item["severity"] == "error" or item["code"] in READINESS_CODES
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "generator_version": BUILDER_VERSION,
        "fastmcp_version": FASTMCP_VERSION,
        "profile": profile,
        "valid": valid,
        "ready": valid and not readiness_issues,
        "readiness_issues": readiness_issues,
        "diagnostics": diagnostics,
        "executed": False,
        "limitations": (
            "Static analysis only: dynamic resolution, imports, installed dependencies, "
            "and runtime behavior are not evaluated. Readiness covers source evidence only; "
            "runtime lint, tests, discovery, and transport checks must be assessed separately."
        ),
    }


def review_project_security(files: list[dict]) -> dict:
    """Return focused high-confidence security diagnostics from framework validation."""
    result = validate_project(files, profile="framework")
    diagnostics = [
        item for item in result["diagnostics"] if item["code"] in SECURITY_CODES
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "generator_version": BUILDER_VERSION,
        "fastmcp_version": FASTMCP_VERSION,
        "passed": not diagnostics,
        "diagnostics": diagnostics,
        "executed": False,
        "limitations": (
            "Focused AST analysis only: data flows, dependencies, dynamic imports, and runtime "
            "behavior are not evaluated."
        ),
    }
