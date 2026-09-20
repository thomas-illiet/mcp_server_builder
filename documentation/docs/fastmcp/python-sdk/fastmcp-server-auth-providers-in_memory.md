> ## Documentation Index
> Fetch the complete documentation index at: https://gofastmcp.com/llms.txt
> Use this file to discover all available pages before exploring further.

# in_memory

# `fastmcp.server.auth.providers.in_memory`

## Classes

### `InMemoryOAuthProvider` <sup><a href="https://github.com/PrefectHQ/fastmcp/blob/main/fastmcp_slim/fastmcp/server/auth/providers/in_memory.py#L31" target="_blank"><Icon icon="github" style="width: 14px; height: 14px;" /></a></sup>

An in-memory OAuth provider for testing purposes.
It simulates the OAuth 2.1 flow locally without external calls.

**Methods:**

#### `get_client` <sup><a href="https://github.com/PrefectHQ/fastmcp/blob/main/fastmcp_slim/fastmcp/server/auth/providers/in_memory.py#L70" target="_blank"><Icon icon="github" style="width: 14px; height: 14px;" /></a></sup>

```python theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
get_client(self, client_id: str) -> OAuthClientInformationFull | None
```

#### `register_client` <sup><a href="https://github.com/PrefectHQ/fastmcp/blob/main/fastmcp_slim/fastmcp/server/auth/providers/in_memory.py#L73" target="_blank"><Icon icon="github" style="width: 14px; height: 14px;" /></a></sup>

```python theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
register_client(self, client_info: OAuthClientInformationFull) -> None
```

#### `authorize` <sup><a href="https://github.com/PrefectHQ/fastmcp/blob/main/fastmcp_slim/fastmcp/server/auth/providers/in_memory.py#L97" target="_blank"><Icon icon="github" style="width: 14px; height: 14px;" /></a></sup>

```python theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str
```

Simulates user authorization and generates an authorization code.
Returns a redirect URI with the code and state.

#### `load_authorization_code` <sup><a href="https://github.com/PrefectHQ/fastmcp/blob/main/fastmcp_slim/fastmcp/server/auth/providers/in_memory.py#L154" target="_blank"><Icon icon="github" style="width: 14px; height: 14px;" /></a></sup>

```python theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
load_authorization_code(self, client: OAuthClientInformationFull, authorization_code: str) -> AuthorizationCode | None
```

#### `exchange_authorization_code` <sup><a href="https://github.com/PrefectHQ/fastmcp/blob/main/fastmcp_slim/fastmcp/server/auth/providers/in_memory.py#L167" target="_blank"><Icon icon="github" style="width: 14px; height: 14px;" /></a></sup>

```python theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
exchange_authorization_code(self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode) -> OAuthToken
```

#### `load_refresh_token` <sup><a href="https://github.com/PrefectHQ/fastmcp/blob/main/fastmcp_slim/fastmcp/server/auth/providers/in_memory.py#L220" target="_blank"><Icon icon="github" style="width: 14px; height: 14px;" /></a></sup>

```python theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
load_refresh_token(self, client: OAuthClientInformationFull, refresh_token: str) -> RefreshToken | None
```

#### `exchange_refresh_token` <sup><a href="https://github.com/PrefectHQ/fastmcp/blob/main/fastmcp_slim/fastmcp/server/auth/providers/in_memory.py#L235" target="_blank"><Icon icon="github" style="width: 14px; height: 14px;" /></a></sup>

```python theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
exchange_refresh_token(self, client: OAuthClientInformationFull, refresh_token: RefreshToken, scopes: list[str]) -> OAuthToken
```

#### `load_access_token` <sup><a href="https://github.com/PrefectHQ/fastmcp/blob/main/fastmcp_slim/fastmcp/server/auth/providers/in_memory.py#L292" target="_blank"><Icon icon="github" style="width: 14px; height: 14px;" /></a></sup>

```python theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
load_access_token(self, token: str) -> AccessToken | None
```

#### `verify_token` <sup><a href="https://github.com/PrefectHQ/fastmcp/blob/main/fastmcp_slim/fastmcp/server/auth/providers/in_memory.py#L303" target="_blank"><Icon icon="github" style="width: 14px; height: 14px;" /></a></sup>

```python theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
verify_token(self, token: str) -> AccessToken | None
```

Verify a bearer token and return access info if valid.

This method implements the TokenVerifier protocol by delegating
to our existing load\_access\_token method.

**Args:**

* `token`: The token string to validate

**Returns:**

* AccessToken object if valid, None if invalid or expired

#### `revoke_token` <sup><a href="https://github.com/PrefectHQ/fastmcp/blob/main/fastmcp_slim/fastmcp/server/auth/providers/in_memory.py#L360" target="_blank"><Icon icon="github" style="width: 14px; height: 14px;" /></a></sup>

```python theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
revoke_token(self, token: AccessToken | RefreshToken) -> None
```

Revokes an access or refresh token and its counterpart.
