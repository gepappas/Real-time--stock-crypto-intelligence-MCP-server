"""
real-time-stock-crypto-intelligence v5.2.2 — Dual Transport Entry Point
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 stdio → MCP protocol (Claude Desktop, Smithery, MCPize)
 http → FastAPI + SEO pages (Railway / Cloud Run / Fly.io)

FIXES in v5.2.2:
- Database init moved to FastAPI lifespan (non-blocking, runs once)
- Version bumped to 5.2.2 across all modules
- Cleaner shutdown handling
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
logger = logging.getLogger("market-data-intelligence")


def _run_http():
    import uvicorn
    # DB init is now handled in FastAPI lifespan event (app/api.py)
    # so it runs asynchronously without blocking the main thread.
    port = int(os.getenv("PORT", "8080"))
    host = os.getenv("HOST", "0.0.0.0")
    workers = int(os.getenv("WEB_CONCURRENCY", "1"))
    logger.info("Starting HTTP server on %s:%d (%d worker(s))", host, port, workers)
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
