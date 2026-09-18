# MCP Builder

FastMCP server: hybrid search (FTS5 + BGE-M3), project generation
and static validation. HTTP `/mcp`, health `/health`, no authentication.

## Download and version the documents

Prerequisites: **Bash, curl, jq and sha256sum** (Linux or Git Bash on Windows).

```bash
bash scripts/sync-docs.sh
git add documentation
git diff --cached --stat
git commit -m "Update FastMCP and MCP documentation"
```

The script works from any directory and downloads only the official `llms.txt`
files and the Markdown they reference:

```text
documentation/
  indexes/fastmcp.txt    Official FastMCP index
  indexes/mcp.txt        Official MCP index
  docs/fastmcp/…         Pages with their official paths
  docs/mcp/…             Protocol pages and versions
  manifest.json         URLs, titles, versions, date and SHA-256
```

This folder is intended for Git. `.gitattributes` preserves the downloaded bytes,
including on Windows checkout. Review the changes before committing.
The documents keep the rights and licenses of their publishers.

Each run deletes the destination folder entirely, then downloads the
documents again, sequentially. No lock, temporary folder or backup is kept.
On error, partial downloads remain without a complete manifest; rerun the
script to start over from scratch. Don't run two synchronisations
simultaneously or synchronise during a build.

An optional first argument selects another destination, including paths with
spaces. The build always uses `documentation/` at the repository root.
`DOCS_CONFIG` lets tests supply local URLs.

## Embedding endpoint

Indexing and semantic searches use an OpenAI-compatible `POST /v1/embeddings`
endpoint. The default model name is `bge-m3`; override `EMBEDDING_MODEL` when a
provider exposes the same model under another identifier such as `BAAI/bge-m3`.
`OPENAI_BASE_URL` must include `/v1`. Write the key to the host file selected by
`OPENAI_API_KEY_FILE_HOST` (default `.openai_api_key`): Compose mounts it as a
BuildKit secret while indexing and as a read-only secret file at runtime. The
file is ignored by Git and Docker. The key, submitted text and returned vectors
are never logged.

For local Ollama on Docker Desktop:

```bash
ollama pull bge-m3
export OPENAI_BASE_URL=http://host.docker.internal:11434/v1
export EMBEDDING_MODEL=bge-m3
printf '%s' ollama-local > .openai_api_key
```

Use `http://127.0.0.1:11434/v1` instead when running the Python commands directly
on the host. The runtime healthcheck verifies the local bundle only; an endpoint
failure affects `semantic` and `hybrid`, while `lexical` remains available.

## Build and start

```bash
docker compose build mcp-builder
docker compose up -d --no-build --pull never mcp-builder
```

The connected build installs dependencies with **uv 0.12.8** and `uv.lock`, then
calls the configured embedding endpoint to build the immutable search index.
No model weights or Hugging Face runtime are included in the image.

## Make targets

`Makefile` wraps the commands above plus local development.
Prerequisites: `make`, `docker` (compose), `uv`, and `bash`/`curl`/`jq` for `docs`.

```bash
make help     # List the targets
make docs     # Download and version the documents (scripts/sync-docs.sh)
make build    # Build the Docker image
make up       # Start the service (no rebuild)
make down     # Stop the service
make restart  # Rebuild then restart
make logs     # Tail the service logs
make lint     # Check style with ruff
make test     # Run the pytest tests
make test-ollama # Test the real local Ollama bge-m3 endpoint explicitly
make save     # Export the image to offline-mcp-builder.tar
make load     # Import offline-mcp-builder.tar
make clean    # Stop and remove the image
make all      # Build then start
```

A Docker build step verifies the documents, calls the embedding endpoint, then
builds SQLite and the NumPy vectors. The final image ships the documentation and
index, runs read-only and contains no model weights. Runtime semantic queries
still call the endpoint. An update requires rebuilding then recreating the
container; synchronisation alone does not modify the running server.

- MCP client: <http://localhost:8000/mcp>
- Health: <http://localhost:8000/health>

Follow client calls with `docker compose logs -f mcp-builder`.
Each tool call logs its name, an identifier, its start, its duration and its
final status (done, error or cancelled). `tools/list` requests are also
logged. Arguments, results and file contents are never logged.
Repeated `Terminating session: None` messages are hidden at INFO level.

`.env` sets the port, listen address, endpoint, model, concurrency and request limits.
Offline transfer: `docker save -o offline-mcp-builder.tar offline-mcp-builder:0.1.0`,
then `docker load -i offline-mcp-builder.tar` on the isolated host.

## Code and tests

```text
src/mcp_builder/
  server.py       Server assembly
  config/         Official sources and pinned model
  tools/          One file per MCP tool
  corpus/         File and manifest verification
  search/         Chunking, embeddings, indexing and search
  projects/       uv templates and static validation
  http/           Request limiting
scripts/          Download and integration scenarios
tests/            Builder tests
Dockerfile        Server and test image builds
documentation/    Official documents tracked in Git
```

```bash
uv sync --locked
uv run --locked ruff check src scripts tests
uv run --locked pytest -q
OPENAI_BASE_URL=http://127.0.0.1:11434/v1 OPENAI_API_KEY=ollama-local \
  EMBEDDING_MODEL=bge-m3 uv run --locked python scripts/test-ollama-embeddings.py
# Shell script test on Linux:
docker compose --profile test build tests
docker compose --profile test run --rm tests
# Builder started: generation -> validation -> tests of the returned project
docker compose --profile test run --rm tests uv run --locked --no-sync python scripts/test-generated-project.py
```

The seven tools: `search_docs`, `read_doc`, `get_doc_status`, `list_templates`,
`generate_project`, `get_example`, `validate_project`. Submitted files are
neither executed nor retained. Generated projects use uv; their owner creates
and versions their `uv.lock` before a locked build.
