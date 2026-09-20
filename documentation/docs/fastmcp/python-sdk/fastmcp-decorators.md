> ## Documentation Index
> Fetch the complete documentation index at: https://gofastmcp.com/llms.txt
> Use this file to discover all available pages before exploring further.

# decorators

# `fastmcp.decorators`

Shared decorator utilities for FastMCP.

## Functions

### `resolve_task_config` <sup><a href="https://github.com/PrefectHQ/fastmcp/blob/main/fastmcp_slim/fastmcp/decorators.py#L17" target="_blank"><Icon icon="github" style="width: 14px; height: 14px;" /></a></sup>

```python theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
resolve_task_config(task: bool | TaskConfig | None) -> bool | TaskConfig
```

Resolve task config, defaulting None to False.

### `get_fastmcp_meta` <sup><a href="https://github.com/PrefectHQ/fastmcp/blob/main/fastmcp_slim/fastmcp/decorators.py#L29" target="_blank"><Icon icon="github" style="width: 14px; height: 14px;" /></a></sup>

```python theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
get_fastmcp_meta(fn: Any) -> Any | None
```

Extract FastMCP metadata from a function, handling bound methods and wrappers.

## Classes

### `HasFastMCPMeta` <sup><a href="https://github.com/PrefectHQ/fastmcp/blob/main/fastmcp_slim/fastmcp/decorators.py#L23" target="_blank"><Icon icon="github" style="width: 14px; height: 14px;" /></a></sup>

Protocol for callables decorated with FastMCP metadata.
