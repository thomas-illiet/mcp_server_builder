"""Static Python/TOML diagnostics without importing submitted code."""
import ast
import tomllib
from pathlib import PurePosixPath

from mcp_builder import BUILDER_VERSION, FASTMCP_VERSION, SCHEMA_VERSION

REFERENCE = "https://gofastmcp.com/servers/tools"
DIAGNOSTIC_HELP = {
    "invalid_path": ("Utiliser un chemin POSIX relatif, unique et sans '..'.", REFERENCE),
    "toml_syntax": ("Corriger le document TOML indiqué par le parseur.",
                    "https://packaging.python.org/en/latest/guides/writing-pyproject-toml/"),
    "python_syntax": ("Corriger la syntaxe Python avant toute autre validation.",
                      "https://docs.python.org/3/reference/"),
    "todo_skeleton": ("Implémenter la logique métier et adapter le test ciblé.", REFERENCE),
    "legacy_import": ("Remplacer cet import par `from fastmcp import FastMCP`.", REFERENCE),
    "unverified_import": ("Vérifier cet import dans la documentation FastMCP ciblée.", REFERENCE),
    "duplicate_component": ("Renommer ou supprimer l'une des déclarations.", REFERENCE),
    "missing_description": ("Ajouter une docstring ou `description=` au décorateur.", REFERENCE),
    "missing_annotation": ("Ajouter une annotation Python ou un modèle Pydantic borné.", REFERENCE),
    "missing_return_type": ("Déclarer un type de retour sérialisable.", REFERENCE),
    "multiple_tools_in_file": ("Déplacer chaque tool dans son propre module.", REFERENCE),
    "tool_file_layout": ("Déplacer le tool vers le chemin indiqué et mettre à jour les imports.",
                         REFERENCE),
    "component_file_layout": ("Déplacer le composant vers son package dédié.", REFERENCE),
    "component_not_exported": ("Ajouter un import relatif explicite dans le __init__.py.", REFERENCE),
    "secret_argument": ("Fournir les secrets côté serveur via la configuration, jamais via MCP.",
                        "https://gofastmcp.com/servers/tools"),
    "blocking_call_in_async": ("Utiliser un client asynchrone ou déplacer le travail bloquant.",
                               "https://gofastmcp.com/servers/tools"),
    "dangerous_process_call": ("Éviter les processus externes ou employer une liste d'arguments "
                               "fixe sans shell.", REFERENCE),
    "network_without_timeout": ("Définir un timeout explicite et borné pour chaque appel réseau.",
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
        raise ValueError("Entre 1 et 100 fichiers requis")
    if sum(len(f.get("content", "").encode()) for f in files) > 1_000_000:
        raise ValueError("Projet limité à 1 Mo")
    diagnostics, seen_paths, components = [], set(), {}
    modules_by_package: dict[str, set[str]] = {}
    declared_by_file: dict[str, list[tuple[str, str, int]]] = {}

    def report(path, line, code, message, severity="warning"):
        """Append one located diagnostic without retaining files outside this request."""
        suggestion, documentation = DIAGNOSTIC_HELP.get(
            code, ("Examiner et corriger ce diagnostic.", REFERENCE)
        )
        diagnostics.append({"path": path, "line": line, "code": code,
                            "message": message, "severity": severity,
                            "suggestion": suggestion, "documentation": documentation})

    for item in files:
        path, content = item["path"], item["content"]
        parts = PurePosixPath(path).parts
        if (not path or "\\" in path or ":" in path or path.startswith("/")
                or ".." in parts or path in seen_paths):
            report(path, 1, "invalid_path", "Chemin relatif invalide ou dupliqué", "error")
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
            report(path, 1, "todo_skeleton", "Remplacer le squelette TODO avant utilisation")
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
                    report(path, node.lineno, "legacy_import", "Utiliser from fastmcp import FastMCP")
                if node.module == "fastmcp":
                    for alias in node.names:
                        if alias.name not in {"FastMCP", "Client", "Context"}:
                            report(path, node.lineno, "unverified_import",
                                   f"Import {alias.name} non vérifié par ce validateur")
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
                           f"{target.attr} {name} déjà déclaré dans {components[identity]}")
                components[identity] = path
                has_description = isinstance(decorator, ast.Call) and any(
                    kw.arg == "description" for kw in decorator.keywords
                )
                if not ast.get_docstring(node) and not has_description:
                    report(path, node.lineno, "missing_description", "Ajouter une description")
                args = [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
                for arg in args:
                    if arg.annotation is None and arg.arg not in {"self", "cls"}:
                        report(path, node.lineno, "missing_annotation", f"Typer le paramètre {arg.arg}")
                    if any(token in arg.arg.lower() for token in (
                        "secret", "password", "passwd", "api_key", "token"
                    )):
                        report(path, node.lineno, "secret_argument",
                               f"Le paramètre {arg.arg} semble transporter un secret")
                if node.returns is None:
                    report(path, node.lineno, "missing_return_type", "Typer la valeur de retour")
                for call in (child for child in ast.walk(node) if isinstance(child, ast.Call)):
                    call_name = _call_name(call)
                    if call_name in {"os.system", "subprocess.call", "subprocess.run",
                                     "subprocess.Popen"}:
                        report(path, call.lineno, "dangerous_process_call",
                               f"Appel de processus sensible détecté : {call_name}")
                    if isinstance(node, ast.AsyncFunctionDef) and (
                        call_name == "time.sleep" or call_name.startswith("requests.")
                    ):
                        report(path, call.lineno, "blocking_call_in_async",
                               f"Appel bloquant dans une fonction async : {call_name}")
                    if (call_name.startswith(("requests.", "httpx."))
                            and not any(keyword.arg == "timeout" for keyword in call.keywords)):
                        report(path, call.lineno, "network_without_timeout",
                               f"Appel réseau sans timeout explicite : {call_name}")
    for path, declarations in declared_by_file.items():
        public_tools = [item for item in declarations if item[0] == "tool"]
        if len(public_tools) > 1:
            report(path, public_tools[1][2], "multiple_tools_in_file",
                   "Un seul tool public est autorisé par fichier", "error")
        for kind, name, line in declarations:
            package = f"app/{kind}s"
            module = PurePosixPath(path).stem
            if (PurePosixPath(path).parent.as_posix() != package or module != name):
                code = "tool_file_layout" if kind == "tool" else "component_file_layout"
                report(path, line, code,
                       f"Le {kind} {name} doit être dans {package}/{name}.py", "error")
            if PurePosixPath(path).parent.as_posix() == package:
                if module not in modules_by_package.get(package, set()):
                    report(path, line, "component_not_exported",
                           f"Importer explicitement {module} depuis {package}/__init__.py",
                           "error")
    return {"schema_version": SCHEMA_VERSION, "generator_version": BUILDER_VERSION,
            "fastmcp_version": FASTMCP_VERSION,
            "valid": not any(d["severity"] == "error" for d in diagnostics),
            "diagnostics": diagnostics, "executed": False,
            "limitations": "Analyse statique seulement : pas de résolution dynamique, d'import, "
                           "de vérification des dépendances installées ni de garantie fonctionnelle. "
                           "Les doublons sont signalés sans résoudre les instances de serveur."}


def review_project_security(files: list[dict]) -> dict:
    """Return focused high-confidence security diagnostics from the static validator."""
    result = validate_project(files)
    security_codes = {"secret_argument", "blocking_call_in_async", "dangerous_process_call",
                      "network_without_timeout", "invalid_path"}
    diagnostics = [item for item in result["diagnostics"] if item["code"] in security_codes]
    return {"schema_version": SCHEMA_VERSION, "generator_version": BUILDER_VERSION,
            "fastmcp_version": FASTMCP_VERSION,
            "passed": not diagnostics, "diagnostics": diagnostics, "executed": False,
            "limitations": "Analyse AST ciblée seulement : les flux de données, dépendances, "
                           "imports dynamiques et comportements à l'exécution ne sont pas évalués."}
