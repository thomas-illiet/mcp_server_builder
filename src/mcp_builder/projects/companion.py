"""Deterministic high-level workflows for an OpenCode FastMCP companion."""

from __future__ import annotations

import ast
import inspect
from collections.abc import Callable, Iterable

from .components import generate_prompt, generate_resource, generate_tool
from .configuration import (
    configuration_issues,
    configuration_requirements,
    extend_env_example,
    render_configuration_module,
    wire_compose,
    wire_server,
)
from .inspection import inspect_project
from .schemas import (
    BlueprintGenerationResult,
    BlueprintValidationResult,
    CompanionAction,
    CompanionEvidence,
    CompanionIssue,
    DesignSchemaResult,
    Diagnostic,
    GeneratedFile,
    InspectionResult,
    ProjectAssessmentResult,
    ProjectBlueprint,
    ProjectFile,
    PromptSpec,
    ReadinessResult,
    ResourceSpec,
    SecurityReview,
    ToolSpec,
    TypeDefinition,
    ValidationProfile,
    ValidationResult,
    VerificationCheck,
    VerificationOutcome,
    VerificationPlanResult,
)
from .templates import generate_project
from .validation import review_project_security, validate_project

FASTMCP_REFERENCES = (
    "https://gofastmcp.com/servers/server",
    "https://gofastmcp.com/servers/tools",
    "https://gofastmcp.com/servers/resources",
    "https://gofastmcp.com/servers/prompts",
    "https://gofastmcp.com/servers/testing",
)
MCP_REFERENCE = "https://modelcontextprotocol.io/specification/2026-07-28/server"
INSPECTOR_REFERENCE = "https://modelcontextprotocol.io/docs/2026-07-28/tools/inspector"
CONFORMANCE_REFERENCE = "https://github.com/modelcontextprotocol/conformance"
OPENCODE_REFERENCES = {
    "opencode-v1": "https://opencode.ai/docs/mcp-servers",
    "opencode-v2": "https://opencode.ai/v2/docs/mcp-servers",
}


def _issue(
    code: str,
    message: str,
    *,
    path: str | None = None,
    component: tuple[str, str] | None = None,
) -> CompanionIssue:
    """Create one bounded issue with an optional component location."""
    return CompanionIssue(
        code=code,
        message=message,
        path=path,
        component_kind=component[0] if component else None,
        component_name=component[1] if component else None,
    )


def _evidence(check: str, result: str, detail: str) -> CompanionEvidence:
    """Create one evidence statement without embedding command or project output."""
    return CompanionEvidence(check=check, result=result, detail=detail)


def _action(
    action: str,
    description: str,
    *,
    tool: str | None = None,
    command: str | None = None,
) -> CompanionAction:
    """Create one explicit action for the OpenCode caller."""
    return CompanionAction(action=action, description=description, tool=tool, command=command)


def _unique(values: Iterable[str]) -> list[str]:
    """Return strings in first-seen order."""
    return list(dict.fromkeys(values))


def _component_items(
    blueprint: ProjectBlueprint,
) -> list[tuple[str, ToolSpec | ResourceSpec | PromptSpec]]:
    """Return every declared primitive in a deterministic order."""
    return [
        *(("tool", item) for item in blueprint.tools),
        *(("resource", item) for item in blueprint.resources),
        *(("prompt", item) for item in blueprint.prompts),
    ]


def _merged_definitions(
    global_definitions: list[TypeDefinition], local_definitions: list[TypeDefinition]
) -> list[TypeDefinition]:
    """Merge equal declarations and reject conflicting definitions with the same name."""
    merged: dict[str, TypeDefinition] = {item.name: item for item in global_definitions}
    for item in local_definitions:
        existing = merged.get(item.name)
        if existing is not None and existing != item:
            raise ValueError(f"Conflicting type definition: {item.name}")
        merged[item.name] = item
    return list(merged.values())


def _with_project_definitions(specification, blueprint: ProjectBlueprint):
    """Attach project-wide schema declarations to one immutable component input."""
    definitions = _merged_definitions(blueprint.schemas, specification.definitions)
    return specification.model_copy(update={"definitions": definitions})


def _value_matches_type(
    value, annotation: str, definitions: dict[str, TypeDefinition]
) -> bool:
    """Validate one JSON scenario value against the closed blueprint type system."""
    if annotation.startswith("list["):
        item_type = annotation[5:-1]
        return isinstance(value, list) and all(
            _value_matches_type(item, item_type, definitions) for item in value
        )
    if annotation.startswith("dict[str, "):
        item_type = annotation[10:-1]
        return isinstance(value, dict) and all(
            isinstance(key, str) and _value_matches_type(item, item_type, definitions)
            for key, item in value.items()
        )
    simple = {
        "str": lambda item: isinstance(item, str),
        "int": lambda item: type(item) is int,
        "float": lambda item: type(item) in {int, float},
        "bool": lambda item: type(item) is bool,
        "dict": lambda item: isinstance(item, dict),
    }
    if annotation in simple:
        return simple[annotation](value)
    definition = definitions.get(annotation)
    if definition is None:
        return False
    if definition.kind == "enum":
        return isinstance(value, str) and value in definition.values
    if not isinstance(value, dict):
        return False
    fields = {field.name: field for field in definition.fields}
    supplied = set(value)
    required = {field.name for field in definition.fields if field.required}
    if required - supplied or supplied - fields.keys():
        return False
    return all(
        (item is None and not fields[name].required)
        or _value_matches_type(item, fields[name].type, definitions)
        for name, item in value.items()
    )


def _expectation_matches_type(expectation, annotation: str,
                              definitions: dict[str, TypeDefinition]) -> bool:
    """Validate a top-level result expectation against a component return type."""
    if expectation.path != ["data"]:
        return True
    if expectation.operator == "equals":
        return _value_matches_type(expectation.value, annotation, definitions)
    if annotation == "str":
        return isinstance(expectation.value, str)
    if annotation.startswith("list["):
        return _value_matches_type(expectation.value, annotation[5:-1], definitions)
    if annotation.startswith("dict[str, "):
        return isinstance(expectation.value, str)
    return False


def get_design_schema() -> DesignSchemaResult:
    """Return the full bounded blueprint contract and the companion workflow."""
    return DesignSchemaResult(
        status="ok",
        blueprint_schema=ProjectBlueprint.model_json_schema(),
        validation_profiles=["framework", "recommended", "strict"],
        workflow=[
            "discover official documentation",
            "collect missing blueprint decisions",
            "validate the blueprint",
            "generate files in memory",
            "let OpenCode write and implement business logic",
            "assess the complete file set",
            "let OpenCode execute the verification plan",
            "assess readiness from static and reported runtime evidence",
        ],
        evidence=[
            _evidence(
                "stateless_contract",
                "observed",
                "The schema accepts decisions only; it has no session, filesystem, execution, or LLM field.",
            )
        ],
        references=[*FASTMCP_REFERENCES, MCP_REFERENCE, *OPENCODE_REFERENCES.values()],
        next_actions=[
            _action(
                "create_blueprint",
                "Collect every required decision and call validate_blueprint.",
                tool="validate_blueprint",
            )
        ],
    )


