"""Stdio MCP entry point for Hermes Agent and other local MCP clients."""

import logging

from app.db import SessionLocal, ensure_schema
from app.mcp_tools import mcp
from app.services.credentials_service import bootstrap_credentials_from_env

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    ensure_schema()

    db = SessionLocal()
    try:
        if bootstrap_credentials_from_env(db):
            logger.info("Selectel credentials synced from environment")
    finally:
        db.close()

    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
