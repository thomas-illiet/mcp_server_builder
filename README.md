# MCP Builder

MCP Builder is a deterministic FastMCP companion for OpenCode. OpenCode owns the
conversation, repository edits, and command execution; MCP Builder supplies verified
official documentation, bounded design contracts, generated files, static assessment,
and explicit readiness criteria. It does not contain a second LLM, retain project
sessions, write submitted projects, or execute their code.

The initial target is FastMCP Python with OpenCode 1.18.31. The default deployment is
lexical-only, works without an embedding endpoint, and publishes HTTP only on
`127.0.0.1`.

## Companion workflow

The default `companion` tool profile exposes the documentation tools and six high-level
facades:

1. `get_design_schema` returns the bounded `ProjectBlueprint` contract.
2. `validate_blueprint` identifies missing decisions, risks, and references.
3. `generate_from_blueprint` returns files and tests in memory; OpenCode writes them.
4. `assess_project` combines inspection, validation, and security findings.
5. `get_verification_plan` tells OpenCode which checks it must execute.
6. `assess_readiness` returns `ready`, `incomplete`, or `blocked` from the final files
   and the reported check outcomes.

Every facade uses the same versioned fields: `status`, `blocking_issues`, `warnings`,
`evidence`, `references`, and `next_actions`. Readiness requires real business behavior,
no remaining `TODO`, targeted tests, successful lint/tests, MCP discovery, and real
invocation evidence.

Set `MCP_BUILDER_TOOL_PROFILE=advanced` only when direct access to the lower-level
template, component, inspection, patch, and validation tools is useful. Patch proposals
never modify files and report a conflict instead of replacing existing business code
with a generated skeleton.

## Download and version the documentation

Prerequisites are Bash, curl, jq, and sha256sum (Linux or Git Bash on Windows).

```bash
bash scripts/sync-docs.sh
git add documentation
git diff --cached --stat
git commit -m "Update FastMCP and MCP documentation"
```

The human-readable script works from any directory. It deletes `documentation/`, then
downloads only official Markdown referenced by the FastMCP and MCP `llms.txt` indexes:

```text
documentation/
  indexes/fastmcp.txt
  indexes/mcp.txt
  docs/fastmcp/...
  docs/mcp/...
  manifest.json
```

The directory is intentionally tracked by Git. `.gitattributes` prevents Windows
checkout from rewriting bytes covered by the upstream SHA-256 manifest. There is no
lock, staging directory, or backup. A failed run can leave a partial directory without
a complete manifest; rerun the script to reset it. Do not run two synchronizations or
edit the script while it is running.

## Start the local service

The base image builds an immutable SQLite FTS index and needs no API key or embedding
service:

```bash
docker compose build mcp-builder
docker compose up -d --no-build --pull never mcp-builder
```

- MCP endpoint: <http://127.0.0.1:8000/mcp>
- Health endpoint: <http://127.0.0.1:8000/health>
- Activity: `docker compose logs -f mcp-builder`

Compose defaults `MCP_BIND_IP` to `127.0.0.1`. The runtime refuses a non-loopback
publication because this release has no HTTP authentication. Keep the service local;
an intentionally remote deployment needs a separately designed authenticated gateway.

Health returns `ok`, `degraded`, or `unready`. Logs contain tool names, lifecycle,
duration, failure type, and cancellation only. Arguments, results, exception messages,
file contents, and secrets are not logged.

### Optional BGE-M3 semantic search

Lexical search remains available when no embedding endpoint exists. To build and run a
hybrid index, place the credential in an ignored file and use the explicit override:

```bash
export OPENAI_BASE_URL=http://host.docker.internal:11434/v1
export EMBEDDING_MODEL=bge-m3
export OPENAI_API_KEY_FILE_HOST=.openai_api_key
printf '%s' ollama-local > .openai_api_key
docker compose -f compose.yaml -f compose.semantic.yaml build mcp-builder
docker compose -f compose.yaml -f compose.semantic.yaml up -d --no-build mcp-builder
```