def validate_blueprint(blueprint: ProjectBlueprint) -> BlueprintValidationResult:
    """Validate cross-field design decisions without writing or executing anything."""
    blocking: list[CompanionIssue] = []
    warnings: list[CompanionIssue] = []
    components = _component_items(blueprint)
    component_keys = {(kind, item.name) for kind, item in components}

    if not components:
        blocking.append(
            _issue("missing_component", "Declare at least one tool, resource, or prompt.")
        )

    for kind in ("tool", "resource", "prompt"):
        names = [item.name for item_kind, item in components if item_kind == kind]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        for name in duplicates:
            blocking.append(
                _issue(
                    "duplicate_component",
                    f"The {kind} name {name!r} is declared more than once.",
                    component=(kind, name),
                )
            )

    generators: dict[str, Callable] = {
        "tool": generate_tool,
        "resource": generate_resource,
        "prompt": generate_prompt,
    }
    for kind, specification in components:
        try:
            generators[kind](_with_project_definitions(specification, blueprint))
        except (KeyError, TypeError, ValueError) as exc:
            blocking.append(
                _issue(
                    "invalid_component_contract",
                    f"The {kind} {specification.name!r} cannot be generated: {exc}",
                    component=(kind, specification.name),
                )
            )

    referenced_contracts = [
        *((item.component_kind, item.component_name, "annotation") for item in blueprint.annotations),
        *((item.component_kind, item.component_name, "error") for item in blueprint.errors),
        *((item.component_kind, item.component_name, "test scenario")
          for item in blueprint.test_scenarios),
    ]
    for kind, name, contract_type in referenced_contracts:
        if (kind, name) not in component_keys:
            blocking.append(
                _issue(
                    "unknown_component_reference",
                    f"The {contract_type} references an undeclared {kind} {name!r}.",
                    component=(kind, name),
                )
            )

    annotated = [(item.component_kind, item.component_name) for item in blueprint.annotations]
    duplicate_annotations = sorted({key for key in annotated if annotated.count(key) > 1})
    for kind, name in duplicate_annotations:
        blocking.append(
            _issue(
                "duplicate_annotations",
                "Declare at most one annotation contract per component.",
                component=(kind, name),
            )
        )
    for annotation in blueprint.annotations:
        component = (annotation.component_kind, annotation.component_name)
        has_hints = any(
            value is not None
            for value in (
                annotation.read_only,
                annotation.destructive,
                annotation.idempotent,
                annotation.open_world,
            )
        )
        if annotation.component_kind != "tool" and has_hints:
            blocking.append(
                _issue(
                    "unsupported_component_annotations",
                    "This blueprint exposes behavior annotations only for tools.",
                    component=component,
                )
            )
    unannotated_tools = sorted(
        name for kind, name in component_keys if kind == "tool" and (kind, name) not in annotated
    )
    if unannotated_tools:
        warnings.append(
            _issue(
                "missing_tool_annotations",
                "Explicitly decide read-only, destructive, idempotent, and open-world hints for: "
                + ", ".join(unannotated_tools),
            )
        )

    covered = {(item.component_kind, item.component_name) for item in blueprint.test_scenarios}
    for kind, name in sorted(component_keys - covered):
        blocking.append(
            _issue(
                "missing_test_scenario",
                "Declare at least one success or error scenario for this component.",
                component=(kind, name),
            )
        )
    specifications = {(kind, item.name): item for kind, item in components}
    for scenario in blueprint.test_scenarios:
        specification = specifications.get((scenario.component_kind, scenario.component_name))
        if specification is None:
            continue
        parameters = (
            specification.arguments
            if scenario.component_kind == "prompt"
            else specification.parameters
        )
        declared = {item.name for item in parameters}
        required = {item.name for item in parameters if item.required}
        supplied = set(scenario.arguments)
        if missing := sorted(required - supplied):
            blocking.append(
                _issue(
                    "missing_scenario_arguments",
                    "Scenario is missing required arguments: " + ", ".join(missing),
                    component=(scenario.component_kind, scenario.component_name),
                )
            )
        if unknown := sorted(supplied - declared):
            blocking.append(
                _issue(
                    "unknown_scenario_arguments",
                    "Scenario contains undeclared arguments: " + ", ".join(unknown),
                    component=(scenario.component_kind, scenario.component_name),
                )
            )
        try:
            merged_definitions = _merged_definitions(
                blueprint.schemas, specification.definitions
            )
        except ValueError:
            # The component-generation pass above already reports the conflicting
            # declaration as an invalid_component_contract.
            continue
        definitions = {item.name: item for item in merged_definitions}
        by_parameter = {item.name: item for item in parameters}
        for argument, value in scenario.arguments.items():
            parameter = by_parameter.get(argument)
            if parameter is None or (value is None and not parameter.required):
                continue
            if not _value_matches_type(value, parameter.type, definitions):
                blocking.append(
                    _issue(
                        "scenario_argument_type_mismatch",
                        f"Scenario argument {argument!r} does not match {parameter.type!r}.",
                        component=(scenario.component_kind, scenario.component_name),
                    )
                )
        if scenario.result_expectation is not None:
            return_type = "str" if scenario.component_kind == "prompt" else specification.return_type
            if not _expectation_matches_type(
                scenario.result_expectation, return_type, definitions
            ):
                blocking.append(
                    _issue(
                        "scenario_result_type_mismatch",
                        "The structured result expectation does not match the component "
                        f"return type {return_type!r}.",
                        component=(scenario.component_kind, scenario.component_name),
                    )
                )
    error_keys = [
        (item.component_kind, item.component_name, item.code) for item in blueprint.errors
    ]
    for kind, name, code in sorted({key for key in error_keys if error_keys.count(key) > 1}):
        blocking.append(_issue(
            "duplicate_error_contract",
            f"Error code {code!r} is declared more than once for this component.",
            component=(kind, name),
        ))
    declared_errors = set(error_keys)
    covered_errors: set[tuple[str, str, str]] = set()
    for scenario in blueprint.test_scenarios:
        if scenario.expected_outcome != "error" or scenario.error_code is None:
            continue
        key = (scenario.component_kind, scenario.component_name, scenario.error_code)
        if key not in declared_errors:
            blocking.append(_issue(
                "unknown_scenario_error",
                f"Scenario references undeclared error code {scenario.error_code!r}.",
                component=(scenario.component_kind, scenario.component_name),
            ))
        else:
            covered_errors.add(key)
    for kind, name, code in sorted(declared_errors - covered_errors):
        blocking.append(_issue(
            "missing_error_test_scenario",
            f"Error contract {code!r} needs its own error test scenario.",
            component=(kind, name),
        ))

    environment_variables = [item.environment_variable for item in blueprint.secrets]
    for variable in sorted({item for item in environment_variables if environment_variables.count(item) > 1}):
        blocking.append(
            _issue("duplicate_secret_variable", f"Secret environment variable {variable!r} is reused.")
        )
    secret_tokens = {item.name.lower() for item in blueprint.secrets}
    secret_tokens.update({"secret", "password", "passwd", "api_key", "token"})
    for kind, specification in components:
        parameters = (
            specification.arguments if kind == "prompt" else specification.parameters
        )
        for parameter in parameters:
            lowered = parameter.name.lower()
            if lowered in secret_tokens or any(token in lowered for token in (
                "secret", "password", "passwd", "api_key", "token"
            )):
                blocking.append(
                    _issue(
                        "secret_in_mcp_input",
                        f"Parameter {parameter.name!r} appears to expose a secret; use server configuration.",
                        component=(kind, specification.name),
                    )
                )

    references = [*FASTMCP_REFERENCES, MCP_REFERENCE, OPENCODE_REFERENCES[blueprint.client_profile]]
    valid = not blocking
    return BlueprintValidationResult(
        status="valid" if valid else "invalid",
        valid=valid,
        component_counts={
            "tool": len(blueprint.tools),
            "resource": len(blueprint.resources),
            "prompt": len(blueprint.prompts),
        },
        blocking_issues=blocking,
        warnings=warnings,
        evidence=[
            _evidence(
                "blueprint_contract",
                "passed" if valid else "failed",
                f"Checked {len(components)} component contracts and their referenced decisions.",
            ),
            _evidence(
                "server_side_execution",
                "not_run",
                "Validation is deterministic and does not import or execute generated code.",
            ),
        ],
        references=_unique(references),
        next_actions=[
            _action(
                "resolve_blueprint_issues",
                "Resolve every blocking issue and validate the complete blueprint again.",
                tool="validate_blueprint",
            )
        ] if not valid else [
            _action(
                "generate_project",
                "Generate the project files in memory from this validated blueprint.",
                tool="generate_from_blueprint",
            )
        ],
    )


