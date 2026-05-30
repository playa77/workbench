"""Approval request persistence schema."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import aiosqlite

VERSION = "0.1.0"
DESCRIPTION = "Add approval request table"


async def up(conn: aiosqlite.Connection) -> None:
    await conn.executescript(
        """
CREATE TABLE approvals (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    action TEXT NOT NULL,
    permission_level TEXT NOT NULL,
    resources_json TEXT NOT NULL,
    reversible INTEGER NOT NULL,
    preview TEXT,
    timeout_seconds INTEGER NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    resolved_at TEXT,
    resolved_by TEXT,
    reason TEXT
);
CREATE INDEX idx_approvals_status ON approvals(status, created_at);
CREATE INDEX idx_approvals_session ON approvals(session_id, created_at);
"""
    )


async def down(conn: aiosqlite.Connection) -> None:
    await conn.executescript(
        """
DROP TABLE IF EXISTS approvals;
"""
    )
