"""Add source chunk storage and FTS index for research retrieval."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import aiosqlite

VERSION = "0.2.0"
DESCRIPTION = "Add source_chunks table and FTS5 virtual table for keyword retrieval"


async def up(conn: aiosqlite.Connection) -> None:
    await conn.executescript(
        """
CREATE TABLE source_chunks (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    session_id TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    token_count INTEGER NOT NULL,
    metadata_json TEXT
);
CREATE INDEX idx_source_chunks_source ON source_chunks(source_id);
CREATE INDEX idx_source_chunks_session ON source_chunks(session_id);

CREATE VIRTUAL TABLE source_chunks_fts USING fts5(
    content,
    chunk_id UNINDEXED,
    source_id UNINDEXED,
    session_id UNINDEXED
);
"""
    )


async def down(conn: aiosqlite.Connection) -> None:
    await conn.executescript(
        """
DROP TABLE IF EXISTS source_chunks_fts;
DROP TABLE IF EXISTS source_chunks;
"""
    )