def _register_component(file_map: dict[str, str], kind: str, name: str) -> None:
    """Add an explicit package import for one newly generated component."""
    package = f"{kind}s"
    init_path = f"app/{package}/__init__.py"
    current = file_map.get(init_path, f'"""Explicitly register {package}."""\n')
    statement = f"from . import {name} as {name}"
    if statement not in current:
        separator = "" if current.endswith("\n") else "\n"
        current = f"{current}{separator}\n{statement}\n"
    file_map[init_path] = current


def _apply_annotations(
    content: str,
    kind: str,
    annotation,
) -> str:
    """Add validated FastMCP annotations to one generated single-line decorator."""
    names = {
        "read_only": "readOnlyHint",
        "destructive": "destructiveHint",
        "idempotent": "idempotentHint",
        "open_world": "openWorldHint",
    }
    values = {
        names[field]: getattr(annotation, field)
        for field in names
        if kind == "tool" and getattr(annotation, field) is not None
    }
    if not values:
        return content
    marker = f"@mcp.{kind}("
    lines = content.splitlines(keepends=True)
    for index, line in enumerate(lines):
        if line.startswith(marker) and line.rstrip().endswith(")"):
            newline = "\n" if line.endswith("\n") else ""
            decorator = line.rstrip("\r\n")
            lines[index] = f"{decorator[:-1]}, annotations={values!r}){newline}"
            return "".join(lines)
    raise ValueError(f"Generated {kind} decorator could not be annotated")


def _scenario_invocation(blueprint: ProjectBlueprint, scenario) -> str:
    """Render a bounded in-memory client call for one declared scenario."""
    specifications = {
        (kind, item.name): item for kind, item in _component_items(blueprint)
    }
    specification = specifications[(scenario.component_kind, scenario.component_name)]
    if scenario.component_kind == "tool":
        return f"await client.call_tool({scenario.component_name!r}, {scenario.arguments!r})"
    if scenario.component_kind == "prompt":
        return f"await client.get_prompt({scenario.component_name!r}, {scenario.arguments!r})"
    uri = specification.uri
    for name, value in scenario.arguments.items():
        uri = uri.replace(f"{{{name}}}", str(value))
    return f"await client.read_resource({uri!r})"


def _set_literal(values: list[str]) -> str:
    """Render a deterministic non-empty set literal accepted by Ruff."""
    return "{" + ", ".join(repr(value) for value in values) + "}"


def _blueprint_smoke_test(blueprint: ProjectBlueprint) -> str:
    """Generate discovery checks and deliberately incomplete scenario assertions."""
    tool_names = [item.name for item in blueprint.tools]
    resource_uris = [item.uri for item in blueprint.resources]
    prompt_names = [item.name for item in blueprint.prompts]
    discovery = []
    if tool_names:
        discovery.extend([
            "        tools = await client.list_tools()",
            f"        assert {_set_literal(tool_names)} == {{item.name for item in tools}}",
        ])
    if resource_uris:
        discovery.extend([
            "        resources = await client.list_resources()",
            "        templates = await client.list_resource_templates()",
            "        resource_uris = {str(item.uri) for item in resources}",
            "        resource_uris.update(str(item.uri_template) for item in templates)",
            f"        assert {_set_literal(resource_uris)} == resource_uris",
        ])
    if prompt_names:
        discovery.extend([
            "        prompts = await client.list_prompts()",
            f"        assert {_set_literal(prompt_names)} == {{item.name for item in prompts}}",
        ])
    scenarios: list[str] = []
    errors = {
        (item.component_kind, item.component_name, item.code): item
        for item in blueprint.errors
    }
    for scenario in blueprint.test_scenarios:
        expectations = " | ".join(item.replace("\n", " ") for item in scenario.assertions)
        error_setup = ""
        error_suffix = ""
        result_setup = ""
        result_suffix = ""
        if scenario.result_expectation is not None:
            result_setup = (
                f"        expected_result_path = {scenario.result_expectation.path!r}\n"
                f"        expected_operator = {scenario.result_expectation.operator!r}\n"
                f"        expected_value = {scenario.result_expectation.value!r}\n"
            )
            result_suffix = (
                ' + f"; result expectation {expected_result_path} "'
                ' + f"{expected_operator} {expected_value!r}"'
            )
        if scenario.error_code is not None:
            contract = errors[
                (scenario.component_kind, scenario.component_name, scenario.error_code)
            ]
            error_setup = (
                f"        expected_error_code = {contract.code!r}\n"
                f"        expected_error_message = {contract.message!r}\n"
                f"        expected_exception = {scenario.expected_exception!r}\n"
            )
            error_suffix = (
                ' + f"; expected {expected_exception} {expected_error_code}: "'
                ' + expected_error_message'
            )
        scenarios.append(f'''

@pytest.mark.asyncio
async def test_{scenario.name}_contract_is_implemented():
    """Exercise the declared scenario; OpenCode must replace the final placeholder."""
    async with Client(mcp) as client:
{error_setup}{result_setup}        result = {_scenario_invocation(blueprint, scenario)}
        pytest.fail(
            "TODO: implement exact {scenario.expected_outcome} assertions for "
            + {expectations!r}
            + f"; got {{result!r}}"
            {result_suffix}
            {error_suffix}
        )
''')
    return f'''"""Smoke-test the exact blueprint primitives through an in-process client."""

import pytest
from fastmcp import Client

from app.server import mcp


@pytest.mark.asyncio
async def test_blueprint_discovery():
    """Discover exactly the public primitives declared by the blueprint."""
    async with Client(mcp) as client:
{chr(10).join(discovery)}
{''.join(scenarios)}'''


