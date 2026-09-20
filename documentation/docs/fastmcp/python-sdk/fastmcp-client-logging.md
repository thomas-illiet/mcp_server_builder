> ## Documentation Index
> Fetch the complete documentation index at: https://gofastmcp.com/llms.txt
> Use this file to discover all available pages before exploring further.

# logging

# `fastmcp.client.logging`

## Functions

### `default_log_handler` <sup><a href="https://github.com/PrefectHQ/fastmcp/blob/main/fastmcp_slim/fastmcp/client/logging.py#L17" target="_blank"><Icon icon="github" style="width: 14px; height: 14px;" /></a></sup>

```python theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
default_log_handler(message: LogMessage) -> None
```

Default handler that properly routes server log messages to appropriate log levels.

### `create_log_callback` <sup><a href="https://github.com/PrefectHQ/fastmcp/blob/main/fastmcp_slim/fastmcp/client/logging.py#L47" target="_blank"><Icon icon="github" style="width: 14px; height: 14px;" /></a></sup>

```python theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
create_log_callback(handler: LogHandler | None = None) -> LoggingFnT
```
