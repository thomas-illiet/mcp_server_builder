"""Bounded MCP payloads used by deterministic project builders."""

import keyword
import math
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    field_validator,
    model_validator,
)

from mcp_builder import BUILDER_VERSION, FASTMCP_VERSION, SCHEMA_VERSION

SimpleType = Literal[
    "str", "int", "float", "bool", "dict", "list[str]", "list[int]", "list[float]",
    "list[bool]", "dict[str, str]", "dict[str, int]", "dict[str, float]",
    "dict[str, bool]",
]


def _not_python_keyword(value: str) -> str:
    """Reject identifiers that cannot be emitted as Python names."""
    if keyword.iskeyword(value):
        raise ValueError("Python identifiers must not be keywords")
    return value


def _finite_json_value(value: JsonValue) -> JsonValue:
    """Reject non-finite floats recursively so generated JSON remains portable."""
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("JSON values must contain only finite floats")
    if isinstance(value, list):
        for item in value:
            _finite_json_value(item)
    elif isinstance(value, dict):
        for item in value.values():
            _finite_json_value(item)
    return value


PythonIdentifier = Annotated[
    str,
    Field(pattern=r"^[a-z][a-z0-9_]{0,63}$"),
    AfterValidator(_not_python_keyword),
]
FiniteJsonValue = Annotated[JsonValue, AfterValidator(_finite_json_value)]

NamedType = Annotated[
    str,
    Field(pattern=r"^(?:[A-Z][A-Za-z0-9]{0,63}|list\[[A-Z][A-Za-z0-9]{0,63}\])$"),
]
ComponentType = SimpleType | NamedType
EnvironmentVariable = Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9_]{0,127}$")]
ValidationProfile = Literal["framework", "recommended", "strict"]
CompanionStatus = Literal["ok", "valid", "invalid", "ready", "incomplete", "blocked"]


class ComponentParameter(BaseModel):
    """Describe one safe parameter without accepting Python source."""

    model_config = ConfigDict(extra="forbid")

    name: PythonIdentifier
    type: ComponentType
    description: str = Field(min_length=1, max_length=500)
    required: bool = True


class EnumDefinition(BaseModel):
    """Declare a closed string enum usable by generated component contracts."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["enum"] = "enum"
    name: str = Field(pattern=r"^[A-Z][A-Za-z0-9]{0,63}$")
    values: list[Annotated[str, Field(min_length=1, max_length=100)]] = Field(
        min_length=1, max_length=50
    )

    @field_validator("name")
    @classmethod
    def valid_python_name(cls, value: str) -> str:
        """Reject Python constants and keywords that cannot name a generated class."""
        if keyword.iskeyword(value):
            raise ValueError("Type names must be valid non-keyword Python class names")
        return value

    @field_validator("values")
    @classmethod
    def unique_values(cls, values: list[str]) -> list[str]:
        """Reject ambiguous enum declarations while retaining caller order."""
        if len(values) != len(set(values)):
            raise ValueError("Enum values must be unique")
        return values


class ObjectDefinition(BaseModel):
    """Declare a bounded Pydantic object usable by generated component contracts."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["object"] = "object"
    name: str = Field(pattern=r"^[A-Z][A-Za-z0-9]{0,63}$")
    fields: list[ComponentParameter] = Field(min_length=1, max_length=50)

    @field_validator("name")
    @classmethod
    def valid_python_name(cls, value: str) -> str:
        """Reject Python constants and keywords that cannot name a generated class."""
        if keyword.iskeyword(value):
            raise ValueError("Type names must be valid non-keyword Python class names")
        return value

    @field_validator("fields")
    @classmethod
    def unique_fields(cls, fields: list[ComponentParameter]) -> list[ComponentParameter]:
        """Reject duplicate object fields before source generation."""
        names = [field.name for field in fields]
        if len(names) != len(set(names)):
            raise ValueError("Object field names must be unique")
        return fields


TypeDefinition = Annotated[EnumDefinition | ObjectDefinition, Field(discriminator="kind")]


class ToolSpec(BaseModel):
    """Structured input for one generated MCP tool."""

    model_config = ConfigDict(extra="forbid")

    name: PythonIdentifier
    description: str = Field(min_length=1, max_length=1000)
    parameters: list[ComponentParameter] = Field(default_factory=list, max_length=30)
    return_type: ComponentType
    is_async: bool = False
    definitions: list[TypeDefinition] = Field(default_factory=list, max_length=30)


