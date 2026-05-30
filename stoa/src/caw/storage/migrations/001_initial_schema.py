"""Initial database schema for CAW."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import aiosqlite

VERSION = "0.1.0"
DESCRIPTION = (
    "Initial schema: sessions, messages, artifacts, trace_events, sources, citations, eval_runs, "
    "checkpoints"
)


async def up(conn: aiosqlite.Connection) -> None:
    """Apply migration: create initial schema tables and indexes."""
    await conn.executescript(
        """
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    state TEXT NOT NULL,
    mode TEXT NOT NULL,
    parent_id TEXT REFERENCES sessions(id),
    config_json TEXT,
    active_skills TEXT,
    active_pack TEXT,
    metadata_json TEXT
);
CREATE INDEX idx_sessions_state ON sessions(state);
CREATE INDEX idx_sessions_mode ON sessions(mode);
CREATE INDEX idx_sessions_updated ON sessions(updated_at);

CREATE TABLE messages (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    sequence_num INTEGER NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    model TEXT,
    provider TEXT,
    token_count_in INTEGER,
    token_count_out INTEGER,
    created_at TEXT NOT NULL,
    metadata_json TEXT
);
CREATE INDEX idx_messages_session ON messages(session_id, sequence_num);

CREATE TABLE artifacts (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    type TEXT NOT NULL,
    name TEXT NOT NULL,
    path TEXT,
    content TEXT,
    content_hash TEXT,
    created_at TEXT NOT NULL,
    metadata_json TEXT
);
CREATE INDEX idx_artifacts_session ON artifacts(session_id);
CREATE INDEX idx_artifacts_type ON artifacts(type);

CREATE TABLE trace_events (
    id TEXT PRIMARY KEY,
    trace_id TEXT NOT NULL,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    timestamp TEXT NOT NULL,
    event_type TEXT NOT NULL,
    data_json TEXT NOT NULL,
    parent_event_id TEXT REFERENCES trace_events(id)
);
CREATE INDEX idx_trace_session ON trace_events(session_id);
CREATE INDEX idx_trace_trace_id ON trace_events(trace_id);
CREATE INDEX idx_trace_type ON trace_events(event_type);
CREATE INDEX idx_trace_timestamp ON trace_events(timestamp);

CREATE TABLE sources (
    id TEXT PRIMARY KEY,
    session_id TEXT REFERENCES sessions(id),
    type TEXT NOT NULL,
    uri TEXT,
    title TEXT,
    content TEXT,
    content_hash TEXT,
    embedding BLOB,
    created_at TEXT NOT NULL,
    metadata_json TEXT
);
CREATE INDEX idx_sources_session ON sources(session_id);
CREATE INDEX idx_sources_hash ON sources(content_hash);

CREATE TABLE citations (
    id TEXT PRIMARY KEY,
    message_id TEXT NOT NULL REFERENCES messages(id),
    source_id TEXT NOT NULL REFERENCES sources(id),
    claim TEXT NOT NULL,
    excerpt TEXT,
    confidence REAL,
    location TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX idx_citations_message ON citations(message_id);
CREATE INDEX idx_citations_source ON citations(source_id);

CREATE TABLE eval_runs (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    skill_pack TEXT,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL,
    scores_json TEXT,
    trace_id TEXT,
    metadata_json TEXT
);
CREATE INDEX idx_eval_task ON eval_runs(task_id);
CREATE INDEX idx_eval_provider ON eval_runs(provider, model);

CREATE TABLE checkpoints (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    created_at TEXT NOT NULL,
    state_json TEXT NOT NULL,
    message_index INTEGER NOT NULL,
    description TEXT
);
CREATE INDEX idx_checkpoints_session ON checkpoints(session_id);
"""
    )


async def down(conn: aiosqlite.Connection) -> None:
    """Reverse migration by dropping all created tables."""
    await conn.executescript(
        """
DROP TABLE IF EXISTS checkpoints;
DROP TABLE IF EXISTS eval_runs;
DROP TABLE IF EXISTS citations;
DROP TABLE IF EXISTS sources;
DROP TABLE IF EXISTS trace_events;
DROP TABLE IF EXISTS artifacts;
DROP TABLE IF EXISTS messages;
DROP TABLE IF EXISTS sessions;
"""
    )
