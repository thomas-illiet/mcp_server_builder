"""Bound request memory before the MCP parser receives the body."""
from starlette.responses import JSONResponse


class BodyLimit:
    """Bound streamed HTTP bodies before the MCP parser sees them."""
    def __init__(self, app, limit: int):
        """Wrap an ASGI app with a maximum HTTP request body size in bytes."""
        self.app, self.limit = app, limit

    async def __call__(self, scope, receive, send):
        """Buffer a bounded HTTP body, reject overflow with 413 and replay accepted bytes."""
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            if len(body) > self.limit:
                return await JSONResponse({"error": "Request body too large"}, 413)(scope, receive, send)
            if not message.get("more_body", False):
                break
        delivered = False

        async def replay():
            """Deliver the buffered request once, then forward disconnect/subsequent ASGI messages."""
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, replay, send)
