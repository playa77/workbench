"""Workbench — main entry point.

Usage:
    workbench serve           Start the FastAPI server
    workbench init-db         Run Alembic migrations
    workbench create-user     Create a new user and API key
"""

import argparse
import asyncio
import logging
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

    create_user_parser = sub.add_parser("create-user", help="Create a new user and API key")
    create_user_parser.add_argument("username", help="Username for the new user")

    args = parser.parse_args()

    if args.command == "version":
        from workbench.__version__ import __version__

        print(f"Workbench v{__version__}")
        return

    if args.command == "init-db":
        config = load_config()
        _run_migrations(config)
        return

    if args.command == "create-user":
        config = load_config()
        from workbench.core.db import init_db as _init_db
        _init_db(config)
        asyncio.run(_create_user_only(args.username))
        return

    if args.command == "serve":
        config = load_config()
        host = args.host or config.api_host
        port = args.port or config.api_port
        app = create_app(config)
        logger.info("Serving Workbench on %s:%s", host, port)
        uvicorn.run(app, host=host, port=port, log_level=config.log_level.lower())
        return

    parser.print_help()


async def _create_user_only(username: str) -> None:
    from sqlalchemy import select

    from workbench.core.auth import generate_api_key
    from workbench.core.db import close_db, get_engine, get_session_factory
    from workbench.core.models import Base, User, UserApiKey

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = get_session_factory()
    async with factory() as session:
        existing = await session.execute(select(User).where(User.username == username))
        if existing.scalar_one_or_none() is not None:
            print(f"User '{username}' already exists.")
            return

        user = User(username=username)
        session.add(user)
        await session.flush()

        raw_key, hashed = generate_api_key()
        session.add(UserApiKey(user_id=user.id, key_hash=hashed, label="default"))
        await session.commit()

        print(f"User created: {user.id}")
        print(f"Username: {username}")
        print(f"API Key: {raw_key}")
        print()
        print("Save this API key — it will not be shown again.")
        print("Login at the web UI with this key, or use it as a Bearer token.")

    await close_db()


def _run_migrations(config) -> None:
    from workbench.core.db import close_db, init_db

    init_db(config)

    asyncio.run(_run_alembic_upgrade())
    asyncio.run(close_db())


async def _run_alembic_upgrade() -> None:
    from alembic.config import Config as AlembicConfig

    from alembic import command

    root = Path(__file__).resolve().parents[2]
    alembic_ini = root / "alembic.ini"

    alembic_cfg = AlembicConfig(str(alembic_ini))
    alembic_cfg.set_main_option("script_location", str(root / "alembic"))

    command.upgrade(alembic_cfg, "head")
    print("Database schema initialized successfully (Alembic upgrade complete).")


if __name__ == "__main__":
    main()
