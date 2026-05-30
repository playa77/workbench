"""Alembic migration environment.

Uses the workbench async engine for online migrations.
Call ``alembic_setup_db(config)`` before running migrations to initialize the engine.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from workbench.core.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    from sqlalchemy.ext.asyncio import AsyncEngine

    from workbench.core.db import get_engine

    connectable = get_engine()
    is_async = isinstance(connectable, AsyncEngine)

    if is_async:
        import asyncio

        async def _run_async_migrations() -> None:
            async with connectable.connect() as connection:
                await connection.run_sync(_do_run_migrations)
            await connectable.dispose()

        asyncio.run(_run_async_migrations())
    else:
        with connectable.connect() as connection:
            _do_run_migrations(connection)


def _do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations(config: object | None = None) -> None:
    """Entry point for programmatic migration invocation."""
    if context.is_offline_mode():
        run_migrations_offline()
    else:
        run_migrations_online()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
