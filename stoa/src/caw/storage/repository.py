"""Data access repositories for all core models."""

from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING, Any

from caw.models import (
    Artifact,
    ArtifactType,
    CheckpointRef,
    Citation,
    EvalRun,
    Message,
    MessageRole,
    Session,
    SessionMode,
    SessionState,
    Source,
    TraceEvent,
)

if TYPE_CHECKING:
    from caw.storage.database import Database


def _to_iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _from_iso(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value is not None else None


def _json_dump(value: Any) -> str | None:
    return json.dumps(value) if value is not None else None


def _json_load(value: str | None, default: Any) -> Any:
    return json.loads(value) if value is not None else default


class SessionRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def create(self, session: Session) -> Session:
        conn = self._db.connection()
        await conn.execute(
            "INSERT INTO sessions (id, created_at, updated_at, state, mode, parent_id, config_json, "  # noqa: E501
            "active_skills, active_pack, metadata_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                session.id,
                _to_iso(session.created_at),
                _to_iso(session.updated_at),
                session.state.value,
                session.mode.value,
                session.parent_id,
                _json_dump(session.config_overrides),
                _json_dump(session.active_skills),
                session.active_skill_pack,
                _json_dump(session.metadata),
            ),
        )
        await conn.commit()
        return session

    async def get(self, session_id: str) -> Session | None:
        conn = self._db.connection()
        cursor = await conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,))
        row = await cursor.fetchone()
        return _session_from_row(row) if row else None

    async def update(self, session: Session) -> Session:
        conn = self._db.connection()
        await conn.execute(
            "UPDATE sessions SET updated_at = ?, state = ?, mode = ?, parent_id = ?, config_json = ?, "  # noqa: E501
            "active_skills = ?, active_pack = ?, metadata_json = ? WHERE id = ?",
            (
                _to_iso(session.updated_at),
                session.state.value,
                session.mode.value,
                session.parent_id,
                _json_dump(session.config_overrides),
                _json_dump(session.active_skills),
                session.active_skill_pack,
                _json_dump(session.metadata),
                session.id,
            ),
        )
        await conn.commit()
        return session

    async def delete(self, session_id: str) -> None:
        conn = self._db.connection()
        await conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        await conn.commit()

    async def list_by_state(
        self, state: SessionState, limit: int = 50, cursor: str | None = None
    ) -> list[Session]:
        conn = self._db.connection()
        if cursor:
            query = (
                "SELECT * FROM sessions WHERE state = ? AND updated_at < ? "
                "ORDER BY updated_at DESC LIMIT ?"
            )
            params: tuple[object, ...] = (state.value, cursor, limit)
        else:
            query = "SELECT * FROM sessions WHERE state = ? ORDER BY updated_at DESC LIMIT ?"
            params = (state.value, limit)
        rows = await (await conn.execute(query, params)).fetchall()
        return [_session_from_row(row) for row in rows]

    async def list_by_mode(
        self, mode: SessionMode, limit: int = 50, cursor: str | None = None
    ) -> list[Session]:
        conn = self._db.connection()
        if cursor:
            query = (
                "SELECT * FROM sessions WHERE mode = ? AND updated_at < ? "
                "ORDER BY updated_at DESC LIMIT ?"
            )
            params: tuple[object, ...] = (mode.value, cursor, limit)
        else:
            query = "SELECT * FROM sessions WHERE mode = ? ORDER BY updated_at DESC LIMIT ?"
            params = (mode.value, limit)
        rows = await (await conn.execute(query, params)).fetchall()
        return [_session_from_row(row) for row in rows]

    async def list_recent(self, limit: int = 50, cursor: str | None = None) -> list[Session]:
        conn = self._db.connection()
        if cursor:
            rows = await (
                await conn.execute(
                    "SELECT * FROM sessions WHERE updated_at < ? ORDER BY updated_at DESC LIMIT ?",
                    (cursor, limit),
                )
            ).fetchall()
        else:
            rows = await (
                await conn.execute(
                    "SELECT * FROM sessions ORDER BY updated_at DESC LIMIT ?", (limit,)
                )
            ).fetchall()
        return [_session_from_row(row) for row in rows]


class MessageRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def create(self, message: Message) -> Message:
        conn = self._db.connection()
        await conn.execute(
            (
                "INSERT INTO messages ("
                "id, session_id, sequence_num, role, content, model, provider, "
                "token_count_in, token_count_out, created_at, metadata_json"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
            ),
            (
                message.id,
                message.session_id,
                message.sequence_num,
                message.role.value,
                message.content,
                message.model,
                message.provider,
                message.token_count_in,
                message.token_count_out,
                _to_iso(message.created_at),
                _json_dump(message.metadata),
            ),
        )
        await conn.commit()
        return message

    async def get(self, message_id: str) -> Message | None:
        conn = self._db.connection()
        row = await (
            await conn.execute("SELECT * FROM messages WHERE id = ?", (message_id,))
        ).fetchone()
        return _message_from_row(row) if row else None

    async def list_by_session(self, session_id: str, limit: int | None = None) -> list[Message]:
        conn = self._db.connection()
        if limit is None:
            query = "SELECT * FROM messages WHERE session_id = ? ORDER BY sequence_num ASC"
            params: tuple[object, ...] = (session_id,)
        else:
            query = "SELECT * FROM messages WHERE session_id = ? ORDER BY sequence_num ASC LIMIT ?"
            params = (session_id, limit)
        rows = await (await conn.execute(query, params)).fetchall()
        return [_message_from_row(row) for row in rows]

    async def count_by_session(self, session_id: str) -> int:
        conn = self._db.connection()
        row = await (
            await conn.execute(
                "SELECT COUNT(*) AS count FROM messages WHERE session_id = ?", (session_id,)
            )
        ).fetchone()
        return int(row["count"])

    async def get_last_n(self, session_id: str, n: int) -> list[Message]:
        conn = self._db.connection()
        rows = await (
            await conn.execute(
                "SELECT * FROM messages WHERE session_id = ? ORDER BY sequence_num DESC LIMIT ?",
                (session_id, n),
            )
        ).fetchall()
        return [_message_from_row(row) for row in reversed(rows)]


class ArtifactRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def create(self, artifact: Artifact) -> Artifact:
        conn = self._db.connection()
        await conn.execute(
            "INSERT INTO artifacts (id, session_id, type, name, path, content, content_hash, created_at, metadata_json) "  # noqa: E501
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                artifact.id,
                artifact.session_id,
                artifact.type.value,
                artifact.name,
                artifact.path,
                artifact.content,
                artifact.content_hash,
                _to_iso(artifact.created_at),
                _json_dump(artifact.metadata),
            ),
        )
        await conn.commit()
        return artifact

    async def get(self, artifact_id: str) -> Artifact | None:
        conn = self._db.connection()
        row = await (
            await conn.execute("SELECT * FROM artifacts WHERE id = ?", (artifact_id,))
        ).fetchone()
        return _artifact_from_row(row) if row else None

    async def list_by_session(self, session_id: str) -> list[Artifact]:
        conn = self._db.connection()
        rows = await (
            await conn.execute("SELECT * FROM artifacts WHERE session_id = ?", (session_id,))
        ).fetchall()
        return [_artifact_from_row(row) for row in rows]

    async def list_by_type(self, artifact_type: ArtifactType, limit: int = 50) -> list[Artifact]:
        conn = self._db.connection()
        rows = await (
            await conn.execute(
                "SELECT * FROM artifacts WHERE type = ? LIMIT ?", (artifact_type.value, limit)
            )
        ).fetchall()
        return [_artifact_from_row(row) for row in rows]


class TraceEventRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def create(self, event: TraceEvent) -> TraceEvent:
        conn = self._db.connection()
        await conn.execute(
            "INSERT INTO trace_events (id, trace_id, session_id, timestamp, event_type, data_json, parent_event_id) "  # noqa: E501
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                event.id,
                event.trace_id,
                event.session_id,
                _to_iso(event.timestamp),
                event.event_type,
                _json_dump(event.data),
                event.parent_event_id,
            ),
        )
        await conn.commit()
        return event

    async def create_batch(self, events: list[TraceEvent]) -> None:
        conn = self._db.connection()
        await conn.executemany(
            "INSERT INTO trace_events (id, trace_id, session_id, timestamp, event_type, data_json, parent_event_id) "  # noqa: E501
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    event.id,
                    event.trace_id,
                    event.session_id,
                    _to_iso(event.timestamp),
                    event.event_type,
                    _json_dump(event.data),
                    event.parent_event_id,
                )
                for event in events
            ],
        )
        await conn.commit()

    async def get_by_trace_id(
        self, trace_id: str, event_types: list[str] | None = None
    ) -> list[TraceEvent]:
        conn = self._db.connection()
        query = "SELECT * FROM trace_events WHERE trace_id = ?"
        params: list[object] = [trace_id]
        if event_types:
            placeholders = ", ".join("?" for _ in event_types)
            query += f" AND event_type IN ({placeholders})"
            params.extend(event_types)
        query += " ORDER BY timestamp ASC"
        rows = await (await conn.execute(query, tuple(params))).fetchall()
        return [_trace_event_from_row(row) for row in rows]

    async def get_by_session(
        self,
        session_id: str,
        event_types: list[str] | None = None,
        since: datetime | None = None,
    ) -> list[TraceEvent]:
        conn = self._db.connection()
        query = "SELECT * FROM trace_events WHERE session_id = ?"
        params: list[object] = [session_id]
        if event_types:
            placeholders = ", ".join("?" for _ in event_types)
            query += f" AND event_type IN ({placeholders})"
            params.extend(event_types)
        if since is not None:
            query += " AND timestamp >= ?"
            params.append(_to_iso(since) or "")
        query += " ORDER BY timestamp ASC"
        rows = await (await conn.execute(query, tuple(params))).fetchall()
        return [_trace_event_from_row(row) for row in rows]


class SourceRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def create(self, source: Source) -> Source:
        conn = self._db.connection()
        await conn.execute(
            "INSERT INTO sources (id, session_id, type, uri, title, content, content_hash, created_at, metadata_json) "  # noqa: E501
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                source.id,
                source.session_id,
                source.type,
                source.uri,
                source.title,
                source.content,
                source.content_hash,
                _to_iso(source.created_at),
                _json_dump(source.metadata),
            ),
        )
        await conn.commit()
        return source

    async def get(self, source_id: str) -> Source | None:
        conn = self._db.connection()
        row = await (
            await conn.execute("SELECT * FROM sources WHERE id = ?", (source_id,))
        ).fetchone()
        return _source_from_row(row) if row else None

    async def list_by_session(self, session_id: str) -> list[Source]:
        conn = self._db.connection()
        rows = await (
            await conn.execute("SELECT * FROM sources WHERE session_id = ?", (session_id,))
        ).fetchall()
        return [_source_from_row(row) for row in rows]

    async def find_by_hash(self, content_hash: str) -> Source | None:
        conn = self._db.connection()
        row = await (
            await conn.execute(
                "SELECT * FROM sources WHERE content_hash = ? LIMIT 1", (content_hash,)
            )
        ).fetchone()
        return _source_from_row(row) if row else None


class CitationRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def create(self, citation: Citation) -> Citation:
        conn = self._db.connection()
        await conn.execute(
            "INSERT INTO citations (id, message_id, source_id, claim, excerpt, confidence, location, created_at) "  # noqa: E501
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                citation.id,
                citation.message_id,
                citation.source_id,
                citation.claim,
                citation.excerpt,
                citation.confidence,
                citation.location,
                _to_iso(citation.created_at),
            ),
        )
        await conn.commit()
        return citation

    async def list_by_message(self, message_id: str) -> list[Citation]:
        conn = self._db.connection()
        rows = await (
            await conn.execute("SELECT * FROM citations WHERE message_id = ?", (message_id,))
        ).fetchall()
        return [_citation_from_row(row) for row in rows]

    async def list_by_source(self, source_id: str) -> list[Citation]:
        conn = self._db.connection()
        rows = await (
            await conn.execute("SELECT * FROM citations WHERE source_id = ?", (source_id,))
        ).fetchall()
        return [_citation_from_row(row) for row in rows]


class CheckpointRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def create(self, checkpoint: CheckpointRef, state_json: str) -> CheckpointRef:
        conn = self._db.connection()
        await conn.execute(
            "INSERT INTO checkpoints (id, session_id, created_at, state_json, message_index, description) "  # noqa: E501
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                checkpoint.id,
                checkpoint.session_id,
                _to_iso(checkpoint.created_at),
                state_json,
                checkpoint.message_index,
                checkpoint.description,
            ),
        )
        await conn.commit()
        return checkpoint

    async def get_latest(self, session_id: str) -> tuple[CheckpointRef, str] | None:
        conn = self._db.connection()
        row = await (
            await conn.execute(
                "SELECT * FROM checkpoints WHERE session_id = ? ORDER BY created_at DESC LIMIT 1",
                (session_id,),
            )
        ).fetchone()
        if row is None:
            return None
        return _checkpoint_from_row(row), str(row["state_json"])

    async def list_by_session(self, session_id: str) -> list[CheckpointRef]:
        conn = self._db.connection()
        rows = await (
            await conn.execute(
                "SELECT * FROM checkpoints WHERE session_id = ? ORDER BY created_at ASC",
                (session_id,),
            )
        ).fetchall()
        return [_checkpoint_from_row(row) for row in rows]


class EvalRunRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def create(self, run: EvalRun) -> EvalRun:
        conn = self._db.connection()
        await conn.execute(
            "INSERT INTO eval_runs (id, task_id, provider, model, skill_pack, started_at, completed_at, status, "  # noqa: E501
            "scores_json, trace_id, metadata_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                run.id,
                run.task_id,
                run.provider,
                run.model,
                run.skill_pack,
                _to_iso(run.started_at),
                _to_iso(run.completed_at),
                run.status,
                _json_dump(run.scores),
                run.trace_id,
                _json_dump(run.metadata),
            ),
        )
        await conn.commit()
        return run

    async def get(self, run_id: str) -> EvalRun | None:
        conn = self._db.connection()
        row = await (
            await conn.execute("SELECT * FROM eval_runs WHERE id = ?", (run_id,))
        ).fetchone()
        return _eval_run_from_row(row) if row else None

    async def update(self, run: EvalRun) -> EvalRun:
        conn = self._db.connection()
        await conn.execute(
            (
                "UPDATE eval_runs SET task_id = ?, provider = ?, model = ?, skill_pack = ?, "
                "started_at = ?, completed_at = ?, status = ?, scores_json = ?, "
                "trace_id = ?, metadata_json = ? WHERE id = ?"
            ),
            (
                run.task_id,
                run.provider,
                run.model,
                run.skill_pack,
                _to_iso(run.started_at),
                _to_iso(run.completed_at),
                run.status,
                _json_dump(run.scores),
                run.trace_id,
                _json_dump(run.metadata),
                run.id,
            ),
        )
        await conn.commit()
        return run

    async def list_by_task(self, task_id: str, limit: int = 50) -> list[EvalRun]:
        conn = self._db.connection()
        rows = await (
            await conn.execute(
                "SELECT * FROM eval_runs WHERE task_id = ? LIMIT ?", (task_id, limit)
            )
        ).fetchall()
        return [_eval_run_from_row(row) for row in rows]

    async def list_by_provider(self, provider: str, model: str, limit: int = 50) -> list[EvalRun]:
        conn = self._db.connection()
        rows = await (
            await conn.execute(
                "SELECT * FROM eval_runs WHERE provider = ? AND model = ? LIMIT ?",
                (provider, model, limit),
            )
        ).fetchall()
        return [_eval_run_from_row(row) for row in rows]


def _session_from_row(row: Any) -> Session:
    return Session(
        id=str(row["id"]),
        created_at=_from_iso(str(row["created_at"])) or datetime.min,
        updated_at=_from_iso(str(row["updated_at"])) or datetime.min,
        state=SessionState(str(row["state"])),
        mode=SessionMode(str(row["mode"])),
        parent_id=str(row["parent_id"]) if row["parent_id"] is not None else None,
        config_overrides=_json_load(row["config_json"], {}),
        active_skills=_json_load(row["active_skills"], []),
        active_skill_pack=str(row["active_pack"]) if row["active_pack"] is not None else None,
        metadata=_json_load(row["metadata_json"], {}),
    )


