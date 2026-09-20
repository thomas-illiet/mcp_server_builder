> ## Documentation Index
> Fetch the complete documentation index at: https://gofastmcp.com/llms.txt
> Use this file to discover all available pages before exploring further.

# exceptions

# `fastmcp.utilities.exceptions`

## Functions

### `is_http_status_error` <sup><a href="https://github.com/PrefectHQ/fastmcp/blob/main/fastmcp_slim/fastmcp/utilities/exceptions.py#L19" target="_blank"><Icon icon="github" style="width: 14px; height: 14px;" /></a></sup>

```python theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
is_http_status_error(exc: BaseException) -> bool
```

Return whether an exception is an httpx2 or legacy-httpx status error.

### `get_http_status_code` <sup><a href="https://github.com/PrefectHQ/fastmcp/blob/main/fastmcp_slim/fastmcp/utilities/exceptions.py#L26" target="_blank"><Icon icon="github" style="width: 14px; height: 14px;" /></a></sup>

```python theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
get_http_status_code(exc: BaseException) -> int | None
```

Return the response status code from a recognized HTTP status error.

### `is_timeout_error` <sup><a href="https://github.com/PrefectHQ/fastmcp/blob/main/fastmcp_slim/fastmcp/utilities/exceptions.py#L34" target="_blank"><Icon icon="github" style="width: 14px; height: 14px;" /></a></sup>

```python theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
is_timeout_error(exc: BaseException) -> bool
```

Return whether an exception is an httpx2 or legacy-httpx timeout.

### `is_request_error` <sup><a href="https://github.com/PrefectHQ/fastmcp/blob/main/fastmcp_slim/fastmcp/utilities/exceptions.py#L41" target="_blank"><Icon icon="github" style="width: 14px; height: 14px;" /></a></sup>

```python theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
is_request_error(exc: BaseException) -> bool
```

Return whether an exception is an httpx2 or legacy-httpx request error.

### `iter_exc` <sup><a href="https://github.com/PrefectHQ/fastmcp/blob/main/fastmcp_slim/fastmcp/utilities/exceptions.py#L48" target="_blank"><Icon icon="github" style="width: 14px; height: 14px;" /></a></sup>

```python theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
iter_exc(group: BaseExceptionGroup)
```

### `get_catch_handlers` <sup><a href="https://github.com/PrefectHQ/fastmcp/blob/main/fastmcp_slim/fastmcp/utilities/exceptions.py#L76" target="_blank"><Icon icon="github" style="width: 14px; height: 14px;" /></a></sup>

```python theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
get_catch_handlers() -> Mapping[type[BaseException] | Iterable[type[BaseException]], Callable[[BaseExceptionGroup[Any]], Any]]
```