class ResourceSpec(BaseModel):
    """Structured input for one generated MCP resource."""

    model_config = ConfigDict(extra="forbid")

    name: PythonIdentifier
    uri: str = Field(min_length=3, max_length=500)
    parameters: list[ComponentParameter] = Field(default_factory=list, max_length=20)
    return_type: ComponentType
    is_async: bool = False
    definitions: list[TypeDefinition] = Field(default_factory=list, max_length=30)


class PromptSpec(BaseModel):
    """Structured input for one generated MCP prompt."""

    model_config = ConfigDict(extra="forbid")

    name: PythonIdentifier
    description: str = Field(min_length=1, max_length=1000)
    arguments: list[ComponentParameter] = Field(default_factory=list, max_length=20)
    is_async: bool = False
    definitions: list[TypeDefinition] = Field(default_factory=list, max_length=30)


class ComponentAnnotationSpec(BaseModel):
    """Record intentional MCP behavior hints for one named component."""

    model_config = ConfigDict(extra="forbid")

    component_kind: Literal["tool", "resource", "prompt"]
    component_name: PythonIdentifier
    read_only: bool | None = None
    destructive: bool | None = None
    idempotent: bool | None = None
    open_world: bool | None = None


class SecretSpec(BaseModel):
    """Describe a server-side secret without ever accepting its value."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=64)
    environment_variable: EnvironmentVariable
    description: str = Field(min_length=1, max_length=500)
    required: bool = True


class DataSourceSpec(BaseModel):
    """Describe an external dependency needed by the generated server."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=64)
    kind: Literal["api", "database", "filesystem", "http", "memory", "other"]
    description: str = Field(min_length=1, max_length=1000)
    read_only: bool = True
    configuration_keys: list[EnvironmentVariable] = Field(
        default_factory=list, max_length=30
    )


class ErrorContract(BaseModel):
    """Describe one user-visible failure contract for a component."""

    model_config = ConfigDict(extra="forbid")

    component_kind: Literal["tool", "resource", "prompt"]
    component_name: PythonIdentifier
    code: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    condition: str = Field(min_length=1, max_length=1000)
    message: str = Field(min_length=1, max_length=1000)


class ScenarioResultExpectation(BaseModel):
    """Describe one machine-checkable assertion against a client-call result."""

    model_config = ConfigDict(extra="forbid")

    path: list[
        Annotated[str, Field(min_length=1, max_length=64)]
        | Annotated[int, Field(ge=0, le=10_000)]
    ] = Field(default_factory=lambda: ["data"], min_length=1, max_length=20)
    operator: Literal["equals", "contains"]
    value: FiniteJsonValue


class TestScenario(BaseModel):
    """Describe a contract test OpenCode must turn into executable assertions."""

    model_config = ConfigDict(extra="forbid")

    name: PythonIdentifier
    component_kind: Literal["tool", "resource", "prompt"]
    component_name: PythonIdentifier
    description: str = Field(min_length=1, max_length=1000)
    arguments: dict[str, FiniteJsonValue] = Field(default_factory=dict, max_length=50)
    expected_outcome: Literal["success", "error"]
    error_code: str | None = Field(
        default=None,
        pattern=r"^[a-z][a-z0-9_]{0,63}$",
    )
    expected_exception: Literal["ToolError", "ValueError", "RuntimeError"] | None = None
    result_expectation: ScenarioResultExpectation | None = None
    assertions: list[Annotated[str, Field(min_length=1, max_length=500)]] = Field(
        min_length=1, max_length=20
    )

    @model_validator(mode="after")
    def error_outcome_has_code(self) -> "TestScenario":
        """Link error scenarios explicitly to one declared error contract."""
        if self.expected_outcome == "error" and self.error_code is None:
            raise ValueError("Error scenarios require error_code")
        if self.expected_outcome == "success" and self.error_code is not None:
            raise ValueError("Success scenarios cannot declare error_code")
        if self.expected_outcome == "success" and self.result_expectation is None:
            raise ValueError("Success scenarios require result_expectation")
        if self.expected_outcome == "success" and self.expected_exception is not None:
            raise ValueError("Success scenarios cannot declare expected_exception")
        if self.expected_outcome == "error" and self.expected_exception is None:
            raise ValueError("Error scenarios require expected_exception")
        if self.expected_outcome == "error" and self.result_expectation is not None:
            raise ValueError("Error scenarios cannot declare result_expectation")
        return self


