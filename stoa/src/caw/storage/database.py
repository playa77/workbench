"""Database connection and migration management."""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import TYPE_CHECKING, Any

import aiosqlite

from caw.errors import StorageError

if TYPE_CHECKING:
    from caw.core.config import StorageConfig


class Database:
    """Manages SQLite connection lifecycle and migrations."""

    def __init__(self, config: StorageConfig) -> None:
        self._config = config
        self._connection: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        """Open database connection and apply pragmas."""
        db_path = Path(self._config.db_path)
        if db_path != Path(":memory:"):
            db_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._connection = await aiosqlite.connect(str(db_path))
            self._connection.row_factory = aiosqlite.Row
            await self._connection.execute("PRAGMA journal_mode=WAL")
            await self._connection.execute("PRAGMA synchronous=NORMAL")
            await self._connection.execute("PRAGMA cache_size=-64000")
            await self._connection.execute("PRAGMA foreign_keys=ON")
            await self._connection.commit()
        except Exception as exc:
            raise StorageError(
                message=f"Failed to connect to database at {db_path}",
                code="storage_connect_failed",
                details={"path": str(db_path)},
            ) from exc

    async def close(self) -> None:
        """Close database connection gracefully."""
        if self._connection is None:
            return
        await self._connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        await self._connection.close()
        self._connection = None

    def connection(self) -> aiosqlite.Connection:
        """Return active connection."""
        if self._connection is None:
            raise StorageError(
                message="Database connection requested before connect().",
                code="storage_not_connected",
            )
        return self._connection

    async def run_migrations(self) -> list[str]:
        """Run all pending migrations in order."""
        conn = self.connection()
        await conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_version ("
            "version TEXT PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT (datetime('now')), "
            "description TEXT)"
        )
        await conn.commit()

        cursor = await conn.execute("SELECT version FROM schema_version")
        rows = await cursor.fetchall()
        applied = {str(row["version"]) for row in rows}

        migration_modules = self._discover_migrations()
        newly_applied: list[str] = []
        for module in migration_modules:
            version = self._migration_version(module)
            if version in applied:
                continue
            try:
                await conn.execute("BEGIN")
                await module.up(conn)
                await conn.execute(
                    "INSERT INTO schema_version (version, description) VALUES (?, ?)",
                    (version, getattr(module, "DESCRIPTION", "")),
                )
                await conn.commit()
                newly_applied.append(version)
            except Exception as exc:
                await conn.rollback()
                raise StorageError(
                    message=f"Migration {version} failed",
                    code="storage_migration_failed",
                ) from exc
        return newly_applied

    def _discover_migrations(self) -> list[Any]:
        migrations_dir = Path(__file__).parent / "migrations"
        modules: list[Any] = []
        for migration_file in sorted(migrations_dir.glob("[0-9][0-9][0-9]_*.py")):
            module_name = f"caw.storage.migrations.{migration_file.stem}"
            modules.append(importlib.import_module(module_name))
        return modules

    def _migration_version(self, module: Any) -> str:
        module_name = module.__name__.split(".")[-1]
        return module_name.split("_", maxsplit=1)[0]
