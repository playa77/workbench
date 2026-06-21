"""Tests for shared.db.session — init_db, close_db, get_engine, get_session_factory, get_session."""

import pytest

from workbench.shared.db import session as db_session_mod
from workbench.shared.db.session import (
    DatabaseConfig,
    close_db,
    get_engine,
    get_session,
    get_session_factory,
    init_db,
)


@pytest.fixture(autouse=True)
def _reset_db_globals():
    """Reset shared DB module globals between tests."""
    db_session_mod._engine = None
    db_session_mod._session_factory = None
    yield
    db_session_mod._engine = None
    db_session_mod._session_factory = None


def test_database_config_defaults():
    cfg = DatabaseConfig()
    assert cfg.url == ""
    assert cfg.pool_size == 10
    assert cfg.echo is False


def test_init_db_sqlite():
    cfg = DatabaseConfig(url="sqlite+aiosqlite:///:memory:", echo=False)
    init_db(cfg)
    engine = get_engine()
    assert engine is not None
    factory = get_session_factory()
    assert factory is not None


def test_get_engine_before_init_raises():
    with pytest.raises(RuntimeError, match="not initialized"):
        get_engine()


def test_get_session_factory_before_init_raises():
    with pytest.raises(RuntimeError, match="not initialized"):
        get_session_factory()


@pytest.mark.asyncio
async def test_get_session_yields_session():
    cfg = DatabaseConfig(url="sqlite+aiosqlite:///:memory:", echo=False)
    init_db(cfg)
    gen = get_session()
    session = await gen.__anext__()
    assert session is not None
    await gen.aclose()


@pytest.mark.asyncio
async def test_close_db():
    cfg = DatabaseConfig(url="sqlite+aiosqlite:///:memory:", echo=False)
    init_db(cfg)
    await close_db()
    with pytest.raises(RuntimeError):
        get_engine()


def test_init_db_empty_url_uses_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    cfg = DatabaseConfig(url="")
    init_db(cfg)
    engine = get_engine()
    assert engine is not None
