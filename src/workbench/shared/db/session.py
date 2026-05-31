"""Shared async database session factory.

Supports PostgreSQL (via asyncpg) and SQLite (via aiosqlite) as a fallback.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

if TYPE_CHECKING:
    pass

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


@dataclass
class DatabaseConfig:
    """Configuration for the shared database session factory.

    Attributes:
        url: Database URL (sqlite://... or postgresql+asyncpg://...).
        pool_size: Maximum number of connections in the pool (PostgreSQL only).
        pool_timeout: Seconds to wait for a connection from the pool.
        pool_recycle: Seconds before a connection is recycled.
        echo: Enable SQLAlchemy engine echo for debugging.
    """

    url: str = ""
    pool_size: int = 10
    pool_timeout: int = 30
    pool_recycle: int = 3600
    echo: bool = False


def _build_engine(config: DatabaseConfig) -> AsyncEngine:
    url = config.url
    if url.startswith("sqlite"):
        try:
            import aiosqlite  # noqa: F401
        except ImportError as exc:
            raise RuntimeError(
                "aiosqlite is required for SQLite support. "
                "Install with: pip install aiosqlite"
            ) from exc
        return create_async_engine(
            url,
            connect_args={"check_same_thread": False},
            echo=config.echo,
        )
    return create_async_engine(
        url,
        pool_size=config.pool_size,
        max_overflow=0,
        pool_timeout=config.pool_timeout,
        pool_recycle=config.pool_recycle,
        echo=config.echo,
    )


def get_engine() -> AsyncEngine:
    if _engine is None:
        raise RuntimeError("Database not initialized -- call init_db() first")
    return _engine


def init_db(config: DatabaseConfig) -> None:
    global _engine, _session_factory
    db_url = config.url
    if not db_url:
        import os
        db_url = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///data/workbench.db")

    config.url = db_url
    _engine = _build_engine(config)
    _session_factory = async_sessionmaker(
        bind=_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    if _session_factory is None:
        raise RuntimeError("Database not initialized -- call init_db() first")
    return _session_factory


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
        finally:
            await session.close()


async def close_db() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
    _session_factory = None
