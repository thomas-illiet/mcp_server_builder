> ## Documentation Index
> Fetch the complete documentation index at: https://gofastmcp.com/llms.txt
> Use this file to discover all available pages before exploring further.

# oauth

# `fastmcp.client.auth.oauth`

## Functions

### `check_if_auth_required` <sup><a href="https://github.com/PrefectHQ/fastmcp/blob/main/fastmcp_slim/fastmcp/client/auth/oauth.py#L58" target="_blank"><Icon icon="github" style="width: 14px; height: 14px;" /></a></sup>

```python theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
check_if_auth_required(mcp_url: str, httpx_kwargs: dict[str, Any] | None = None) -> bool
```

Check if the MCP endpoint requires authentication by making a test request.

**Returns:**

* True if auth appears to be required, False otherwise

## Classes

### `ClientNotFoundError` <sup><a href="https://github.com/PrefectHQ/fastmcp/blob/main/fastmcp_slim/fastmcp/client/auth/oauth.py#L50" target="_blank"><Icon icon="github" style="width: 14px; height: 14px;" /></a></sup>

Raised when OAuth client credentials are not found on the server.

### `ExpiredClientRegistrationError` <sup><a href="https://github.com/PrefectHQ/fastmcp/blob/main/fastmcp_slim/fastmcp/client/auth/oauth.py#L54" target="_blank"><Icon icon="github" style="width: 14px; height: 14px;" /></a></sup>

Raised when dynamic registration returns an expired client secret.

### `TokenStorageAdapter` <sup><a href="https://github.com/PrefectHQ/fastmcp/blob/main/fastmcp_slim/fastmcp/client/auth/oauth.py#L88" target="_blank"><Icon icon="github" style="width: 14px; height: 14px;" /></a></sup>

**Methods:**

#### `clear` <sup><a href="https://github.com/PrefectHQ/fastmcp/blob/main/fastmcp_slim/fastmcp/client/auth/oauth.py#L135" target="_blank"><Icon icon="github" style="width: 14px; height: 14px;" /></a></sup>

```python theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
clear(self) -> None
```

#### `get_tokens` <sup><a href="https://github.com/PrefectHQ/fastmcp/blob/main/fastmcp_slim/fastmcp/client/auth/oauth.py#L144" target="_blank"><Icon icon="github" style="width: 14px; height: 14px;" /></a></sup>

```python theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
get_tokens(self) -> OAuthToken | None
```

#### `set_tokens` <sup><a href="https://github.com/PrefectHQ/fastmcp/blob/main/fastmcp_slim/fastmcp/client/auth/oauth.py#L148" target="_blank"><Icon icon="github" style="width: 14px; height: 14px;" /></a></sup>

```python theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
set_tokens(self, tokens: OAuthToken) -> None
```

#### `get_token_expiry` <sup><a href="https://github.com/PrefectHQ/fastmcp/blob/main/fastmcp_slim/fastmcp/client/auth/oauth.py#L168" target="_blank"><Icon icon="github" style="width: 14px; height: 14px;" /></a></sup>

```python theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
get_token_expiry(self) -> float | None
```

#### `get_client_info` <sup><a href="https://github.com/PrefectHQ/fastmcp/blob/main/fastmcp_slim/fastmcp/client/auth/oauth.py#L178" target="_blank"><Icon icon="github" style="width: 14px; height: 14px;" /></a></sup>

```python theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
get_client_info(self) -> OAuthClientInformationFull | None
```

#### `set_client_info` <sup><a href="https://github.com/PrefectHQ/fastmcp/blob/main/fastmcp_slim/fastmcp/client/auth/oauth.py#L184" target="_blank"><Icon icon="github" style="width: 14px; height: 14px;" /></a></sup>

```python theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
set_client_info(self, client_info: OAuthClientInformationFull) -> None
```

### `OAuth` <sup><a href="https://github.com/PrefectHQ/fastmcp/blob/main/fastmcp_slim/fastmcp/client/auth/oauth.py#L202" target="_blank"><Icon icon="github" style="width: 14px; height: 14px;" /></a></sup>

OAuth client provider for MCP servers with browser-based authentication.

This class provides OAuth authentication for FastMCP clients by opening
a browser for user authorization and running a local callback server.

**Methods:**

#### `redirect_handler` <sup><a href="https://github.com/PrefectHQ/fastmcp/blob/main/fastmcp_slim/fastmcp/client/auth/oauth.py#L381" target="_blank"><Icon icon="github" style="width: 14px; height: 14px;" /></a></sup>

```python theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
redirect_handler(self, authorization_url: str) -> None
```

Open browser for authorization, with pre-flight check for invalid client.

#### `callback_handler` <sup><a href="https://github.com/PrefectHQ/fastmcp/blob/main/fastmcp_slim/fastmcp/client/auth/oauth.py#L402" target="_blank"><Icon icon="github" style="width: 14px; height: 14px;" /></a></sup>

```python theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
callback_handler(self) -> AuthorizationCodeResult
```

Handle OAuth callback and return the authorization code result.

#### `async_auth_flow` <sup><a href="https://github.com/PrefectHQ/fastmcp/blob/main/fastmcp_slim/fastmcp/client/auth/oauth.py#L446" target="_blank"><Icon icon="github" style="width: 14px; height: 14px;" /></a></sup>

```python theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
async_auth_flow(self, request: httpx2.Request) -> AsyncGenerator[httpx2.Request, httpx2.Response]
```

HTTPX auth flow with automatic retry on stale cached credentials.

If the OAuth flow fails due to invalid/stale client credentials,
clears the cache and retries once with fresh registration.
