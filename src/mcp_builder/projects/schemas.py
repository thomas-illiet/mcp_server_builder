"""Bounded MCP payloads used by deterministic project builders."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from mcp_builder import BUILDER_VERSION, FASTMCP_VERSION, SCHEMA_VERSION

SimpleType = Literal[
    "str", "int", "float", "bool", "dict", "list[str]", "list[int]", "list[float]",
    "list[bool]", "dict[str, str]", "dict[str, int]", "dict[str, float]",
    "dict[str, bool]",
]


class ComponentParameter(BaseModel):
    """Describe one safe parameter without accepting Python source."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=64)
    type: SimpleType
    description: str = Field(min_length=1, max_length=500)
    required: bool = True


class ToolSpec(BaseModel):
    """Structured input for one generated MCP tool."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=64)
    description: str = Field(min_length=1, max_length=1000)
    parameters: list[ComponentParameter] = Field(default_factory=list, max_length=30)
    return_type: SimpleType
    is_async: bool = False


class ResourceSpec(BaseModel):
    """Structured input for one generated MCP resource."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=64)
    uri: str = Field(min_length=3, max_length=500)
    parameters: list[ComponentParameter] = Field(default_factory=list, max_length=20)
    return_type: SimpleType
    is_async: bool = False


class PromptSpec(BaseModel):
    """Structured input for one generated MCP prompt."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=64)
    description: str = Field(min_length=1, max_length=1000)
    arguments: list[ComponentParameter] = Field(default_factory=list, max_length=20)
    is_async: bool = False


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


class ComponentInspection(BaseModel):
    """Static description of one discovered FastMCP component."""

    kind: Literal["tool", "resource", "prompt"]
    name: str
    function: str
    path: str
    line: int
    is_async: bool
    parameters: list[str]
    return_annotation: str | None
    exported: bool
    targeted_test: bool


class InspectionResult(BaseModel):
    """Versioned project map produced without importing submitted files."""

    schema_version: str = SCHEMA_VERSION
    generator_version: str = BUILDER_VERSION
    fastmcp_version: str = FASTMCP_VERSION
    components: list[ComponentInspection]
    pydantic_models: list[dict]
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


class PatchProposal(BaseModel):
    """Versioned patch proposal; the service never applies these changes."""

    schema_version: str = SCHEMA_VERSION
    generator_version: str = BUILDER_VERSION
    fastmcp_version: str = FASTMCP_VERSION
    changes: list[PatchChange]
    warnings: list[str]
    assumptions: list[str]
    references: list[str]
    executed: bool = False
