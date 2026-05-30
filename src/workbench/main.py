"""Workbench — main entry point.

Usage:
    workbench serve        Start the FastAPI server
    workbench init-db      Run Alembic migrations
"""

import argparse
import asyncio
import logging
import sys

import uvicorn

from workbench.api.app import create_app
from workbench.core.config import load_config

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Workbench — unified BYOK AI Workbench")
    sub = parser.add_subparsers(dest="command")

    serve_parser = sub.add_parser("serve", help="Start the API server")
    serve_parser.add_argument("--host", default=None, help="Bind address")
    serve_parser.add_argument("--port", type=int, default=None, help="Listen port")

    sub.add_parser("init-db", help="Initialize database schema (runs Alembic)")
    sub.add_parser("version", help="Print version and exit")

    args = parser.parse_args()

    if args.command == "version":
        from workbench.__version__ import __version__
        print(f"Workbench v{__version__}")
        return

    config = load_config()

    if args.command == "init-db":
        _run_migrations(config)
        return

    if args.command == "serve":
        host = args.host or config.api_host
        port = args.port or config.api_port
        app = create_app(config)
        logger.info("Serving Workbench on %s:%s", host, port)
        uvicorn.run(app, host=host, port=port, log_level=config.log_level.lower())
        return

    parser.print_help()


def _run_migrations(config) -> None:
    from workbench.core.db import init_db, close_db
    from workbench.core.models import Base

    init_db(config)
    from workbench.core.db import _engine as engine

    async def _do() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        print("Database schema initialized successfully.")

    asyncio.run(_do())
    asyncio.run(close_db())


if __name__ == "__main__":
    main()
