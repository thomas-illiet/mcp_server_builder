"""Guarded patch proposals for existing projects; changes are never applied here."""

import ast
import hashlib
from pathlib import PurePosixPath

from .components import generate_prompt, generate_resource, generate_tool
from .schemas import PatchProposal, PromptSpec, ResourceSpec, ToolSpec


def _digest(content: str) -> str:
    """Return the exact source-content digest used for optimistic concurrency."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _change(path: str, content: str, reason: str, existing: str | None = None) -> dict:
    """Build one create/replace change guarded by the original content digest."""
    return {"path": path, "operation": "replace" if existing is not None else "create",
            "content": content, "original_sha256": _digest(existing) if existing is not None else None,
            "reason": reason}


def propose_project_patch(kind: str, specification: dict, files: list[dict]) -> PatchProposal:
    """Propose component, test and explicit registration changes for an existing project."""
    if not 1 <= len(files) <= 100:
        raise ValueError("Entre 1 et 100 fichiers requis")
    if sum(len(item.get("content", "").encode()) for item in files) > 1_000_000:
        raise ValueError("Projet limité à 1 Mo")
    file_map: dict[str, str] = {}
    for item in files:
        path = item["path"]
        parts = PurePosixPath(path).parts
        if (not path or path in file_map or path.startswith("/") or "\\" in path
                or ":" in path or ".." in parts):
            raise ValueError("Le projet contient un chemin invalide ou dupliqué")
        file_map[path] = item["content"]
    generators = {
        "tool": (ToolSpec, generate_tool, "tools"),
        "resource": (ResourceSpec, generate_resource, "resources"),
        "prompt": (PromptSpec, generate_prompt, "prompts"),
    }
    if kind not in generators:
        raise ValueError("Type de composant attendu : tool, resource ou prompt")
    model, generator, package = generators[kind]
    generated = generator(model.model_validate(specification))
    component, test = generated.files
    name = component.path.rsplit("/", 1)[-1].removesuffix(".py")
    init_path = f"app/{package}/__init__.py"
    init_existing = file_map.get(init_path)
    init_content = init_existing or f'"""Explicitly register {package}."""\n'
    try:
        init_tree = ast.parse(init_content)
    except SyntaxError as exc:
        raise ValueError(f"Impossible de modifier {init_path} : syntaxe invalide") from exc
    registered = any(
        isinstance(statement, ast.ImportFrom) and statement.level == 1
        and ((statement.module or "").split(".", 1)[0] == name
             or (statement.module is None
                 and any(alias.name == name for alias in statement.names)))
        for statement in init_tree.body
    )
    changes = [
        _change(component.path, component.content,
                f"Ajouter ou régénérer le {kind} {name} dans son module dédié.",
                file_map.get(component.path)),
        _change(test.path, test.content,
                f"Ajouter ou régénérer le test ciblé du {kind} {name}.", file_map.get(test.path)),
    ]
    if not registered:
        separator = "" if init_content.endswith("\n") else "\n"
        updated = f"{init_content}{separator}\nfrom . import {name} as {name}\n"
        changes.append(_change(init_path, updated,
                               f"Enregistrer explicitement le module {name}.", init_existing))
    warnings = list(generated.warnings)
    if component.path in file_map or test.path in file_map:
        warnings.append("Au moins un fichier existant serait remplacé ; vérifier original_sha256.")
    return PatchProposal(changes=changes, warnings=warnings,
                         assumptions=generated.assumptions,
                         references=generated.references)