def generate_from_blueprint(blueprint: ProjectBlueprint) -> BlueprintGenerationResult:
    """Return a complete project in memory; never persist or execute generated files."""
    validation = validate_blueprint(blueprint)
    if not validation.valid:
        return BlueprintGenerationResult(
            status="blocked",
            blocking_issues=validation.blocking_issues,
            warnings=validation.warnings,
            evidence=validation.evidence,
            references=validation.references,
            next_actions=validation.next_actions,
            files=[],
            generated_components=0,
        )

    project = generate_project(blueprint.name, blueprint.template, blueprint.transport)
    file_map = {item["path"]: item["content"] for item in project["files"]}
    for path in (
        "app/tools/add.py",
        "app/resources/version.py",
        "app/prompts/explain.py",
        "tests/test_server.py",
    ):
        file_map.pop(path, None)
    for package in ("tools", "resources", "prompts"):
        file_map[f"app/{package}/__init__.py"] = (
            f'"""Register {package} modules explicitly."""\n'
        )
    file_map["tests/test_smoke.py"] = _blueprint_smoke_test(blueprint)
    readme = file_map.get("README.md")
    if readme:
        heading = f"# {blueprint.name}\n"
        purpose = f"\n## Purpose\n\n{blueprint.objective}\n"
        file_map["README.md"] = readme.replace(heading, f"{heading}{purpose}", 1)
    warnings = list(validation.warnings)
    references = list(validation.references)
    generators: dict[str, Callable] = {
        "tool": generate_tool,
        "resource": generate_resource,
        "prompt": generate_prompt,
    }
    annotations = {
        (item.component_kind, item.component_name): item for item in blueprint.annotations
    }
    for kind, specification in _component_items(blueprint):
        generated = generators[kind](_with_project_definitions(specification, blueprint))
        for item in generated.files:
            content = item.content
            annotation = annotations.get((kind, specification.name))
            if annotation is not None and item.path.startswith(f"app/{kind}s/"):
                content = _apply_annotations(content, kind, annotation)
            file_map[item.path] = content
        _register_component(file_map, kind, specification.name)
        references.extend(generated.references)
    server_path = "app/server.py"
    if server_path in file_map and _component_items(blueprint):
        imports = "from app import prompts, resources, tools  # noqa: F401"
        if imports not in file_map[server_path]:
            file_map[server_path] = f"{imports}\n{file_map[server_path]}"
    requirements = configuration_requirements(blueprint)
    if requirements:
        file_map["app/config.py"] = render_configuration_module(requirements)
        file_map[server_path] = wire_server(file_map[server_path])
        file_map["compose.yaml"] = wire_compose(file_map["compose.yaml"], requirements)
        file_map[".env.example"] = extend_env_example(
            file_map.get(".env.example", ""), requirements
        )

    generated_size = sum(len(content.encode("utf-8")) for content in file_map.values())
    if len(file_map) > 100 or generated_size > 1_000_000:
        return BlueprintGenerationResult(
            status="blocked",
            files=[],
            generated_components=0,
            blocking_issues=[_issue(
                "generated_project_limit",
                "The blueprint expands beyond the 100-file or 1 MB assessment limit; "
                "split the server into a smaller bounded MCP surface.",
            )],
            warnings=warnings,
            evidence=[_evidence(
                "in_memory_generation",
                "failed",
                "Generation exceeded the bounded assessment envelope before returning files.",
            )],
            references=_unique(references),
            next_actions=[_action(
                "reduce_blueprint_scope",
                "Reduce primitives or repeated schema definitions, then validate again.",
                tool="validate_blueprint",
            )],
        )

    return BlueprintGenerationResult(
        status="incomplete",
        files=[GeneratedFile(path=path, content=content) for path, content in file_map.items()],
        generated_components=len(_component_items(blueprint)),
        warnings=warnings,
        evidence=[
            _evidence(
                "in_memory_generation",
                "passed",
                f"Generated {len(file_map)} files without a server-side write.",
            ),
            _evidence(
                "business_logic",
                "not_run",
                "Component contracts remain intentionally incomplete until OpenCode implements them.",
            ),
        ],
        references=_unique(references),
        next_actions=[
            _action(
                "write_generated_files",
                "Write the returned files into the target project from OpenCode.",
            ),
            _action(
                "implement_business_logic",
                "Replace every TODO with real behavior and contract assertions.",
            ),
            _action(
                "assess_project",
                "Submit the complete in-memory file set for static assessment.",
                tool="assess_project",
            ),
        ],
    )


def _supports_profile(function: Callable) -> bool:
    """Allow mixed-version callers while the legacy API remains supported."""
    return "profile" in inspect.signature(function).parameters


def _validate(files: list[dict], profile: ValidationProfile) -> ValidationResult:
    """Run the current validator and normalize its versioned result."""
    result = (
        validate_project(files, profile=profile)
        if _supports_profile(validate_project)
        else validate_project(files)
    )
    return ValidationResult.model_validate(result)


def _payload_diagnostic(exc: Exception) -> Diagnostic:
    """Map bounded input failures to a stable diagnostic without echoing content."""
    message = str(exc)
    if "1 MB" in message:
        code = "project_size_limit"
        summary = "The submitted project exceeds the 1 MB assessment limit."
    elif "Between 1 and 100" in message:
        code = "project_file_count_limit"
        summary = "Submit between 1 and 100 project files."
    else:
        code = "project_payload_invalid"
        summary = "The submitted project violates the bounded file contract."
    return Diagnostic(
        path="<project>",
        line=1,
        code=code,
        message=summary,
        severity="error",
        suggestion="Reduce or correct the file payload, then assess the complete project again.",
        documentation=MCP_REFERENCE,
    )


def _failed_validation(
    profile: ValidationProfile, diagnostic: Diagnostic
) -> ValidationResult:
    """Return a typed failed validation when analysis cannot safely start."""
    return ValidationResult(
        valid=False,
        diagnostics=[diagnostic],
        executed=False,
        limitations="Static analysis did not run because the bounded input contract failed.",
        profile=profile,
        ready=False,
        readiness_issues=[diagnostic],
    )


def _unavailable_security(diagnostic: Diagnostic) -> SecurityReview:
    """Return a typed unavailable security review for an invalid payload."""
    return SecurityReview(
        passed=False,
        diagnostics=[diagnostic],
        executed=False,
        limitations="Security analysis did not run because the bounded input contract failed.",
    )


def _empty_inspection(validation: ValidationResult) -> InspectionResult:
    """Retain validation evidence when invalid paths prevent project mapping."""
    return InspectionResult(
        components=[],
        pydantic_models=[],
        enums=[],
        dependencies=[],
        declared_fastmcp_version=None,
        architecture={},
        validation=validation,
        executed=False,
    )


def _blocked_assessment(
    profile: ValidationProfile, exc: Exception
) -> ProjectAssessmentResult:
    """Return the shared envelope when a project payload cannot be analyzed."""
    diagnostic = _payload_diagnostic(exc)
    validation = _failed_validation(profile, diagnostic)
    security = _unavailable_security(diagnostic)
    return ProjectAssessmentResult(
        status="blocked",
        inspection=_empty_inspection(validation),
        security=security,
        static_valid=False,
        static_ready=False,
        blocking_issues=[_diagnostic_issue(diagnostic)],
        evidence=[
            _evidence(
                "static_validation",
                "failed",
                "The bounded project payload was rejected before static analysis.",
            )
        ],
        references=[*FASTMCP_REFERENCES, MCP_REFERENCE],
        next_actions=[
            _action(
                "correct_project_payload",
                "Correct the bounded file payload and assess the complete project again.",
                tool="assess_project",
            )
        ],
    )


