"""Canonical architecture and safety guide embedded in generated projects."""

from mcp_builder import BUILDER_VERSION, FASTMCP_VERSION, SCHEMA_VERSION

GUIDE = f"""# MCP Builder Guide

This project targets **FastMCP {FASTMCP_VERSION}** exclusively.

## Mandatory MCP Builder workflow

Do not design or generate a FastMCP implementation from memory when the MCP Builder tools are
available. Use the server as the source of truth and follow this sequence:

1. Call `get_doc_status` to confirm the bundled documentation and tested FastMCP version.
2. Call `search_docs` for every relevant API, protocol behavior, security constraint, or design
   decision. Use `read_doc` when a complete page or section is needed. Do not invent an API that
   has not been confirmed by these tools.
3. For a new project, call `list_templates`, then `generate_project`. Use `get_example` for the
   component patterns involved. Do not hand-write boilerplate that a generator can produce.
4. For a new component, call `generate_tool`, `generate_resource`, or `generate_prompt`, followed
   by `generate_component_test` when a focused test is needed.
5. For an existing project, call `inspect_project` before proposing changes. Then call
   `review_project_security` and `validate_project`. Use `propose_project_patch` for guarded
   changes instead of directly replacing existing files.
6. Before declaring the work complete, call `validate_project` again on the final file set and
   resolve every error. Report any warning or limitation that remains.

If a required MCP Builder tool cannot be called, state that limitation explicitly and ask before
falling back to an unverified implementation. Treat tool output as evidence, not as optional
background material.

## Required architecture

- Put tools in `app/tools/`, with exactly one public tool per file.
- Put resources in `app/resources/` and prompts in `app/prompts/`.
- Register every module explicitly from its directory's `__init__.py`; do not use dynamic
  discovery or runtime-generated imports.
- Use typed signatures, precise descriptions, and Pydantic models for complex inputs. Prefer
  structured, typed outputs.

A tool performs an action requested by the model. A resource exposes URI-addressable data. A
prompt provides a reusable message template.

## Errors, security, and annotations

- Report user-correctable errors with `fastmcp.exceptions.ToolError`.
- Never put secrets in arguments, results, or logs.
- Never execute user-supplied code, and validate every path and size.
- Document relevant MCP annotations, including read-only, idempotent, and destructive behavior.
  Declare an annotation only when the implementation actually satisfies it.
- Generated network operations must be asynchronous. Synchronous functions are appropriate for
  short computations and are executed by FastMCP in its thread pool.

## Tests

Write one focused test per component with `fastmcp.Client` and the in-memory server. Verify
discovery, argument validation, structured results, and user-facing errors. Generated skeletons
contain an explicit failing `TODO`: replace it with business logic and adapt the test before
treating the component as functional.

Patch proposals are never applied by the server. Before any client-side write, verify that
`original_sha256` still exactly matches the local file content so a recent change is not
overwritten.

References:

- https://gofastmcp.com/servers/tools
- https://gofastmcp.com/servers/resources
- https://gofastmcp.com/servers/prompts
- https://gofastmcp.com/servers/testing
- https://modelcontextprotocol.io/specification/draft/server/index
"""


def get_builder_guide() -> dict:
    """Return the canonical guide and its machine-readable architecture rules."""
    return {
        "schema_version": SCHEMA_VERSION,
        "generator_version": BUILDER_VERSION,
        "guide": GUIDE,
        "fastmcp_version": FASTMCP_VERSION,
        "required_tool_workflow": [
            {"step": 1, "tools": ["get_doc_status"], "required": True},
            {"step": 2, "tools": ["search_docs", "read_doc"], "required": True},
            {"step": 3, "tools": ["list_templates", "generate_project", "get_example"],
             "required_for": "new_project"},
            {"step": 4, "tools": ["generate_tool", "generate_resource", "generate_prompt",
                                    "generate_component_test"],
             "required_for": "new_component"},
            {"step": 5, "tools": ["inspect_project", "review_project_security",
                                    "validate_project", "propose_project_patch"],
             "required_for": "existing_project"},
            {"step": 6, "tools": ["validate_project"], "required": True},
        ],
        "architecture_rules": [
            "app/tools contains exactly one file per public tool",
            "resources and prompts use their dedicated MCP primitives",
            "components are registered explicitly from package __init__.py files",
            "submitted code is never executed by MCP Builder",
        ],
    }
