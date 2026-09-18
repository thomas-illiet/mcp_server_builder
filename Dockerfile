# syntax=docker/dockerfile:1
FROM python:3.14.6-slim AS base
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

FROM base AS dependencies
COPY --from=ghcr.io/astral-sh/uv:0.12.8 /uv /uvx /usr/local/bin/
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential cargo libssl-dev pkg-config \
    && rm -rf /var/lib/apt/lists/*
ENV UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never UV_NO_BINARY_PACKAGE=cryptography \
    PATH=/app/.venv/bin:$PATH
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev --no-install-project

FROM dependencies AS indexer
COPY src/mcp_builder/__init__.py /app/src/mcp_builder/__init__.py
COPY src/mcp_builder/config /app/src/mcp_builder/config
COPY src/mcp_builder/corpus /app/src/mcp_builder/corpus
COPY src/mcp_builder/search /app/src/mcp_builder/search
ENV PYTHONPATH=/app/src

FROM indexer AS documents
ARG OPENAI_BASE_URL
ARG EMBEDDING_MODEL=bge-m3
COPY documentation /sources
RUN --mount=type=secret,id=openai_api_key,required=true \
    OPENAI_API_KEY_FILE=/run/secrets/openai_api_key \
    OPENAI_BASE_URL="$OPENAI_BASE_URL" EMBEDDING_MODEL="$EMBEDDING_MODEL" \
    python -m mcp_builder.search.index --sources /sources --output /indexed

FROM dependencies AS application
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev --no-editable

FROM base AS runtime
COPY --from=application /app/.venv /app/.venv
COPY --chown=10001:10001 --from=documents /indexed /data
RUN mkdir -p /run/secrets && touch /run/secrets/openai_api_key \
    && chown -R 10001:10001 /run/secrets
ENV PATH=/app/.venv/bin:$PATH DOCS_DIR=/data PORT=8000 EMBEDDING_CONCURRENCY=1 \
    EMBEDDING_MODEL=bge-m3 EMBEDDING_TIMEOUT=60 OPENAI_API_KEY_FILE=/run/secrets/openai_api_key \
    MAX_REQUEST_BYTES=2000000 HOME=/tmp
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
