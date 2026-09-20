"""Generate and verify server-side configuration declared by a blueprint."""

from __future__ import annotations

import ast
from dataclasses import dataclass

from .schemas import ProjectBlueprint


@dataclass(frozen=True)
class ConfigurationRequirement:
    """One environment key and the strictest requirement declared for it."""

    key: str
    required: bool
    descriptions: tuple[str, ...]


def configuration_requirements(
    blueprint: ProjectBlueprint,
) -> list[ConfigurationRequirement]:
    """Merge secret and data-source keys without ever accepting their values."""
    declared: dict[str, tuple[bool, list[str]]] = {}
    for secret in blueprint.secrets:
        required, descriptions = declared.setdefault(
            secret.environment_variable, (False, [])
        )
        descriptions.append(secret.description)
        declared[secret.environment_variable] = (
            required or secret.required,
            descriptions,
        )
    for source in blueprint.data_sources:
        for key in source.configuration_keys:
            required, descriptions = declared.setdefault(key, (False, []))
            descriptions.append(f"{source.name}: {source.description}")
            declared[key] = (True, descriptions)
    return [
        ConfigurationRequirement(key, required, tuple(dict.fromkeys(descriptions)))
        for key, (required, descriptions) in sorted(declared.items())
    ]


def render_configuration_module(
    requirements: list[ConfigurationRequirement],
) -> str:
    """Return a startup-validated settings module with no secret values embedded."""
    entries = "\n".join(
        f'        {item.key!r}: _read({item.key!r}, required={item.required!r}),'
        for item in requirements
    )
    return f'''"""Load blueprint-declared server configuration without logging values."""

import os


def _read(name: str, *, required: bool) -> str | None:
    """Read one value and fail startup when a required setting is absent."""
    value = os.getenv(name)
    if required and not value:
        raise RuntimeError(f"Missing required server configuration: {{name}}")
    return value


def load_settings() -> dict[str, str | None]:
    """Load the complete immutable-by-convention server-side configuration."""
    return {{
{entries}
    }}


settings = load_settings()
'''


def extend_env_example(
    content: str,
    requirements: list[ConfigurationRequirement],
) -> str:
    """Document each declared key while retaining existing template guidance."""
    existing = {
        line.split("=", 1)[0].strip()
        for line in content.splitlines()
        if "=" in line and not line.lstrip().startswith("#")
    }
    blocks: list[str] = []
    for item in requirements:
        if item.key in existing:
            continue
        requirement = "Required" if item.required else "Optional"
        description = " ".join(value.replace("\n", " ") for value in item.descriptions)
        blocks.append(f"# {requirement}: {description}\n{item.key}=")
    if not blocks:
        return content
    prefix = content.rstrip("\n")
    separator = "\n\n" if prefix else ""
    return f"{prefix}{separator}{'\n\n'.join(blocks)}\n"


def wire_compose(
    content: str,
    requirements: list[ConfigurationRequirement],
) -> str:
    """Pass declared host settings into the hardened generated container."""
    if not requirements:
        return content
    settings = [
        (
            f'      {item.key}: "${{{item.key}:?Set {item.key} in .env}}"'
            if item.required
            else f'      {item.key}: "${{{item.key}:-}}"'
        )
        for item in requirements
    ]
    lines = content.splitlines()
    try:
        environment_index = lines.index("    environment:")
    except ValueError:
        try:
            insertion = lines.index("    read_only: true") + 1
        except ValueError as exc:
            raise ValueError("Generated Compose service has no safe insertion point") from exc
        lines[insertion:insertion] = ["    environment:", *settings]
    else:
        insertion = environment_index + 1
        while insertion < len(lines) and lines[insertion].startswith("      "):
            insertion += 1
        lines[insertion:insertion] = settings
    return "\n".join(lines) + "\n"


def wire_server(content: str) -> str:
    """Make importing the generated server validate its configuration immediately."""
    marker = "from app.instance import mcp"
    if marker not in content:
        raise ValueError("Generated server does not import the shared MCP instance")
    configuration_import = "from app.config import settings  # noqa: F401"
    if configuration_import in content:
        return content
    return content.replace(marker, f"{configuration_import}\n{marker}", 1)


def _call_name(call: ast.Call) -> str:
    """Return the static dotted name of a call when available."""
    parts: list[str] = []
    node = call.func
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def _without_yaml_comment(value: str) -> str:
    """Remove an active YAML comment while preserving hashes inside quoted values."""
    quote: str | None = None
    escaped = False
    for index, character in enumerate(value):
        if quote == '"' and character == "\\" and not escaped:
            escaped = True
            continue
        if character in {"'", '"'} and not escaped:
            quote = None if quote == character else character if quote is None else quote
        elif character == "#" and quote is None and (
            index == 0 or value[index - 1].isspace()
        ):
            return value[:index].rstrip()
        escaped = False
    return value.rstrip()