def _blocked_readiness(
    profile: ValidationProfile,
    verification_results: list[VerificationOutcome],
    exc: Exception,
) -> ReadinessResult:
    """Return a final blocked envelope when submitted files exceed safe bounds."""
    diagnostic = _payload_diagnostic(exc)
    return ReadinessResult(
        status="blocked",
        ready=False,
        validation=_failed_validation(profile, diagnostic),
        security=_unavailable_security(diagnostic),
        verification_results=verification_results,
        blocking_issues=[_diagnostic_issue(diagnostic)],
        evidence=[
            _evidence(
                "static_validation",
                "failed",
                "The bounded project payload was rejected before readiness analysis.",
            )
        ],
        references=[*FASTMCP_REFERENCES, MCP_REFERENCE],
        next_actions=[
            _action(
                "correct_project_payload",
                "Correct the bounded file payload and reassess readiness.",
                tool="assess_readiness",
            )
        ],
    )


def _inspect(files: list[dict], profile: ValidationProfile) -> InspectionResult:
    """Run the current inspector and normalize its versioned result."""
    result = (
        inspect_project(files, profile=profile)
        if _supports_profile(inspect_project)
        else inspect_project(files)
    )
    return InspectionResult.model_validate(result)


def _security(files: list[dict]) -> SecurityReview:
    """Run the bounded static security pass."""
    return SecurityReview.model_validate(review_project_security(files))


def _diagnostic_issue(diagnostic) -> CompanionIssue:
    """Convert a validator diagnostic into the companion issue envelope."""
    return _issue(
        diagnostic.code,
        diagnostic.message,
        path=diagnostic.path,
    )


def _ast_call_name(call: ast.Call) -> str:
    """Return a dotted static call name for readiness evidence matching."""
    parts: list[str] = []
    node = call.func
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def _literal_value(expression: ast.AST, constants: dict[str, object]):
    """Resolve a bounded literal or a local name assigned to one literal."""
    if isinstance(expression, ast.Name) and expression.id in constants:
        return constants[expression.id]
    try:
        return ast.literal_eval(expression)
    except (ValueError, TypeError, SyntaxError):
        return object()


def _result_path(expression: ast.AST, result_names: set[str]) -> tuple[str | int, ...] | None:
    """Return the attribute/subscript path rooted in a scenario call result."""
    if (
        isinstance(expression, ast.Call)
        and isinstance(expression.func, ast.Name)
        and expression.func.id == "str"
        and len(expression.args) == 1
        and not expression.keywords
    ):
        expression = expression.args[0]
    parts: list[str | int] = []
    while isinstance(expression, (ast.Attribute, ast.Subscript)):
        if isinstance(expression, ast.Attribute):
            parts.append(expression.attr)
            expression = expression.value
            continue
        try:
            key = ast.literal_eval(expression.slice)
        except (ValueError, TypeError, SyntaxError):
            return None
        if not isinstance(key, (str, int)):
            return None
        parts.append(key)
        expression = expression.value
    if not isinstance(expression, ast.Name) or expression.id not in result_names:
        return None
    return tuple(reversed(parts))


def _success_expectation_asserted(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
    result_names: set[str],
    scenario,
) -> bool:
    """Match a real result expression against the scenario's structured expectation."""
    expectation = scenario.result_expectation
    if expectation is None:
        return False
    expected_path = tuple(expectation.path)
    constants: dict[str, object] = {}
    for node in ast.walk(function):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)) or node.value is None:
            continue
        try:
            value = ast.literal_eval(node.value)
        except (ValueError, TypeError, SyntaxError):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        constants.update(
            {target.id: value for target in targets if isinstance(target, ast.Name)}
        )

    def matches(expression: ast.AST) -> bool:
        if isinstance(expression, ast.Compare) and len(expression.ops) == 1:
            left = expression.left
            right = expression.comparators[0]
            operator = expression.ops[0]
            if expectation.operator == "equals" and isinstance(operator, ast.Eq):
                candidates = ((left, right), (right, left))
            elif expectation.operator == "contains" and isinstance(operator, ast.In):
                candidates = ((right, left),)
            else:
                return False
            return any(
                _result_path(result_expression, result_names) == expected_path
                and _literal_value(expected_expression, constants) == expectation.value
                for result_expression, expected_expression in candidates
            )
        if not isinstance(expression, ast.Call) or not isinstance(expression.func, ast.Attribute):
            return False
        methods = {
            "equals": {"assertEqual", "assert_equals"},
            "contains": {"assertIn", "assert_in"},
        }[expectation.operator]
        if expression.func.attr not in methods or len(expression.args) < 2:
            return False
        first, second = expression.args[:2]
        candidates = (
            ((first, second), (second, first))
            if expectation.operator == "equals"
            else ((second, first),)
        )
        return any(
            _result_path(result_expression, result_names) == expected_path
            and _literal_value(expected_expression, constants) == expectation.value
            for result_expression, expected_expression in candidates
        )

    return any(
        matches(node.test if isinstance(node, ast.Assert) else node)
        for node in ast.walk(function)
        if isinstance(node, ast.Assert)
        or (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr.startswith("assert")
        )
    )


def _error_expectation_asserted(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
    *,
    matches_call: Callable[[ast.Call], bool],
    pytest_names: set[str],
    exception_names: set[str],
    expected_message: str,
) -> bool:
    """Require the exact call inside pytest.raises with the declared type and message."""
    constants: dict[str, object] = {}
    for node in ast.walk(function):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)) or node.value is None:
            continue
        try:
            value = ast.literal_eval(node.value)
        except (ValueError, TypeError, SyntaxError):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        constants.update(
            {target.id: value for target in targets if isinstance(target, ast.Name)}
        )
    for context in (
        node for node in ast.walk(function) if isinstance(node, (ast.With, ast.AsyncWith))
    ):
        for entry in context.items:
            expression = entry.context_expr
            if (
                not isinstance(expression, ast.Call)
                or not isinstance(expression.func, ast.Attribute)
                or not isinstance(expression.func.value, ast.Name)
                or expression.func.value.id not in pytest_names
                or expression.func.attr != "raises"
                or not expression.args
                or not isinstance(expression.args[0], ast.Name)
                or expression.args[0].id not in exception_names
            ):
                continue
            match = next((item.value for item in expression.keywords if item.arg == "match"), None)
            message = _literal_value(match, constants) if match is not None else None
            if message != expected_message:
                continue
            if any(
                matches_call(call)
                for statement in context.body
                for call in ast.walk(statement)
                if isinstance(call, ast.Call)
            ):
                return True
    return False


