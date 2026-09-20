> ## Documentation Index
> Fetch the complete documentation index at: https://gofastmcp.com/llms.txt
> Use this file to discover all available pages before exploring further.

# provider

# `fastmcp.server.providers.openapi.provider`

OpenAPIProvider for creating MCP components from OpenAPI specifications.

## Classes

### `OpenAPIProvider` <sup><a href="https://github.com/PrefectHQ/fastmcp/blob/main/fastmcp_slim/fastmcp/server/providers/openapi/provider.py#L61" target="_blank"><Icon icon="github" style="width: 14px; height: 14px;" /></a></sup>

Provider that creates MCP components from an OpenAPI specification.

Components are created eagerly during initialization by parsing the OpenAPI
spec. Each component makes HTTP calls to the described API endpoints.

**Methods:**

#### `lifespan` <sup><a href="https://github.com/PrefectHQ/fastmcp/blob/main/fastmcp_slim/fastmcp/server/providers/openapi/provider.py#L204" target="_blank"><Icon icon="github" style="width: 14px; height: 14px;" /></a></sup>

```python theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
lifespan(self) -> AsyncIterator[None]
```

Manage the lifecycle of the auto-created httpx client.

#### `get_tasks` <sup><a href="https://github.com/PrefectHQ/fastmcp/blob/main/fastmcp_slim/fastmcp/server/providers/openapi/provider.py#L454" target="_blank"><Icon icon="github" style="width: 14px; height: 14px;" /></a></sup>

```python theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
get_tasks(self) -> Sequence[FastMCPComponent]
```

Return empty list - OpenAPI components don't support tasks.
