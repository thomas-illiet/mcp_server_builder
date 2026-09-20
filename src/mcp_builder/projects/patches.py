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
    """Propose only non-destructive component, test, and registration changes."""
    if not 1 <= len(files) <= 100:
        raise ValueError("Between 1 and 100 files are required")
    if sum(len(item.get("content", "").encode()) for item in files) > 1_000_000:
        raise ValueError("Project size is limited to 1 MB")
    file_map: dict[str, str] = {}
    for item in files:
        path = item["path"]
        parts = PurePosixPath(path).parts
        if (not path or path in file_map or path.startswith("/") or "\\" in path
                or ":" in path or ".." in parts):
            raise ValueError("The project contains an invalid or duplicate path")
        file_map[path] = item["content"]
    generators = {
        "tool": (ToolSpec, generate_tool, "tools"),
        "resource": (ResourceSpec, generate_resource, "resources"),
        "prompt": (PromptSpec, generate_prompt, "prompts"),
    }
    if kind not in generators:
        raise ValueError("Expected component type: tool, resource, or prompt")
    model, generator, package = generators[kind]
    generated = generator(model.model_validate(specification))
    component, test = generated.files
    name = component.path.rsplit("/", 1)[-1].removesuffix(".py")
    conflicts = [
        {
            "path": path,
            "reason": (
                "A generated skeleton must not replace existing code. OpenCode must inspect "
                "this file and produce a targeted diff."
            ),
            "original_sha256": _digest(file_map[path]),
        }
        for path in (component.path, test.path)
        if path in file_map
    ]
    if conflicts:
        return PatchProposal(
            changes=[],
            conflicts=conflicts,
            warnings=[
                "No changes were proposed because a component or focused test already exists."
            ],
            assumptions=generated.assumptions,
            references=generated.references,
        )

    init_path = f"app/{package}/__init__.py"
    init_existing = file_map.get(init_path)
    init_content = init_existing or f'"""Explicitly register {package}."""\n'
    try:
        init_tree = ast.parse(init_content)
    except SyntaxError as exc:
        raise ValueError(f"Cannot modify {init_path}: invalid syntax") from exc
    registered = any(
        isinstance(statement, ast.ImportFrom) and statement.level == 1
        and ((statement.module or "").split(".", 1)[0] == name
             or (statement.module is None
                 and any(alias.name == name for alias in statement.names)))
        for statement in init_tree.body
    )
    changes = [
        _change(component.path, component.content,
                f"Add the {kind} {name} in its dedicated module."),
        _change(test.path, test.content,
                f"Add the focused test for {kind} {name}."),
    ]
    if not registered:
        separator = "" if init_content.endswith("\n") else "\n"
        updated = f"{init_content}{separator}\nfrom . import {name} as {name}\n"
        changes.append(_change(init_path, updated,
                               f"Register the {name} module explicitly.", init_existing))
    return PatchProposal(changes=changes, conflicts=[], warnings=list(generated.warnings),
                         assumptions=generated.assumptions,
                         references=generated.references)