def _scenario_function_verified(
    blueprint: ProjectBlueprint,
    scenario,
    files: list[dict],
) -> tuple[bool, bool]:
    """Prove one generated scenario still invokes its exact inputs and asserts the result."""
    expected_name = f"test_{scenario.name}_contract_is_implemented"
    specification = {
        (kind, item.name): item for kind, item in _component_items(blueprint)
    }[(scenario.component_kind, scenario.component_name)]
    method = {
        "tool": "call_tool",
        "resource": "read_resource",
        "prompt": "get_prompt",
    }[scenario.component_kind]
    if scenario.component_kind == "resource":
        expected_target = specification.uri
        for name, value in scenario.arguments.items():
            expected_target = expected_target.replace(f"{{{name}}}", str(value))
    else:
        expected_target = scenario.component_name
    error_contract = next(
        (
            item for item in blueprint.errors
            if item.component_kind == scenario.component_kind
            and item.component_name == scenario.component_name
            and item.code == scenario.error_code
        ),
        None,
    )
    found = False
    for item in files:
        if not item["path"].startswith("tests/") or not item["path"].endswith(".py"):
            continue
        try:
            tree = ast.parse(item["content"])
        except (SyntaxError, ValueError, RecursionError):
            continue
        client_names: set[str] = set()
        server_names: set[str] = set()
        pytest_names: set[str] = set()
        exception_names: set[str] = (
            {scenario.expected_exception}
            if scenario.expected_exception in {"ValueError", "RuntimeError"}
            else set()
        )
        for statement in tree.body:
            if isinstance(statement, ast.Import):
                pytest_names.update(
                    alias.asname or alias.name
                    for alias in statement.names
                    if alias.name == "pytest"
                )
                continue
            if not isinstance(statement, ast.ImportFrom):
                continue
            if statement.module == "fastmcp":
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
            elif statement.module == "fastmcp.exceptions":
                exception_names.update(
                    alias.asname or alias.name
                    for alias in statement.names
                    if alias.name == scenario.expected_exception
                )
        for function in (
            node for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == expected_name
        ):
            found = True
            client_variables: set[str] = set()
            for context in (
                node for node in ast.walk(function)
                if isinstance(node, (ast.With, ast.AsyncWith))
            ):
                for entry in context.items:
                    expression = entry.context_expr
                    if (
                        isinstance(expression, ast.Call)
                        and _ast_call_name(expression) in client_names
                        and expression.args
                        and isinstance(expression.args[0], ast.Name)
                        and expression.args[0].id in server_names
                        and isinstance(entry.optional_vars, ast.Name)
                    ):
                        client_variables.add(entry.optional_vars.id)

            def matches(call: ast.Call) -> bool:
                if not isinstance(call.func, ast.Attribute) or call.func.attr != method:
                    return False
                if (
                    not isinstance(call.func.value, ast.Name)
                    or call.func.value.id not in client_variables
                ):
                    return False
                if not call.args:
                    return False
                try:
                    target = ast.literal_eval(call.args[0])
                except (ValueError, TypeError, SyntaxError):
                    return False
                if target != expected_target:
                    return False
                if scenario.component_kind == "resource":
                    return True
                if len(call.args) < 2:
                    return not scenario.arguments
                try:
                    arguments = ast.literal_eval(call.args[1])
                except (ValueError, TypeError, SyntaxError):
                    return False
                return arguments == scenario.arguments

            result_names: set[str] = set()
            target_calls: list[ast.Call] = []
            for node in ast.walk(function):
                if isinstance(node, ast.Call) and matches(node):
                    target_calls.append(node)
                if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                    continue
                value = node.value
                if value is None or not any(
                    matches(call) for call in ast.walk(value) if isinstance(call, ast.Call)
                ):
                    continue
                assignment_targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                result_names.update(
                    target.id for target in assignment_targets if isinstance(target, ast.Name)
                )
            if not target_calls:
                continue
            if scenario.expected_outcome == "success" and _success_expectation_asserted(
                function, result_names, scenario
            ):
                return True, True
            if (
                scenario.expected_outcome == "error"
                and error_contract is not None
                and _error_expectation_asserted(
                    function,
                    matches_call=matches,
                    pytest_names=pytest_names,
                    exception_names=exception_names,
                    expected_message=error_contract.message,
                )
            ):
                return True, True
    return found, False


def _blueprint_alignment(
    blueprint: ProjectBlueprint,
    inspection: InspectionResult,
    files: list[dict],
) -> list[CompanionIssue]:
    """Require the inspected public MCP surface and typed contracts to match the blueprint."""
    expected = {(kind, item.name): item for kind, item in _component_items(blueprint)}
    discovered = {(item.kind, item.function): item for item in inspection.components}
    issues: list[CompanionIssue] = []
    for kind, name in sorted(expected.keys() - discovered.keys()):
        issues.append(_issue(
            "blueprint_component_missing",
            "The final project does not expose this blueprint component.",
            component=(kind, name),
        ))
    for kind, name in sorted(discovered.keys() - expected.keys()):
        issues.append(_issue(
            "blueprint_component_unexpected",
            "The final project exposes a public component absent from the blueprint.",
            path=discovered[(kind, name)].path,
            component=(kind, name),
        ))
    for key in sorted(expected.keys() & discovered.keys()):
        kind, name = key
        specification = expected[key]
        component = discovered[key]
        parameters = (
            specification.arguments if kind == "prompt" else specification.parameters
        )
        expected_parameters = [item.name for item in parameters]
        if component.parameters != expected_parameters:
            issues.append(_issue(
                "blueprint_parameters_mismatch",
                f"Expected parameters {expected_parameters!r}, found {component.parameters!r}.",
                path=component.path,
                component=key,
            ))
        expected_types = [item.type for item in parameters]
        if component.parameter_types != expected_types:
            issues.append(_issue(
                "blueprint_parameter_types_mismatch",
                f"Expected parameter types {expected_types!r}, found "
                f"{component.parameter_types!r}.",
                path=component.path,
                component=key,
            ))
        expected_required = [item.name for item in parameters if item.required]
        if component.required_parameters != expected_required:
            issues.append(_issue(
                "blueprint_parameter_requiredness_mismatch",
                f"Expected required parameters {expected_required!r}, found "
                f"{component.required_parameters!r}.",
                path=component.path,
                component=key,
            ))
        if component.is_async != specification.is_async:
            issues.append(_issue(
                "blueprint_async_mismatch",
                f"Expected is_async={specification.is_async}, found {component.is_async}.",
                path=component.path,
                component=key,
            ))
        expected_return = "str" if kind == "prompt" else specification.return_type
        if component.return_annotation != expected_return:
            issues.append(_issue(
                "blueprint_return_type_mismatch",
                f"Expected return type {expected_return!r}, found {component.return_annotation!r}.",
                path=component.path,
                component=key,
            ))
        if kind == "resource" and component.name != specification.uri:
            issues.append(_issue(
                "blueprint_resource_uri_mismatch",
                f"Expected resource URI {specification.uri!r}, found {component.name!r}.",
                path=component.path,
                component=key,
            ))
        if kind == "tool":
            annotation = next(
                (
                    item for item in blueprint.annotations
                    if item.component_kind == kind and item.component_name == name
                ),
                None,
            )
            hint_names = {
                "read_only": "readOnlyHint",
                "destructive": "destructiveHint",
                "idempotent": "idempotentHint",
                "open_world": "openWorldHint",
            }
            expected_hints = {
                hint: getattr(annotation, field)
                for field, hint in hint_names.items()
                if annotation is not None and getattr(annotation, field) is not None
            }
            if any(
                component.tool_annotations.get(hint) != value
                for hint, value in expected_hints.items()
            ):
                issues.append(_issue(
                    "blueprint_annotations_mismatch",
                    f"Expected tool annotations {expected_hints!r}, found "
                    f"{component.tool_annotations!r}.",
                    path=component.path,
                    component=key,
                ))

    for scenario in blueprint.test_scenarios:
        found, verified = _scenario_function_verified(blueprint, scenario, files)
        if verified:
            continue
        issues.append(_issue(
            "blueprint_scenario_unverified" if found else "blueprint_scenario_missing",
            (
                "The scenario test does not invoke the declared arguments and assert its exact "
                "outcome/error contract."
                if found else "The final project is missing the generated scenario test."
            ),
            component=(scenario.component_kind, scenario.component_name),
        ))

    expected_definitions: dict[str, TypeDefinition] = {
        item.name: item for item in blueprint.schemas
    }
    for _, specification in _component_items(blueprint):
        expected_definitions.update({item.name: item for item in specification.definitions})
    actual_models: dict[str, list[list[dict]]] = {}
    for model in inspection.pydantic_models:
        actual_models.setdefault(model["name"], []).append(model.get("field_contracts", []))
    actual_enums: dict[str, list[list[str]]] = {}
    for enum in inspection.enums:
        actual_enums.setdefault(enum["name"], []).append(enum.get("values", []))
    for name, definition in sorted(expected_definitions.items()):
        if definition.kind == "enum":
            if list(definition.values) not in actual_enums.get(name, []):
                issues.append(_issue(
                    "blueprint_enum_mismatch",
                    f"No enum {name!r} matches values {definition.values!r}.",
                ))
            continue
        expected_fields = [
            {
                "name": field.name,
                "annotation": field.type,
                "required": field.required,
            }
            for field in definition.fields
        ]
        if expected_fields not in actual_models.get(name, []):
            issues.append(_issue(
                "blueprint_model_mismatch",
                f"No Pydantic model {name!r} matches the blueprint fields.",
            ))

    for code, message, path in configuration_issues(
        files, configuration_requirements(blueprint)
    ):
        issues.append(_issue(code, message, path=path))
    return issues


