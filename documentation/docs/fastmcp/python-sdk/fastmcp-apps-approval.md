> ## Documentation Index
> Fetch the complete documentation index at: https://gofastmcp.com/llms.txt
> Use this file to discover all available pages before exploring further.

# approval

# `fastmcp.apps.approval`

Approval — a Provider that adds human-in-the-loop approval to any server.

The LLM presents a summary of what it's about to do, and the user
approves or rejects via buttons. The result is sent back into the
conversation as a message, prompting the LLM's next turn.

Requires `fastmcp[apps]` (prefab-ui).

Usage::

from fastmcp import FastMCP
from fastmcp.apps.approval import Approval

mcp = FastMCP("My Server")
mcp.add\_provider(Approval())

## Classes

### `Approval` <sup><a href="https://github.com/PrefectHQ/fastmcp/blob/main/fastmcp_slim/fastmcp/apps/approval.py#L49" target="_blank"><Icon icon="github" style="width: 14px; height: 14px;" /></a></sup>

A Provider that adds human-in-the-loop approval to a server.

The LLM calls the `request_approval` tool with a summary and
optional details. The user sees an approval card with Approve and
Reject buttons. Clicking either sends a message back into the
conversation (via `SendMessage`), triggering the LLM's next turn.

The message appears as if the user sent it, so the LLM sees
something like `'"Deploy v3.2 to production" is APPROVED'`.

Example::

from fastmcp import FastMCP
from fastmcp.apps.approval import Approval

mcp = FastMCP("My Server")
mcp.add\_provider(Approval())

Customized::

Approval(
title="Deploy Gate",
approve\_text="Ship it",
approve\_variant="default",
reject\_text="Abort",
reject\_variant="destructive",
)
