> ## Documentation Index
> Fetch the complete documentation index at: https://gofastmcp.com/llms.txt
> Use this file to discover all available pages before exploring further.

# http

# `fastmcp.client.transports.http`

Streamable HTTP transport for FastMCP Client.

## Classes

### `StreamableHttpTransport` <sup><a href="https://github.com/PrefectHQ/fastmcp/blob/main/fastmcp_slim/fastmcp/client/transports/http.py#L31" target="_blank"><Icon icon="github" style="width: 14px; height: 14px;" /></a></sup>

Transport implementation that connects to an MCP server via Streamable HTTP Requests.

**Methods:**

#### `connect_session` <sup><a href="https://github.com/PrefectHQ/fastmcp/blob/main/fastmcp_slim/fastmcp/client/transports/http.py#L156" target="_blank"><Icon icon="github" style="width: 14px; height: 14px;" /></a></sup>

```python theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
connect_session(self, **session_kwargs: Unpack[SessionKwargs]) -> AsyncIterator[ClientSession]
```

#### `get_session_id` <sup><a href="https://github.com/PrefectHQ/fastmcp/blob/main/fastmcp_slim/fastmcp/client/transports/http.py#L227" target="_blank"><Icon icon="github" style="width: 14px; height: 14px;" /></a></sup>

```python theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
get_session_id(self) -> str | None
```

#### `close` <sup><a href="https://github.com/PrefectHQ/fastmcp/blob/main/fastmcp_slim/fastmcp/client/transports/http.py#L230" target="_blank"><Icon icon="github" style="width: 14px; height: 14px;" /></a></sup>

```python theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
close(self)
```
