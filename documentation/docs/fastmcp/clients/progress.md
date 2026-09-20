> ## Documentation Index
> Fetch the complete documentation index at: https://gofastmcp.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Progress Monitoring

> Handle progress notifications from long-running server operations.

export const VersionBadge = ({version}) => {
  return <Badge stroke size="lg" icon="gift" iconType="regular" className="version-badge">
            New in version <code>{version}</code>
        </Badge>;
};

<VersionBadge version="2.3.5" />

Use this when you need to track progress of long-running operations.

MCP servers can report progress during operations. The client receives these updates through a progress handler.

## Progress Handler

Set a handler when creating the client:

```python theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
from fastmcp import Client

async def progress_handler(
    progress: float,
    total: float | None,
    message: str | None
) -> None:
    if total is not None:
        percentage = (progress / total) * 100
        print(f"Progress: {percentage:.1f}% - {message or ''}")
    else:
        print(f"Progress: {progress} - {message or ''}")

client = Client(
    "my_mcp_server.py",
    progress_handler=progress_handler
)
```

The handler receives three parameters:

<Card icon="code" title="Handler Parameters">
  <ResponseField name="progress" type="float">
    Current progress value
  </ResponseField>

  <ResponseField name="total" type="float | None">
    Expected total value (may be None if unknown)
  </ResponseField>

  <ResponseField name="message" type="str | None">
    Optional status message
  </ResponseField>
</Card>

## Per-Call Handler

Override the client-level handler for specific tool calls:

```python theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
async with client:
    result = await client.call_tool(
        "long_running_task",
        {"param": "value"},
        progress_handler=my_progress_handler
    )
```
