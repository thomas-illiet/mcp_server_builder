> ## Documentation Index
> Fetch the complete documentation index at: https://gofastmcp.com/llms.txt
> Use this file to discover all available pages before exploring further.

# __init__

# `fastmcp.server.transforms.search`

Search transforms for tool discovery.

Search transforms collapse a large tool catalog into a search interface,
letting LLMs discover tools on demand instead of seeing the full list.

Example:

```python theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
from fastmcp import FastMCP
from fastmcp.server.transforms.search import RegexSearchTransform

mcp = FastMCP("Server")
mcp.add_transform(RegexSearchTransform())
# list_tools now returns only search_tools + call_tool
```
