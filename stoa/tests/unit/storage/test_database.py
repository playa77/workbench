from pathlib import Path

import pytest

from caw.core.config import StorageConfig
from caw.errors import StorageError
from caw.storage.database import Database


@pytest.mark.asyncio
async def test_connect_creates_file(tmp_path: Path) -> None:
    db_file = tmp_path / "caw.db"
    db = Database(StorageConfig(db_path=str(db_file), trace_dir="/tmp/t", artifact_dir="/tmp/a"))
    await db.connect()
    assert db_file.exists()
    await db.close()


@pytest.mark.asyncio
async def test_connect_creates_parent_dirs(tmp_path: Path) -> None:
    db_file = tmp_path / "nested" / "dir" / "caw.db"
    db = Database(StorageConfig(db_path=str(db_file), trace_dir="/tmp/t", artifact_dir="/tmp/a"))
    await db.connect()
    assert db_file.parent.exists()
    await db.close()


@pytest.mark.asyncio
async def test_pragmas_applied(db: Database) -> None:
    conn = db.connection()
    jm = await (await conn.execute("PRAGMA journal_mode")).fetchone()
    fk = await (await conn.execute("PRAGMA foreign_keys")).fetchone()
    assert str(jm[0]).lower() == "memory" or str(jm[0]).lower() == "wal"
    assert int(fk[0]) == 1


@pytest.mark.asyncio
async def test_run_migrations_initial(db: Database) -> None:
    conn = db.connection()
    rows = await (
        await conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sessions'")
    ).fetchall()
    assert rows


@pytest.mark.asyncio
async def test_run_migrations_idempotent(db: Database) -> None:
    first = await db.run_migrations()
    second = await db.run_migrations()
    assert first == []
    assert second == []


@pytest.mark.asyncio
async def test_close_no_error(db: Database) -> None:
    await db.close()


def test_connection_before_connect_raises() -> None:
    db = Database(StorageConfig(db_path=":memory:", trace_dir="/tmp/t", artifact_dir="/tmp/a"))
    with pytest.raises(StorageError):
        db.connection()
