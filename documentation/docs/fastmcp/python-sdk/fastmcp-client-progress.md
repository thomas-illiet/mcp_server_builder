> ## Documentation Index
> Fetch the complete documentation index at: https://gofastmcp.com/llms.txt
> Use this file to discover all available pages before exploring further.

# progress

# `fastmcp.client.progress`

## Functions

### `default_progress_handler` <sup><a href="https://github.com/PrefectHQ/fastmcp/blob/main/fastmcp_slim/fastmcp/client/progress.py#L12" target="_blank"><Icon icon="github" style="width: 14px; height: 14px;" /></a></sup>

```python theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
default_progress_handler(progress: float, total: float | None, message: str | None) -> None
```

Default handler for progress notifications.

Logs progress updates at debug level, properly handling missing total or message values.

**Args:**

* `progress`: Current progress value
* `total`: Optional total expected value
* `message`: Optional status message
