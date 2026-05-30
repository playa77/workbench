from collections.abc import AsyncIterator

import pytest_asyncio

from caw.core.config import StorageConfig
from caw.storage.database import Database


@pytest_asyncio.fixture
async def db() -> AsyncIterator[Database]:
    database = Database(
        StorageConfig(db_path=":memory:", trace_dir="/tmp/t", artifact_dir="/tmp/a")
    )
    await database.connect()
    await database.run_migrations()
    yield database
    await database.close()
