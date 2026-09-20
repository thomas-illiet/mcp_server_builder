> ## Documentation Index
> Fetch the complete documentation index at: https://gofastmcp.com/llms.txt
> Use this file to discover all available pages before exploring further.

# configuration

# `fastmcp.cli.deploy.configuration`

Global non-secret configuration for the FastMCP CLI.

## Classes

### `HorizonConfiguration` <sup><a href="https://github.com/PrefectHQ/fastmcp/blob/main/fastmcp_slim/fastmcp/cli/deploy/configuration.py#L18" target="_blank"><Icon icon="github" style="width: 14px; height: 14px;" /></a></sup>

**Methods:**

#### `validate_api_origin` <sup><a href="https://github.com/PrefectHQ/fastmcp/blob/main/fastmcp_slim/fastmcp/cli/deploy/configuration.py#L26" target="_blank"><Icon icon="github" style="width: 14px; height: 14px;" /></a></sup>

```python theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
validate_api_origin(cls, value: str) -> str
```

### `ConfigurationStore` <sup><a href="https://github.com/PrefectHQ/fastmcp/blob/main/fastmcp_slim/fastmcp/cli/deploy/configuration.py#L30" target="_blank"><Icon icon="github" style="width: 14px; height: 14px;" /></a></sup>

Persist the Horizon API origin without organization state.

**Methods:**

#### `load` <sup><a href="https://github.com/PrefectHQ/fastmcp/blob/main/fastmcp_slim/fastmcp/cli/deploy/configuration.py#L40" target="_blank"><Icon icon="github" style="width: 14px; height: 14px;" /></a></sup>

```python theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
load(self) -> HorizonConfiguration
```

#### `save` <sup><a href="https://github.com/PrefectHQ/fastmcp/blob/main/fastmcp_slim/fastmcp/cli/deploy/configuration.py#L49" target="_blank"><Icon icon="github" style="width: 14px; height: 14px;" /></a></sup>

```python theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
save(self, configuration: HorizonConfiguration) -> None
```

#### `set_api_origin` <sup><a href="https://github.com/PrefectHQ/fastmcp/blob/main/fastmcp_slim/fastmcp/cli/deploy/configuration.py#L55" target="_blank"><Icon icon="github" style="width: 14px; height: 14px;" /></a></sup>

```python theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
set_api_origin(self, api_origin: str) -> HorizonConfiguration
```

Set the origin and clear credentials before an origin change.