class ProjectBlueprint(BaseModel):
    """Complete, stateless design contract for one FastMCP project."""

    model_config = ConfigDict(extra="forbid")

    name: PythonIdentifier
    objective: str = Field(min_length=10, max_length=2000)
    template: Literal["minimal", "structured"] = "structured"
    transport: Literal["http", "stdio"] = "http"
    client_profile: Literal["opencode-v1", "opencode-v2"] = "opencode-v1"
    tools: list[ToolSpec] = Field(default_factory=list, max_length=50)
    resources: list[ResourceSpec] = Field(default_factory=list, max_length=50)
    prompts: list[PromptSpec] = Field(default_factory=list, max_length=50)
    schemas: list[TypeDefinition] = Field(default_factory=list, max_length=50)
    annotations: list[ComponentAnnotationSpec] = Field(default_factory=list, max_length=150)
    secrets: list[SecretSpec] = Field(default_factory=list, max_length=50)
    data_sources: list[DataSourceSpec] = Field(default_factory=list, max_length=50)
    errors: list[ErrorContract] = Field(default_factory=list, max_length=100)
    test_scenarios: list[TestScenario] = Field(default_factory=list, max_length=200)

    @field_validator("schemas")
    @classmethod
    def unique_schema_names(cls, schemas: list[TypeDefinition]) -> list[TypeDefinition]:
        """Reject ambiguous project-wide model names."""
        names = [schema.name for schema in schemas]
        if len(names) != len(set(names)):
            raise ValueError("Project schema names must be unique")
        return schemas

    @model_validator(mode="after")
    def unique_named_contracts(self) -> "ProjectBlueprint":
        """Reject duplicate names where the wire identity would be ambiguous."""
        if len(self.tools) + len(self.resources) + len(self.prompts) > 40:
            raise ValueError(
                "A blueprint is limited to 40 total primitives so its generated files "
                "remain assessable in one request"
            )
        for label, items in (
            ("secret", self.secrets),
            ("data source", self.data_sources),
            ("test scenario", self.test_scenarios),
        ):
            names = [item.name for item in items]
            if len(names) != len(set(names)):
                raise ValueError(f"Duplicate {label} name")
        return self


class GeneratedFile(BaseModel):
    """One in-memory generated file."""

    path: str
    content: str


class GenerationResult(BaseModel):
    """Common envelope returned by every component generator."""

    schema_version: str = SCHEMA_VERSION
    generator_version: str = BUILDER_VERSION
    fastmcp_version: str = FASTMCP_VERSION
    files: list[GeneratedFile]
    warnings: list[str]
    assumptions: list[str]
    references: list[str]


class ProjectFile(BaseModel):
    """Bounded in-memory file payload for static validation; never persisted by the server."""

    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1, max_length=240)
    content: str = Field(max_length=1_000_000)


class Diagnostic(BaseModel):
    """One stable, located and repairable static-analysis diagnostic."""

    path: str
    line: int = Field(ge=1)
    code: str
    message: str
    severity: Literal["warning", "error"]
    suggestion: str
    documentation: str


class ValidationResult(BaseModel):
    """Versioned result of bounded static project validation."""

    schema_version: str = SCHEMA_VERSION
    generator_version: str = BUILDER_VERSION
    fastmcp_version: str = FASTMCP_VERSION
    valid: bool
    diagnostics: list[Diagnostic]
    executed: bool
    limitations: str
    profile: ValidationProfile = "recommended"
    ready: bool = False
    readiness_issues: list[Diagnostic] = Field(default_factory=list)


class ComponentInspection(BaseModel):
    """Static description of one discovered FastMCP component."""

    kind: Literal["tool", "resource", "prompt"]
    name: str
    function: str
    path: str
    line: int
    is_async: bool
    parameters: list[str]
    parameter_types: list[str | None] = Field(default_factory=list)
    required_parameters: list[str] = Field(default_factory=list)
    return_annotation: str | None
    exported: bool
    targeted_test: bool
    tool_annotations: dict[str, bool] = Field(default_factory=dict)


class InspectionResult(BaseModel):
    """Versioned project map produced without importing submitted files."""

    schema_version: str = SCHEMA_VERSION
    generator_version: str = BUILDER_VERSION
    fastmcp_version: str = FASTMCP_VERSION
    components: list[ComponentInspection]
    pydantic_models: list[dict]
    enums: list[dict] = Field(default_factory=list)
    dependencies: list[str]
    declared_fastmcp_version: str | None
    architecture: dict
    validation: ValidationResult
    executed: bool = False


