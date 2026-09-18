"""Trusted FastMCP snippets and official references."""
from mcp_builder import BUILDER_VERSION, FASTMCP_VERSION, SCHEMA_VERSION

EXAMPLES = {
    "tool": ("servers/tools", '''@mcp.tool
def add(a: int, b: int) -> int:
    """Add two integers."""
    return a + b
'''),
    "resource": ("servers/resources", '''@mcp.resource("config://version")
def version() -> str:
    """Return the application version."""
    return "1.0.0"
'''),
    "prompt": ("servers/prompts", '''@mcp.prompt
def explain(topic: str) -> str:
    """Ask the assistant to explain a topic."""
    return f"Explain this topic with examples: {topic}"
'''),
    "context": ("servers/context", '''from fastmcp import Context

@mcp.tool
async def progress(steps: int, ctx: Context) -> str:
    """Demonstrate progress reporting."""
    if not 1 <= steps <= 100:
        raise ValueError("steps must be between 1 and 100")
    for step in range(steps):
        await ctx.report_progress(progress=step + 1, total=steps)
    return "Done"
'''),
    "errors": ("servers/tools", '''from fastmcp.exceptions import ToolError

@mcp.tool
def divide(a: float, b: float) -> float:
    """Divide two numbers with an explicit user-facing error."""
    if b == 0:
        raise ToolError("The divisor must not be zero")
    return a / b
'''),
    "testing": ("servers/testing", '''"""Exercise the example server through an in-process MCP client."""

import pytest
from fastmcp import Client
from app.server import mcp

@pytest.mark.asyncio
async def test_add():
    """Check that typed arguments reach the add tool and its result is serialized."""
    async with Client(mcp) as client:
        result = await client.call_tool("add", {"a": 2, "b": 3})
        assert result.data == 5
'''),
}

def get_example(topic: str) -> dict:
    """Return a trusted snippet and its official reference, or reject an unknown topic."""
    if topic not in EXAMPLES:
        raise ValueError(f"Exemples disponibles : {', '.join(EXAMPLES)}")
    page, code = EXAMPLES[topic]
    return {"schema_version": SCHEMA_VERSION, "generator_version": BUILDER_VERSION,
            "topic": topic, "code": code, "reference": f"https://gofastmcp.com/{page}.md",
            "requires": "from fastmcp import FastMCP; mcp = FastMCP('Example')",
            "fastmcp_version": FASTMCP_VERSION}