def _compose_server_environment(content: str) -> dict[str, str]:
    """Return active values declared under ``services.server.environment`` only.

    Generated Compose files use a bounded mapping shape, so a small indentation
    reader is preferable to loading an executable or feature-rich YAML parser.
    Comment-only lines never affect structure or satisfy a configuration key.
    """
    top_level: str | None = None
    service: str | None = None
    environment_indent: int | None = None
    entry_indent: int | None = None
    values: dict[str, str] = {}

    for raw_line in content.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        prefix = raw_line[: len(raw_line) - len(raw_line.lstrip(" "))]
        if "\t" in prefix:
            continue
        indent = len(prefix)
        active = _without_yaml_comment(raw_line[indent:]).strip()
        if not active:
            continue

        if indent == 0:
            top_level = active[:-1] if active.endswith(":") else None
            service = None
            environment_indent = None
            entry_indent = None
            continue
        if indent == 2:
            service = (
                active[:-1]
                if top_level == "services" and active.endswith(":")
                else None
            )
            environment_indent = None
            entry_indent = None
            continue
        if indent == 4:
            environment_indent = (
                indent
                if top_level == "services" and service == "server" and active == "environment:"
                else None
            )
            entry_indent = None
            continue
        if environment_indent is None or indent <= environment_indent:
            continue
        if entry_indent is None:
            entry_indent = indent
        if indent != entry_indent:
            continue

        if active.startswith("- ") and "=" in active:
            key, value = active[2:].split("=", 1)
        elif ":" in active:
            key, value = active.split(":", 1)
        else:
            continue
        key = key.strip().strip("'\"")
        if key:
            values[key] = value.strip()
    return values


def configuration_issues(
    files: list[dict],
    requirements: list[ConfigurationRequirement],
) -> list[tuple[str, str, str]]:
    """Return bounded static issues for missing documentation, loading, or wiring."""
    if not requirements:
        return []
    file_map = {item["path"]: item["content"] for item in files}
    issues: list[tuple[str, str, str]] = []

    env_content = file_map.get(".env.example", "")
    documented = {
        line.split("=", 1)[0].strip()
        for line in env_content.splitlines()
        if "=" in line and not line.lstrip().startswith("#")
    }
    for item in requirements:
        if item.key not in documented:
            issues.append((
                "blueprint_configuration_missing",
                f"The blueprint configuration key {item.key!r} is missing from .env.example.",
                ".env.example",
            ))

    config_content = file_map.get("app/config.py")
    loaded: dict[str, bool] = {}
    has_startup_load = False
    has_required_guard = False
    if config_content is not None:
        try:
            tree = ast.parse(config_content)
        except (SyntaxError, ValueError, RecursionError):
            tree = None
        if tree is not None:
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "_read":
                    has_environment_read = any(
                        isinstance(call, ast.Call) and _call_name(call) == "os.getenv"
                        for call in ast.walk(node)
                    )
                    has_guarded_raise = any(
                        isinstance(branch, ast.If)
                        and any(
                            isinstance(name, ast.Name) and name.id == "required"
                            for name in ast.walk(branch.test)
                        )
                        and any(isinstance(child, ast.Raise) for child in ast.walk(branch))
                        for branch in ast.walk(node)
                    )
                    has_required_guard = has_environment_read and has_guarded_raise
                if isinstance(node, ast.Call) and _call_name(node) == "_read" and node.args:
                    try:
                        key = ast.literal_eval(node.args[0])
                    except (ValueError, TypeError, SyntaxError):
                        continue
                    required = next(
                        (
                            keyword.value.value
                            for keyword in node.keywords
                            if keyword.arg == "required"
                            and isinstance(keyword.value, ast.Constant)
                            and isinstance(keyword.value.value, bool)
                        ),
                        None,
                    )
                    if isinstance(key, str) and required is not None:
                        loaded[key] = required
                if isinstance(node, (ast.Assign, ast.AnnAssign)):
                    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                    value = node.value
                    has_startup_load = has_startup_load or (
                        any(isinstance(target, ast.Name) and target.id == "settings" for target in targets)
                        and isinstance(value, ast.Call)
                        and _call_name(value) == "load_settings"
                    )

    if config_content is None or not has_required_guard or not has_startup_load:
        issues.append((
            "blueprint_configuration_loader_missing",
            "app/config.py must read declared environment keys and fail startup for missing required values.",
            "app/config.py",
        ))
    for item in requirements:
        if loaded.get(item.key) != item.required:
            issues.append((
                "blueprint_configuration_requiredness_mismatch",
                f"Configuration key {item.key!r} must be loaded with required={item.required!r}.",
                "app/config.py",
            ))

    server_content = file_map.get("app/server.py", "")
    try:
        server_tree = ast.parse(server_content)
    except (SyntaxError, ValueError, RecursionError):
        server_tree = None
    imports_settings = bool(server_tree) and any(
        isinstance(node, ast.ImportFrom)
        and node.module == "app.config"
        and any(alias.name == "settings" for alias in node.names)
        for node in ast.walk(server_tree)
    )
    if not imports_settings:
        issues.append((
            "blueprint_configuration_startup_missing",
            "app/server.py must import the validated settings during startup.",
            "app/server.py",
        ))

    compose_environment = _compose_server_environment(file_map.get("compose.yaml", ""))
    for item in requirements:
        marker = f"${{{item.key}:?" if item.required else f"${{{item.key}:-}}"
        if marker not in compose_environment.get(item.key, ""):
            issues.append((
                "blueprint_configuration_compose_missing",
                f"Compose does not pass configuration key {item.key!r} with the declared requiredness.",
                "compose.yaml",
            ))
    return issues
