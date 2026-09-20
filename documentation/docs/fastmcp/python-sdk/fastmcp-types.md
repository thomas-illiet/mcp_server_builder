> ## Documentation Index
> Fetch the complete documentation index at: https://gofastmcp.com/llms.txt
> Use this file to discover all available pages before exploring further.

# types

# `fastmcp.types`

Reusable type annotations for FastMCP tool parameters.

These types can be used in tool function signatures to influence how
parameters are presented in UIs (e.g. `fastmcp dev apps`) and
serialized in JSON Schema.

Example:

```python theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
from fastmcp import FastMCP
from fastmcp.types import Textarea

mcp = FastMCP("demo")

@mcp.tool()
def run_query(sql: Textarea) -> str:
    ...
```
