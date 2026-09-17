"""Log MCP tool activity without recording arguments, results or exception messages."""

import asyncio
import logging
from time import perf_counter
from uuid import uuid4

from fastmcp.server.middleware import Middleware

logger = logging.getLogger("mcp_builder.tools")


class ToolLoggingMiddleware(Middleware):
    """Trace each tool call with a unique ID, elapsed time and completion status."""

    async def on_call_tool(self, context, call_next):
        """Log execution boundaries while preserving results, errors and cancellation."""
        call_id = uuid4().hex[:12]
        tool_name = context.message.name
        started = perf_counter()
        logger.info("Tool started tool=%r call=%s", tool_name, call_id)

        try:
            result = await call_next(context)
        except asyncio.CancelledError:
            logger.warning(
                "Tool cancelled tool=%r call=%s duration_ms=%.1f",
                tool_name, call_id, (perf_counter() - started) * 1000,
            )
            raise
        except Exception as exc:
            # Exception messages and tracebacks can contain client files or arguments.
            logger.error(
                "Tool failed tool=%r call=%s duration_ms=%.1f error_type=%s",
                tool_name, call_id, (perf_counter() - started) * 1000, type(exc).__name__,
            )
            raise

        logger.info(
            "Tool completed tool=%r call=%s duration_ms=%.1f",
            tool_name, call_id, (perf_counter() - started) * 1000,
        )
        return result

    async def on_list_tools(self, context, call_next):
        """Show when a client requests the available tool catalogue."""
        logger.info("Client requested tools/list")
        return await call_next(context)
