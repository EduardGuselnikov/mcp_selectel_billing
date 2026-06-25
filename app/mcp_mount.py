from starlette.types import ASGIApp, Receive, Scope, Send

MCP_HTTP_PATHS = frozenset({"/mcp", "/mcp/"})


class MCPHttpMiddleware:
    """Пробрасывает /mcp и /mcp/ в Streamable HTTP MCP на внутренний путь /."""

    def __init__(self, app: ASGIApp, mcp_asgi_app: ASGIApp) -> None:
        self.app = app
        self.mcp_asgi_app = mcp_asgi_app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope.get("path") in MCP_HTTP_PATHS:
            mcp_scope = dict(scope)
            mcp_scope["path"] = "/"
            mcp_scope["raw_path"] = b"/"
            await self.mcp_asgi_app(mcp_scope, receive, send)
            return

        await self.app(scope, receive, send)