For a direct host process, use `http://127.0.0.1:11434/v1`. The credential is mounted as
a Docker secret and is never copied into the image or placed in Compose environment
values. Hybrid search falls back explicitly to lexical results when a configured
endpoint becomes unavailable.

## Configure OpenCode

Start MCP Builder first, then copy one matching profile into the FastMCP project that
OpenCode will edit:

```text
integrations/opencode/v1/   OpenCode 1.18.31 schema
integrations/opencode/v2/   V2 schema and Code Mode
```

For a new V1 project on PowerShell:

```powershell
$Target = 'C:\path\to\fastmcp-project'
Copy-Item integrations\opencode\v1\opencode.json "$Target\opencode.json"
New-Item -ItemType Directory -Force "$Target\.opencode\agents" | Out-Null
Copy-Item integrations\opencode\v1\.opencode\agents\mcp-companion.md `
  "$Target\.opencode\agents\mcp-companion.md"
Set-Location $Target
opencode mcp list
```

If the target already has `opencode.json`, merge the `default_agent` and `mcp_builder`
entries instead of overwriting it. The V1 profile configures a remote server at
`http://127.0.0.1:8000/mcp`, disables OAuth discovery, and uses a 30-second catalog
timeout. The V2 profile nests the server under `mcp.servers`, uses `protocol: "auto"`,
keeps Code Mode enabled, and separates startup, catalog, and execution timeouts.

`mcp-companion` is a primary agent and deliberately declares neither a model nor
permissions, so it inherits the user's OpenCode choices. Its required sequence is:
discover, clarify, validate the blueprint, generate, implement, execute checks, assess,
then declare readiness. It does not depend on MCP sampling, elicitation, or tasks.

References: [OpenCode V1 MCP servers](https://opencode.ai/docs/mcp-servers),
[OpenCode agents](https://opencode.ai/docs/agents), and
[OpenCode V2 MCP servers](https://opencode.ai/v2/docs/mcp-servers).

## Diagnose the environment

The doctor checks the corpus, immutable index when present, Docker engine, loopback
port, optional embedding endpoint, bundled OpenCode profiles, CLI version, and active
MCP connection. Output never includes a credential or remote response body.

```bash
uv sync --locked
uv run --locked mcp-builder doctor
uv run --locked mcp-builder doctor --json
```

`ok` means every required integration passed. `degraded` is reserved for the optional
semantic endpoint because lexical search remains usable; missing Docker, an unhealthy
OpenCode connection, an invalid corpus, or a non-loopback publication are `unready`.
The command exits 2 for `unready`. It also reads only `MCP_BIND_IP` from a local `.env`
so that the diagnosis matches Compose without exposing any other setting.

## Development and acceptance

```bash
uv sync --locked
uv run --locked ruff check src scripts tests
uv run --locked pytest -q
docker compose --profile test build tests
docker compose --profile test run --rm tests
```

The generated-project scenario creates both templates in temporary directories, locks
and installs each environment, runs Ruff and Pytest, then starts the HTTP transport and
performs real MCP discovery and invocation:

```bash
uv run --locked python scripts/test-generated-project.py
# Keep one generated project for inspection:
uv run --locked python scripts/test-generated-project.py \
  --template structured --output artifacts/generated-project
```

The modern OpenCode verification plan additionally requires MCP Inspector and the
[official MCP conformance suite](https://github.com/modelcontextprotocol/conformance).
MCP Builder describes these checks; OpenCode executes them and submits bounded outcomes
to `assess_readiness`.

## Repository layout

```text
src/mcp_builder/
  server.py       HTTP assembly, health, and loopback guard
  doctor.py       human and JSON diagnostics
  tools/          companion and advanced MCP tools
  projects/       blueprints, generation, assessment, and validation
  corpus/         source-manifest verification
  search/         lexical and optional semantic indexing
integrations/     ready-to-copy OpenCode V1 and V2 profiles
scripts/          documentation and end-to-end scenarios
tests/            deterministic unit and contract tests
documentation/    official, manifest-verified documents tracked by Git
```

Useful Make targets include `docs`, `build`, `up`, `down`, `restart`, `logs`, `lint`,
`test`, `test-ollama`, `save`, `load`, and `clean`.