def _message_from_row(row: Any) -> Message:
    return Message(
        id=str(row["id"]),
        session_id=str(row["session_id"]),
        sequence_num=int(row["sequence_num"]),
        role=MessageRole(str(row["role"])),
        content=str(row["content"]),
        model=str(row["model"]) if row["model"] is not None else None,
        provider=str(row["provider"]) if row["provider"] is not None else None,
        token_count_in=int(row["token_count_in"]) if row["token_count_in"] is not None else None,
        token_count_out=int(row["token_count_out"]) if row["token_count_out"] is not None else None,
        created_at=_from_iso(str(row["created_at"])) or datetime.min,
        metadata=_json_load(row["metadata_json"], {}),
    )


def _artifact_from_row(row: Any) -> Artifact:
    return Artifact(
        id=str(row["id"]),
        session_id=str(row["session_id"]),
        type=ArtifactType(str(row["type"])),
        name=str(row["name"]),
        path=str(row["path"]) if row["path"] is not None else None,
        content=str(row["content"]) if row["content"] is not None else None,
        content_hash=str(row["content_hash"]) if row["content_hash"] is not None else None,
        created_at=_from_iso(str(row["created_at"])) or datetime.min,
        metadata=_json_load(row["metadata_json"], {}),
    )


def _trace_event_from_row(row: Any) -> TraceEvent:
    return TraceEvent(
        id=str(row["id"]),
        trace_id=str(row["trace_id"]),
        session_id=str(row["session_id"]),
        timestamp=_from_iso(str(row["timestamp"])) or datetime.min,
        event_type=str(row["event_type"]),
        data=_json_load(row["data_json"], {}),
        parent_event_id=str(row["parent_event_id"]) if row["parent_event_id"] is not None else None,
    )


def _source_from_row(row: Any) -> Source:
    return Source(
        id=str(row["id"]),
        session_id=str(row["session_id"]) if row["session_id"] is not None else None,
        type=str(row["type"]),
        uri=str(row["uri"]) if row["uri"] is not None else None,
        title=str(row["title"]) if row["title"] is not None else None,
        content=str(row["content"]) if row["content"] is not None else None,
        content_hash=str(row["content_hash"]) if row["content_hash"] is not None else None,
        created_at=_from_iso(str(row["created_at"])) or datetime.min,
        metadata=_json_load(row["metadata_json"], {}),
    )


def _citation_from_row(row: Any) -> Citation:
    return Citation(
        id=str(row["id"]),
        message_id=str(row["message_id"]),
        source_id=str(row["source_id"]),
        claim=str(row["claim"]),
        excerpt=str(row["excerpt"]) if row["excerpt"] is not None else None,
        confidence=float(row["confidence"]) if row["confidence"] is not None else None,
        location=str(row["location"]) if row["location"] is not None else None,
        created_at=_from_iso(str(row["created_at"])) or datetime.min,
    )


def _checkpoint_from_row(row: Any) -> CheckpointRef:
    return CheckpointRef(
        id=str(row["id"]),
        session_id=str(row["session_id"]),
        created_at=_from_iso(str(row["created_at"])) or datetime.min,
        message_index=int(row["message_index"]),
        description=str(row["description"]) if row["description"] is not None else None,
    )


def _eval_run_from_row(row: Any) -> EvalRun:
    return EvalRun(
        id=str(row["id"]),
        task_id=str(row["task_id"]),
        provider=str(row["provider"]),
        model=str(row["model"]),
        skill_pack=str(row["skill_pack"]) if row["skill_pack"] is not None else None,
        started_at=_from_iso(str(row["started_at"])) or datetime.min,
        completed_at=_from_iso(str(row["completed_at"])) if row["completed_at"] else None,
        status=str(row["status"]),
        scores=_json_load(row["scores_json"], {}),
        trace_id=str(row["trace_id"]) if row["trace_id"] is not None else None,
        metadata=_json_load(row["metadata_json"], {}),
    )
