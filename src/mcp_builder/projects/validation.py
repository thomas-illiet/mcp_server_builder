"""Static Python/TOML diagnostics without importing submitted code."""
import ast
import tomllib
from pathlib import PurePosixPath


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

    def report(path, line, code, message, severity="warning"):
        """Append one located diagnostic without retaining files outside this request."""
        diagnostics.append({"path": path, "line": line, "code": code,
                            "message": message, "severity": severity})

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
                if node.returns is None:
                    report(path, node.lineno, "missing_return_type", "Typer la valeur de retour")
    return {"valid": not any(d["severity"] == "error" for d in diagnostics),
            "diagnostics": diagnostics, "executed": False,
            "limitations": "Analyse statique seulement : pas de résolution dynamique, d'import, "
                           "de vérification des dépendances installées ni de garantie fonctionnelle. "
                           "Les doublons sont signalés sans résoudre les instances de serveur."}
