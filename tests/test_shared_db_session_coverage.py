"""Additional coverage tests for workbench.shared.db.session."""

from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from workbench.shared.db.session import DatabaseConfig, _build_engine


def test_build_engine_missing_aiosqlite():
    """_build_engine raises helpful RuntimeError when aiosqlite is missing."""
    config = DatabaseConfig(url="sqlite+aiosqlite:///test.db")
    with patch.dict("sys.modules", {"aiosqlite": None}):
        with pytest.raises(RuntimeError) as exc_info:
            _build_engine(config)
        assert "aiosqlite" in str(exc_info.value)


def test_build_engine_postgresql():
    """_build_engine creates engine with pool for PostgreSQL URLs."""
    config = DatabaseConfig(url="postgresql+asyncpg://user:pass@localhost/db")
    engine = _build_engine(config)
    assert isinstance(engine, AsyncEngine)
    assert engine.url.drivername == "postgresql+asyncpg"
