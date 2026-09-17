# syntax=docker/dockerfile:1
FROM python:3.14.6-slim AS base
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HF_HUB_DISABLE_TELEMETRY=1

FROM base AS dependencies
COPY --from=ghcr.io/astral-sh/uv:0.12.8 /uv /uvx /usr/local/bin/
ENV UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never PATH=/app/.venv/bin:$PATH
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev --no-install-project

FROM dependencies AS model
COPY src/mcp_builder/config/sources.json /model-config.json
# Only the connected build downloads the pinned model; the shell script handles docs only.
RUN python -c "import json; from huggingface_hub import snapshot_download; c=json.load(open('/model-config.json'))['model']; snapshot_download(c['id'], revision=c['revision'], allow_patterns=list(c['files']), local_dir='/model')"

FROM dependencies AS indexer
COPY src/mcp_builder/__init__.py /app/src/mcp_builder/__init__.py
COPY src/mcp_builder/config /app/src/mcp_builder/config
COPY src/mcp_builder/corpus /app/src/mcp_builder/corpus
COPY src/mcp_builder/search /app/src/mcp_builder/search
ENV PYTHONPATH=/app/src HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1

FROM indexer AS documents
ARG INDEX_THREADS=2
COPY documentation /sources
RUN --network=none --mount=type=bind,from=model,source=/model,target=/model \
    python -m mcp_builder.search.index --sources /sources --model /model --output /indexed --threads "$INDEX_THREADS"

FROM dependencies AS application
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev --no-editable

FROM base AS runtime
COPY --from=application /app/.venv /app/.venv
COPY --chown=10001:10001 --from=documents /indexed /data
ENV PATH=/app/.venv/bin:$PATH DOCS_DIR=/data PORT=8000 EMBEDDING_CONCURRENCY=1 EMBEDDING_THREADS=2 \
    MAX_REQUEST_BYTES=2000000 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HOME=/tmp
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=120s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"
CMD ["python", "-m", "mcp_builder.server"]

FROM dependencies AS tests
RUN apt-get update && apt-get install -y --no-install-recommends bash curl jq ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked
COPY tests ./tests
COPY scripts ./scripts
CMD ["uv", "run", "--locked", "--no-sync", "pytest", "-q", "-p", "no:cacheprovider"]

FROM runtime AS final