def assess_project(
    files: list[dict] | list[ProjectFile],
    profile: ValidationProfile = "recommended",
) -> ProjectAssessmentResult:
    """Combine static inspection, validation, and security without importing code."""
    payload = [item.model_dump() if isinstance(item, ProjectFile) else item for item in files]
    try:
        validation = _validate(payload, profile)
        security = _security(payload)
    except (KeyError, TypeError, UnicodeError, ValueError) as exc:
        return _blocked_assessment(profile, exc)
    try:
        inspection = _inspect(payload, profile)
    except ValueError:
        inspection = _empty_inspection(validation)
    blocking: list[CompanionIssue] = []
    warnings: list[CompanionIssue] = []
    seen: set[tuple[str, str, int]] = set()
    readiness_keys = {
        (item.code, item.path, item.line) for item in validation.readiness_issues
    }
    for diagnostic in [*validation.diagnostics, *security.diagnostics]:
        key = (diagnostic.code, diagnostic.path, diagnostic.line)
        if key in seen:
            continue
        seen.add(key)
        issue = _diagnostic_issue(diagnostic)
        if diagnostic.severity == "error" or key in readiness_keys:
            blocking.append(issue)
        else:
            warnings.append(issue)
    if validation.ready and security.passed:
        blocking.append(
            _issue(
                "runtime_verification_missing",
                "Static checks passed, but required build, test, MCP, Docker, and OpenCode checks have not been reported.",
            )
        )
    status = "blocked" if not validation.valid or not security.passed else "incomplete"
    return ProjectAssessmentResult(
        status=status,
        inspection=inspection,
        security=security,
        static_valid=validation.valid and security.passed,
        static_ready=validation.ready and security.passed,
        blocking_issues=blocking,
        warnings=warnings,
        evidence=[
            _evidence(
                "static_validation",
                "passed" if validation.valid else "failed",
                f"Applied the {profile} validation profile without importing submitted files.",
            ),
            _evidence(
                "security_review",
                "passed" if security.passed else "failed",
                "Applied the bounded static security rules without executing submitted code.",
            ),
            _evidence(
                "runtime_verification",
                "not_run",
                "Runtime checks are delegated to OpenCode.",
            ),
        ],
        references=[*FASTMCP_REFERENCES, MCP_REFERENCE],
        next_actions=[
            _action(
                "resolve_static_issues",
                "Fix every static readiness issue and reassess the complete project.",
                tool="assess_project",
            )
        ] if not validation.ready or not security.passed else [
            _action(
                "get_verification_plan",
                "Request the required local execution checks for this blueprint.",
                tool="get_verification_plan",
            )
        ],
    )


def _verification_checks(blueprint: ProjectBlueprint) -> list[VerificationCheck]:
    """Build the ordered, client-executed verification sequence."""
    checks = [
        VerificationCheck(
            check_id="lock",
            category="build",
            command="uv lock",
            success_criteria="uv resolves the declared dependency graph and updates uv.lock successfully.",
        ),
        VerificationCheck(
            check_id="install",
            category="build",
            command="uv sync --locked",
            success_criteria="The locked application and development dependencies install successfully.",
        ),
        VerificationCheck(
            check_id="lint",
            category="lint",
            command="uv run --locked ruff check .",
            success_criteria="Ruff exits successfully without rewriting files.",
        ),
        VerificationCheck(
            check_id="unit_tests",
            category="test",
            command="uv run --locked pytest",
            success_criteria="Every unit and contract test passes; no TODO is accepted as success.",
        ),
        VerificationCheck(
            check_id="mcp_smoke",
            category="mcp",
            command="uv run --locked pytest tests/test_smoke.py",
            success_criteria="The in-memory client discovers every primitive and invokes representative calls.",
        ),
    ]
    if blueprint.transport == "http":
        checks.append(VerificationCheck(
            check_id="http_transport",
            category="transport",
            command="uv run --locked python -m app.server",
            success_criteria=(
                "With the server running, a real MCP client connects to "
                "http://127.0.0.1:8000/mcp, lists primitives, and invokes a representative call."
            ),
        ))
    else:
        checks.append(VerificationCheck(
            check_id="stdio_transport",
            category="transport",
            command="uv run --locked python -m app.server",
            success_criteria=(
                "A real MCP client starts the command over stdio, lists primitives, and invokes a representative call."
            ),
        ))
    checks.extend([
        VerificationCheck(
            check_id="docker_build",
            category="build",
            command="docker compose build",
            success_criteria="The locked project image builds successfully.",
        ),
        VerificationCheck(
            check_id="docker_runtime",
            category="transport",
            command="docker compose up -d --build",
            success_criteria="The container becomes healthy and a real MCP client completes a call.",
        ),
        VerificationCheck(
            check_id="opencode_connection",
            category="client",
            command="opencode mcp list",
            success_criteria="OpenCode reports mcp_builder connected with the selected client profile.",
        ),
        VerificationCheck(
            check_id="opencode_invocation",
            category="client",
            command=(
                'opencode run --agent mcp-companion "Call mcp_builder get_design_schema, '
                'then report only status and schema_version. Do not edit files."'
            ),
            success_criteria=(
                "OpenCode discovers the companion, invokes get_design_schema, and reports "
                "status ok with the current schema version."
            ),
        ),
    ])
    if blueprint.client_profile == "opencode-v2":
        target = (
            "--server-url http://127.0.0.1:8000/mcp --transport http"
            if blueprint.transport == "http"
            else "uv run --locked python -m app.server"
        )
        checks.append(VerificationCheck(
            check_id="mcp_inspector",
            category="mcp",
            command=(
                f"npx -y @modelcontextprotocol/inspector --cli {target} "
                "--method tools/list"
            ),
            success_criteria="The MCP Inspector lists the server tools successfully.",
        ))
        checks.append(VerificationCheck(
            check_id="mcp_conformance",
            category="mcp",
            command=(
                "npx -y @modelcontextprotocol/conformance server --url "
                "http://127.0.0.1:8000/mcp --requirements 2026-07-28"
            ),
            success_criteria="All applicable stable server scenarios pass; exclusions are explicit.",
            required=blueprint.transport == "http",
        ))
    return checks


