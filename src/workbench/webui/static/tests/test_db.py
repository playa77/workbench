"""Tests for core.db — init_db compatibility shim."""

import asyncio

import pytest

from workbench.core.config import WorkbenchConfig
from workbench.core.db import close_db, get_engine, init_db


@pytest.mark.asyncio
async def test_init_db_delegates_to_shared(test_config):
    """init_db should create a DatabaseConfig and call _init_shared_db."""
    init_db(test_config)
    engine = get_engine()
    assert engine is not None
    await close_db()
