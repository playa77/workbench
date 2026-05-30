"""Workbench — main entry point.

Usage:
    workbench serve        Start the FastAPI server
    workbench init-db      Run Alembic migrations
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

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
    from workbench.core.db import close_db, init_db

    init_db(config)

    asyncio.run(_run_alembic_upgrade())
    asyncio.run(close_db())


async def _run_alembic_upgrade() -> None:
    from alembic import command
    from alembic.config import Config as AlembicConfig

    root = Path(__file__).resolve().parents[2]
    alembic_ini = root / "alembic.ini"

    alembic_cfg = AlembicConfig(str(alembic_ini))
    alembic_cfg.set_main_option("script_location", str(root / "alembic"))

    command.upgrade(alembic_cfg, "head")
    print("Database schema initialized successfully (Alembic upgrade complete).")


if __name__ == "__main__":
    main()
