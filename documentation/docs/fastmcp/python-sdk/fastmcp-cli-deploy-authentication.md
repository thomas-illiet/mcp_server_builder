> ## Documentation Index
> Fetch the complete documentation index at: https://gofastmcp.com/llms.txt
> Use this file to discover all available pages before exploring further.

# authentication

# `fastmcp.cli.deploy.authentication`

Horizon device authorization workflow.

## Functions

### `poll_device_authorization` <sup><a href="https://github.com/PrefectHQ/fastmcp/blob/main/fastmcp_slim/fastmcp/cli/deploy/authentication.py#L32" target="_blank"><Icon icon="github" style="width: 14px; height: 14px;" /></a></sup>

```python theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
poll_device_authorization(client: HorizonClient, authorization: DeviceAuthorization) -> SecretStr
```

Poll at the server interval until the device request completes.

### `authorize_device` <sup><a href="https://github.com/PrefectHQ/fastmcp/blob/main/fastmcp_slim/fastmcp/cli/deploy/authentication.py#L77" target="_blank"><Icon icon="github" style="width: 14px; height: 14px;" /></a></sup>

```python theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
authorize_device(client: HorizonClient) -> SecretStr
```

Create, present, and complete a Horizon device authorization.

## Classes

### `DeviceAuthorizationError` <sup><a href="https://github.com/PrefectHQ/fastmcp/blob/main/fastmcp_slim/fastmcp/cli/deploy/authentication.py#L20" target="_blank"><Icon icon="github" style="width: 14px; height: 14px;" /></a></sup>

Device authorization did not complete.

### `DeviceAuthorizationDeniedError` <sup><a href="https://github.com/PrefectHQ/fastmcp/blob/main/fastmcp_slim/fastmcp/cli/deploy/authentication.py#L24" target="_blank"><Icon icon="github" style="width: 14px; height: 14px;" /></a></sup>

The user denied the device authorization request.

### `DeviceAuthorizationExpiredError` <sup><a href="https://github.com/PrefectHQ/fastmcp/blob/main/fastmcp_slim/fastmcp/cli/deploy/authentication.py#L28" target="_blank"><Icon icon="github" style="width: 14px; height: 14px;" /></a></sup>

The device authorization request expired.
