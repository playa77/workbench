"""Workbench — main entry point.

Usage:
    workbench serve           Start the FastAPI server
    workbench init-db         Run Alembic migrations
    workbench create-user     Create a new user and API key
    workbench backup          Create a full-system backup archive
    workbench restore         Restore from a backup archive
"""

# Version: 1.1.0 | 2026-06-26

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

    create_user_parser = sub.add_parser("create-user", help="Create a new user")
    create_user_parser.add_argument("--username", required=True, help="Username for the new user")
    create_user_parser.add_argument("--email", required=True, help="Email address")
    create_user_parser.add_argument("--password", required=True, help="Password")
    create_user_parser.add_argument("--admin", action="store_true", default=False, help="Grant admin privileges")

    backup_parser = sub.add_parser("backup", help="Create a full-system backup (database + data directory)")
    backup_parser.add_argument("--output-dir", default="/app/backups", help="Directory for the backup archive (default: /app/backups)")
    backup_parser.add_argument("--description", default="", help="Optional description for the backup manifest")

    restore_parser = sub.add_parser("restore", help="Restore a full-system backup from an archive")
    restore_parser.add_argument("archive", help="Path to the backup .tar.gz archive")

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
        if not config.smtp_host:
            print("WARNING: SMTP is not configured. Email features will not work.")
        from workbench.core.db import init_db as _init_db
        _init_db(config)
        asyncio.run(_create_user_only(args.username, args.email, args.password, args.admin))
        return

    if args.command == "backup":
        _backup_command(args.output_dir, args.description)
        return

    if args.command == "restore":
        _restore_command(args.archive)
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


async def _create_user_only(username: str, email: str, password: str, is_admin: bool = False) -> None:
    from sqlalchemy import select

    from workbench.core.auth import hash_password
    from workbench.core.db import close_db, get_engine, get_session_factory
    from workbench.core.models import Base, User

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = get_session_factory()
    async with factory() as session:
        existing = await session.execute(
            select(User).where((User.username == username) | (User.email == email))
        )
        if existing.scalar_one_or_none() is not None:
            print(f"User with username '{username}' or email '{email}' already exists.")
            return

        user = User(
            username=username,
            email=email,
            password_hash=hash_password(password),
            is_admin=is_admin,
        )
        session.add(user)
        await session.commit()

        role = "admin" if is_admin else "user"
        print(f"User created: {user.id}")
        print(f"Username: {username}")
        print(f"Email: {email}")
        print(f"Role: {role}")
        print()
        print("Login at the web UI with your email/username and password.")

    await close_db()


def _run_migrations(config) -> None:
    from workbench.core.db import close_db, init_db

    init_db(config)

    _run_alembic_upgrade()
    asyncio.run(close_db())


def _run_alembic_upgrade() -> None:
    from alembic.config import Config as AlembicConfig

    from alembic import command

    # Primary: relative to the source tree (editable installs)
    root = Path(__file__).resolve().parents[2]
    # Fallback: relative to the current working directory (Docker / pip install)
    if not (root / "alembic.ini").exists():
        root = Path.cwd()
    alembic_ini = root / "alembic.ini"

    alembic_cfg = AlembicConfig(str(alembic_ini))
    alembic_cfg.set_main_option("script_location", str(root / "alembic"))

    command.upgrade(alembic_cfg, "head")
    print("Database schema initialized successfully (Alembic upgrade complete).")


def _backup_command(output_dir: str, description: str) -> None:
    """CLI handler: create a full-system backup."""
    import os
    import sys
    from datetime import datetime, timezone

    from workbench.services.backup_service import create_full_backup

    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url:
        print("ERROR: DATABASE_URL environment variable is not set.", file=sys.stderr)
        sys.exit(1)

    data_dir = os.environ.get("WORKBENCH_DATA_DIR", "/app/data")

    logger.info("Starting full-system backup (output: %s)...", output_dir)
    result = create_full_backup(
        database_url=database_url,
        data_dir=data_dir,
        output_dir=output_dir,
        description=description,
    )

    if result.success:
        print(f"Backup created successfully: {result.archive_path}")
        print(f"  Archive size:  {result.archive_size_bytes:,} bytes")
        print(f"  DB dump size:  {result.pg_dump_size_bytes:,} bytes")
        print(f"  Data dir size: {result.data_dir_size_bytes:,} bytes")
    else:
        print(f"ERROR: Backup failed: {result.error_message}", file=sys.stderr)
        sys.exit(1)


def _restore_command(archive_path: str) -> None:
    """CLI handler: restore a full-system backup."""
    import os
    import sys

    from workbench.services.backup_service import restore_full_backup

    if not os.path.exists(archive_path):
        print(f"ERROR: Archive not found: {archive_path}", file=sys.stderr)
        sys.exit(1)

    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url:
        print("ERROR: DATABASE_URL environment variable is not set.", file=sys.stderr)
        sys.exit(1)

    data_dir = os.environ.get("WORKBENCH_DATA_DIR", "/app/data")

    print(f"WARNING: This will OVERWRITE the current database and data directory!")
    print(f"  Database: all existing tables will be dropped and recreated.")
    print(f"  Data dir: {data_dir} will be replaced.")
    print(f"  Archive:  {archive_path}")
    print()
    response = input("Type 'yes' to confirm: ")
    if response.strip().lower() != "yes":
        print("Aborted.")
        return

    logger.info("Starting restore from: %s", archive_path)
    result = restore_full_backup(
        archive_path=archive_path,
        database_url=database_url,
        data_dir=data_dir,
    )

    if result.success:
        print("Restore completed successfully.")
        print(f"  Tables restored: {result.tables_restored}")
        print(f"  Data files restored: {result.data_files_restored}")
    else:
        print(f"ERROR: Restore failed: {result.error_message}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