class SecurityReview(BaseModel):
    """Focused static security findings for submitted FastMCP components."""

    schema_version: str = SCHEMA_VERSION
    generator_version: str = BUILDER_VERSION
    fastmcp_version: str = FASTMCP_VERSION
    passed: bool
    diagnostics: list[Diagnostic]
    executed: bool = False
    limitations: str


class PatchChange(BaseModel):
    """One guarded in-memory file change proposed to the caller."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    path: str
    operation: Literal["create", "replace"]
    content: str
    original_sha256: str | None
    reason: str


class PatchConflict(BaseModel):
    """Describe an existing file that a generated skeleton must not replace."""

    path: str
    reason: str
    original_sha256: str


class PatchProposal(BaseModel):
    """Versioned patch proposal; the service never applies these changes."""

    schema_version: str = SCHEMA_VERSION
    generator_version: str = BUILDER_VERSION
    fastmcp_version: str = FASTMCP_VERSION
    changes: list[PatchChange]
    warnings: list[str]
    assumptions: list[str]
    references: list[str]
    conflicts: list[PatchConflict] = Field(default_factory=list)
    executed: bool = False


class CompanionIssue(BaseModel):
    """One stable issue OpenCode can locate and act upon."""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    message: str = Field(min_length=1, max_length=2000)
    path: str | None = Field(default=None, max_length=240)
    component_kind: Literal["tool", "resource", "prompt"] | None = None
    component_name: str | None = Field(default=None, max_length=64)


class CompanionEvidence(BaseModel):
    """Bounded evidence statement without retaining project or command output."""

    model_config = ConfigDict(extra="forbid")

    check: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    result: Literal["passed", "failed", "not_run", "observed"]
    detail: str = Field(min_length=1, max_length=1000)


class CompanionAction(BaseModel):
    """One deterministic next step for the OpenCode agent."""

    model_config = ConfigDict(extra="forbid")

    action: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    description: str = Field(min_length=1, max_length=1000)
    tool: str | None = Field(default=None, max_length=100)
    command: str | None = Field(default=None, max_length=2000)


class CompanionEnvelope(BaseModel):
    """Common versioned response contract shared by all companion facades."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = SCHEMA_VERSION
    generator_version: str = BUILDER_VERSION
    fastmcp_version: str = FASTMCP_VERSION
    status: CompanionStatus
    blocking_issues: list[CompanionIssue] = Field(default_factory=list)
    warnings: list[CompanionIssue] = Field(default_factory=list)
    evidence: list[CompanionEvidence] = Field(default_factory=list)
    references: list[str] = Field(default_factory=list)
    next_actions: list[CompanionAction] = Field(default_factory=list)


class DesignSchemaResult(CompanionEnvelope):
    """Machine-readable decisions and workflow required before generation."""

    blueprint_schema: dict[str, JsonValue]
    validation_profiles: list[ValidationProfile]
    workflow: list[str]


class BlueprintValidationResult(CompanionEnvelope):
    """Semantic validation result for a syntactically valid blueprint."""

    valid: bool
    component_counts: dict[str, int]


class BlueprintGenerationResult(CompanionEnvelope):
    """In-memory generated project; the builder never writes these files."""

    files: list[GeneratedFile]
    generated_components: int
    executed: bool = False


class ProjectAssessmentResult(CompanionEnvelope):
    """Combined static architecture, validation, and security assessment."""

    inspection: InspectionResult
    security: SecurityReview
    static_valid: bool
    static_ready: bool
    executed: bool = False


class VerificationCheck(BaseModel):
    """One command or interactive check that OpenCode must execute."""

    model_config = ConfigDict(extra="forbid")

    check_id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    category: Literal["build", "lint", "test", "mcp", "transport", "client"]
    command: str = Field(min_length=1, max_length=2000)
    success_criteria: str = Field(min_length=1, max_length=1000)
    required: bool = True


class VerificationPlanResult(CompanionEnvelope):
    """Ordered execution plan returned to, but never run by, OpenCode."""

    checks: list[VerificationCheck]
    executed: bool = False


class VerificationOutcome(BaseModel):
    """Bounded command outcome reported by OpenCode after local execution."""

    model_config = ConfigDict(extra="forbid")

    check_id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    status: Literal["passed", "failed", "not_run"]
    exit_code: int | None = None


class ReadinessResult(CompanionEnvelope):
    """Final readiness decision combining static checks with reported execution."""

    ready: bool
    validation: ValidationResult
    security: SecurityReview
    verification_results: list[VerificationOutcome]
    executed: bool = False
