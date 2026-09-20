> ## Documentation Index
> Fetch the complete documentation index at: https://gofastmcp.com/llms.txt
> Use this file to discover all available pages before exploring further.

# __init__

# `fastmcp.server.providers.skills`

Skills providers for exposing agent skills as MCP resources.

This module provides a two-layer architecture for skill discovery:

* **SkillProvider**: Handles a single skill folder, exposing its files as resources.
* **SkillsDirectoryProvider**: Scans a directory, creates a SkillProvider per folder.
* **Vendor providers**: Platform-specific providers for Claude, Cursor, VS Code, Codex,
  Gemini, Goose, Copilot, and OpenCode.

Example:

```python theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
from pathlib import Path
from fastmcp import FastMCP
from fastmcp.server.providers.skills import ClaudeSkillsProvider, SkillProvider

mcp = FastMCP("Skills Server")

# Load a single skill
mcp.add_provider(SkillProvider(Path.home() / ".claude/skills/pdf-processing"))

# Or load all skills in a directory
mcp.add_provider(ClaudeSkillsProvider())  # Uses ~/.claude/skills/
```
