"""Async database session factory — compatibility shim.

Delegates to workbench.shared.db.session for the canonical implementation.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from workbench.core.config import WorkbenchConfig
from workbench.shared.db.session import (
    DatabaseConfig,
    close_db,
    get_engine,
    get_session,
    get_session_factory,
    init_db as _init_shared_db,
)

__all__ = ["close_db", "get_session", "get_session_factory", "init_db", "get_engine"]


def init_db(config: WorkbenchConfig) -> None:
    db_cfg = DatabaseConfig(
        url=config.database_url or "",
        echo=(config.log_level == "DEBUG"),
    )
    _init_shared_db(db_cfg)
