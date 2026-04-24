#!/usr/bin/env python3
"""
revolut-pulse-mcp v5.2 — Dual Transport Entry Point
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  stdio  →  MCP protocol (Claude Desktop, Smithery, MCPize)
  http   →  FastAPI + SEO pages (Railway / Fly.io)

Set env var:  MCP_TRANSPORT=stdio | http   (default: stdio)
"""
import asyncio
import logging
import os
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("revolut-pulse")


def _run_http():
    import uvicorn
    from app.api import app

    port = int(os.getenv("PORT", "8080"))
    host = os.getenv("HOST", "0.0.0.0")
    workers = int(os.getenv("WEB_CONCURRENCY", "1"))
    logger.info("Starting HTTP server on %s:%d (%d worker(s))", host, port, workers)

    # Optional: init DB and seed billing plans
    try:
        from saas.database import engine, Base
        from saas.billing import seed_plans

        async def _init_db():
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            await seed_plans()

        asyncio.run(_init_db())
        logger.info("Database initialised and billing plans seeded")
    except Exception as exc:
        logger.warning("Database init skipped: %s", exc)

    uvicorn.run(
        "app.api:app",
        host=host,
        port=port,
        workers=workers,
        log_level="info",
        access_log=True,
    )


def _run_stdio():
    from app.mcp_server import mcp
    logger.info("Starting MCP server — transport: stdio")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    transport = os.getenv("MCP_TRANSPORT", "stdio").lower()
    if transport == "http":
        _run_http()
    else:
        _run_stdio()