def get_verification_plan(blueprint: ProjectBlueprint) -> VerificationPlanResult:
    """Return commands for OpenCode to execute; the builder runs none of them."""
    validation = validate_blueprint(blueprint)
    if not validation.valid:
        return VerificationPlanResult(
            status="blocked",
            blocking_issues=validation.blocking_issues,
            warnings=validation.warnings,
            evidence=validation.evidence,
            references=validation.references,
            next_actions=validation.next_actions,
            checks=[],
        )
    checks = _verification_checks(blueprint)
    references = [
        *FASTMCP_REFERENCES,
        MCP_REFERENCE,
        OPENCODE_REFERENCES[blueprint.client_profile],
    ]
    if blueprint.client_profile == "opencode-v2":
        references.extend([INSPECTOR_REFERENCE, CONFORMANCE_REFERENCE])
    return VerificationPlanResult(
        status="ok",
        checks=checks,
        evidence=[
            _evidence(
                "verification_commands",
                "not_run",
                f"Prepared {len(checks)} required checks for OpenCode to execute locally.",
            )
        ],
        references=_unique(references),
        next_actions=[
            _action(
                "execute_verification_plan",
                "Run every required check in order and report one bounded outcome per check.",
            ),
            _action(
                "assess_readiness",
                "Submit the final files and all reported outcomes for a readiness decision.",
                tool="assess_readiness",
            ),
        ],
    )


def assess_readiness(
    blueprint: ProjectBlueprint,
    files: list[dict] | list[ProjectFile],
    verification_results: list[VerificationOutcome],
    profile: ValidationProfile = "recommended",
) -> ReadinessResult:
    """Consolidate static checks and bounded outcomes reported by OpenCode."""
    payload = [item.model_dump() if isinstance(item, ProjectFile) else item for item in files]
    try:
        validation = _validate(payload, profile)
        security = _security(payload)
    except (KeyError, TypeError, UnicodeError, ValueError) as exc:
        return _blocked_readiness(profile, verification_results, exc)
    plan = get_verification_plan(blueprint)
    expected = {item.check_id for item in plan.checks if item.required}
    result_ids = [item.check_id for item in verification_results]
    duplicates = sorted({item for item in result_ids if result_ids.count(item) > 1})
    results = {item.check_id: item for item in verification_results}
    blocking: list[CompanionIssue] = []
    warnings: list[CompanionIssue] = []

    if not plan.checks:
        blocking.extend(plan.blocking_issues)
    try:
        inspection = _inspect(payload, profile)
    except ValueError:
        blocking.append(
            _issue(
                "blueprint_alignment_unavailable",
                "Invalid project paths prevented comparison with the blueprint.",
            )
        )
    else:
        blocking.extend(_blueprint_alignment(blueprint, inspection, payload))
    for diagnostic in validation.readiness_issues:
        blocking.append(_diagnostic_issue(diagnostic))
    if not validation.ready and not validation.readiness_issues:
        blocking.append(
            _issue(
                "static_readiness_incomplete",
                "Static validation did not establish readiness; resolve its diagnostics and reassess.",
            )
        )
    for diagnostic in security.diagnostics:
        blocking.append(_diagnostic_issue(diagnostic))
    for check_id in duplicates:
        blocking.append(
            _issue(
                "duplicate_verification_result",
                f"Verification check {check_id!r} was reported more than once.",
            )
        )
    for check_id in sorted(expected):
        outcome = results.get(check_id)
        if outcome is None or outcome.status == "not_run":
            blocking.append(
                _issue(
                    "verification_not_run",
                    f"Required verification check {check_id!r} has not run.",
                )
            )
        elif outcome.status == "failed":
            blocking.append(
                _issue(
                    "verification_failed",
                    f"Required verification check {check_id!r} failed.",
                )
            )
        elif outcome.exit_code not in {None, 0}:
            blocking.append(
                _issue(
                    "inconsistent_verification_result",
                    f"Check {check_id!r} is marked passed with exit code {outcome.exit_code}.",
                )
            )
    for check_id in sorted(set(results) - expected):
        warnings.append(
            _issue(
                "unexpected_verification_result",
                f"Ignoring outcome for unknown or non-required check {check_id!r}.",
            )
        )

    alignment_failed = any(item.code.startswith("blueprint_") for item in blocking)
    static_failed = not validation.valid or not security.passed or alignment_failed
    execution_failed = any(item.code in {
        "verification_failed", "inconsistent_verification_result",
    } for item in blocking)
    incomplete = any(item.code in {
        "todo_skeleton", "missing_targeted_test", "static_readiness_incomplete",
        "verification_not_run",
    } for item in blocking)
    ready = not blocking and validation.ready and security.passed
    if ready:
        status = "ready"
    elif static_failed or execution_failed:
        status = "blocked"
    else:
        status = "incomplete" if incomplete or blocking else "blocked"

    evidence = [
        _evidence(
            "static_validation",
            "passed" if validation.valid else "failed",
            f"Applied the {profile} profile without executing submitted code.",
        ),
        _evidence(
            "security_review",
            "passed" if security.passed else "failed",
            "Applied bounded static security checks.",
        ),
        _evidence(
            "blueprint_alignment",
            "failed" if alignment_failed else "passed",
            "Compared primitives, typed parameters, models, tool hints, configuration, and URIs.",
        ),
    ]
    for check_id in sorted(expected):
        outcome = results.get(check_id)
        evidence.append(_evidence(
            check_id,
            outcome.status if outcome else "not_run",
            "Outcome reported by OpenCode; MCP Builder did not execute the command.",
        ))

    return ReadinessResult(
        status=status,
        ready=ready,
        validation=validation,
        security=security,
        verification_results=verification_results,
        blocking_issues=blocking,
        warnings=warnings,
        evidence=evidence,
        references=plan.references or [*FASTMCP_REFERENCES, MCP_REFERENCE],
        next_actions=[] if ready else [
            _action(
                "resolve_readiness_blockers",
                "Fix every blocking issue, rerun affected checks, and reassess the final file set.",
                tool="assess_readiness",
            )
        ],
    )
