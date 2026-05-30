"""Async database session factory.

Supports PostgreSQL (via asyncpg) and SQLite (via aiosqlite) as a fallback for local testing.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from workbench.core.config import WorkbenchConfig

_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _build_engine(database_url: str):
    if database_url.startswith("sqlite"):
        return create_async_engine(
            database_url,
            connect_args={"check_same_thread": False},
        )
    return create_async_engine(
        database_url,
        pool_size=10,
        max_overflow=0,
        pool_timeout=30,
        pool_recycle=3600,
    )


def init_db(config: WorkbenchConfig) -> None:
    global _engine, _session_factory
    db_url = config.database_url

    if not db_url:
        import os
        db_url = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///data/workbench.db")

    try:
        import aiosqlite  # noqa: F401
    except ImportError:
        db_url = db_url.replace("sqlite+aiosqlite:", "sqlite+aiosqlite:")

    _engine = _build_engine(db_url)
    _session_factory = async_sessionmaker(
        bind=_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    if _session_factory is None:
        raise RuntimeError("Database not initialized — call init_db() first")
    return _session_factory


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
        finally:
            await session.close()


async def close_db() -> None:
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None
