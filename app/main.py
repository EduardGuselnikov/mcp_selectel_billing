import contextlib
import logging

from fastapi import FastAPI

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

from app.api.users import router as users_router
from app.db import SessionLocal
from app.mcp_mount import MCPHttpMiddleware
from app.mcp_tools import mcp
from app.services.credentials_service import bootstrap_credentials_from_env

logger = logging.getLogger(__name__)


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    db = SessionLocal()
    try:
        if bootstrap_credentials_from_env(db):
            logger.info("Selectel credentials loaded from environment")
    finally:
        db.close()

    async with mcp.session_manager.run():
        yield


fastapi_app = FastAPI(
    title="Selectel MCP Server",
    description="MCP-сервер для получения балансов Selectel",
    version="0.1.0",
    lifespan=lifespan,
)

fastapi_app.include_router(users_router)


@fastapi_app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


app = MCPHttpMiddleware(fastapi_app, mcp.streamable_http_app())
