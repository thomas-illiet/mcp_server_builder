> ## Documentation Index
> Fetch the complete documentation index at: https://gofastmcp.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Auth Utilities

> Create and validate CIMD documents for OAuth

export const VersionBadge = ({version}) => {
  return <Badge stroke size="lg" icon="gift" iconType="regular" className="version-badge">
            New in version <code>{version}</code>
        </Badge>;
};

<VersionBadge version="3.0.0" />

The `fastmcp auth` commands help with CIMD (Client ID Metadata Document) management — part of MCP's OAuth authentication flow. A CIMD is a JSON document you host at an HTTPS URL to identify your client application to MCP servers.

## Creating a CIMD

`fastmcp auth cimd create` generates a CIMD document:

```bash theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
fastmcp auth cimd create \
  --name "My App" \
  --redirect-uri "http://localhost:*/callback"
```

```json theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
{
  "client_id": "https://YOUR-DOMAIN.com/path/to/client.json",
  "client_name": "My App",
  "redirect_uris": ["http://localhost:*/callback"],
  "token_endpoint_auth_method": "none",
  "grant_types": ["authorization_code"],
  "response_types": ["code"]
}
```

By default, the generated document includes a placeholder `client_id`. Update it to match the URL where you'll host the document before deploying, or pass `--client-id` when generating the file.

### Options

| Option       | Flag                   | Description                                                       |
| ------------ | ---------------------- | ----------------------------------------------------------------- |
| Name         | `--name`               | **Required.** Human-readable client name                          |
| Redirect URI | `--redirect-uri`, `-r` | **Required.** Allowed redirect URIs (repeatable)                  |
| Client ID    | `--client-id`          | URL where this document will be hosted; defaults to a placeholder |
| Client URI   | `--client-uri`         | Client's home page URL                                            |
| Logo URI     | `--logo-uri`           | Client's logo URL                                                 |
| Scope        | `--scope`              | Space-separated list of scopes                                    |
| Output       | `--output`, `-o`       | Save to file (default: stdout)                                    |
| Pretty       | `--pretty`             | Pretty-print JSON (default: true)                                 |

### Example

```bash theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
fastmcp auth cimd create \
  --name "My Production App" \
  --redirect-uri "http://localhost:*/callback" \
  --redirect-uri "https://myapp.example.com/callback" \
  --client-id "https://myapp.example.com/oauth/client.json" \
  --client-uri "https://myapp.example.com" \
  --scope "read write" \
  --output client.json
```

## Validating a CIMD

`fastmcp auth cimd validate` fetches a hosted CIMD and verifies it conforms to the spec:

```bash theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
fastmcp auth cimd validate https://myapp.example.com/oauth/client.json
```

The validator checks that the URL is valid (HTTPS, non-root path), the document is valid JSON, the `client_id` matches the URL, and no shared-secret auth methods are used.

On success:

```
→ Fetching https://myapp.example.com/oauth/client.json...
✓ Valid CIMD document

Document details:
  client_id: https://myapp.example.com/oauth/client.json
  client_name: My App
  token_endpoint_auth_method: none
  redirect_uris:
    • http://localhost:*/callback
```

| Option  | Flag              | Description                                   |
| ------- | ----------------- | --------------------------------------------- |
| Timeout | `--timeout`, `-t` | HTTP request timeout in seconds (default: 10) |
