# MCP Builder offline — build, docs and development targets.
IMAGE   := offline-mcp-builder:0.1.0
SERVICE := mcp-builder
TAR     := offline-mcp-builder.tar

.PHONY: help docs build up down restart logs lint test save load clean all

help:
	@echo "Available targets:"
	@echo "  docs     - Download and version the documents (sync-docs.sh)"
	@echo "  build    - Build the Docker image"
	@echo "  up       - Start the service"
	@echo "  down     - Stop the service"
	@echo "  restart  - Rebuild then restart"
	@echo "  logs     - Tail the service logs"
	@echo "  lint     - Check style with ruff"
	@echo "  test     - Run the pytest tests"
	@echo "  save     - Export the image to $(TAR)"
	@echo "  load     - Import the archive $(TAR)"
	@echo "  clean    - Stop and remove the image"
	@echo "  all      - Build then start"

docs:
	bash scripts/sync-docs.sh

build:
	docker compose build $(SERVICE)

up:
	docker compose up -d --no-build --pull never $(SERVICE)

down:
	docker compose down

restart: build
	docker compose up -d --no-build --pull never $(SERVICE)

logs:
	docker compose logs -f $(SERVICE)

lint:
	uv run --locked ruff check src scripts tests

test:
	uv run --locked pytest -q

save:
	docker save -o $(TAR) $(IMAGE)

load:
	docker load -i $(TAR)

clean: down
	docker rmi $(IMAGE) || true

all: build
	docker compose up -d --no-build --pull never $(SERVICE)
