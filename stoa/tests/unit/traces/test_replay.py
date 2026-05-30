from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from caw.models import Session, SessionMode, TraceEvent
from caw.storage.repository import SessionRepository, TraceEventRepository
from caw.traces.collector import TraceCollector

if TYPE_CHECKING:
    from caw.storage.database import Database
from caw.traces.replay import ReplayEngine


async def _create_session(db: Database, session_id: str = "session-1") -> None:
    repo = SessionRepository(db)
    await repo.create(Session(id=session_id, mode=SessionMode.CHAT))


def _event(trace_id: str, session_id: str, event_type: str, at: datetime) -> TraceEvent:
    return TraceEvent(trace_id=trace_id, session_id=session_id, event_type=event_type, timestamp=at)


async def test_timeline_order(db: Database) -> None:
    await _create_session(db)
    collector = TraceCollector(TraceEventRepository(db))
    replay = ReplayEngine(collector)
    base = datetime.now(UTC)

    await collector.emit(_event("t1", "session-1", "b", base + timedelta(seconds=2)))
    await collector.emit(_event("t1", "session-1", "a", base + timedelta(seconds=1)))
    await collector.flush()

    timeline = await replay.timeline("t1")
    assert [event.event_type for event in timeline] == ["a", "b"]


async def test_timeline_filter(db: Database) -> None:
    await _create_session(db)
    collector = TraceCollector(TraceEventRepository(db))
    replay = ReplayEngine(collector)
    base = datetime.now(UTC)

    await collector.emit(_event("t1", "session-1", "provider:request", base))
    await collector.emit(_event("t1", "session-1", "tool:invocation", base + timedelta(seconds=1)))
    await collector.flush()

    timeline = await replay.timeline("t1", event_types=["tool:invocation"])
    assert len(timeline) == 1
    assert timeline[0].event_type == "tool:invocation"


async def test_summary_counts(db: Database) -> None:
    await _create_session(db)
    collector = TraceCollector(TraceEventRepository(db))
    replay = ReplayEngine(collector)
    base = datetime.now(UTC)

    await collector.emit(
        TraceEvent(
            trace_id="t1",
            session_id="session-1",
            event_type="session:created",
            timestamp=base,
            data={"mode": "chat", "skills": []},
        )
    )
    await collector.emit(_event("t1", "session-1", "provider:request", base + timedelta(seconds=1)))
    await collector.emit(_event("t1", "session-1", "tool:invocation", base + timedelta(seconds=2)))
    await collector.emit(_event("t1", "session-1", "provider:error", base + timedelta(seconds=3)))
    await collector.flush()

    summary = await replay.summary("t1")
    assert summary.provider_calls == 1
    assert summary.tool_calls == 1
    assert summary.errors == 1


async def test_summary_duration(db: Database) -> None:
    await _create_session(db)
    collector = TraceCollector(TraceEventRepository(db))
    replay = ReplayEngine(collector)
    base = datetime.now(UTC)

    await collector.emit(_event("t1", "session-1", "session:created", base))
    await collector.emit(
        _event("t1", "session-1", "tool:result", base + timedelta(milliseconds=1500))
    )
    await collector.flush()

    summary = await replay.summary("t1")
    assert summary.duration_ms == 1500


async def test_diff_unique_events(db: Database) -> None:
    await _create_session(db)
    collector = TraceCollector(TraceEventRepository(db))
    replay = ReplayEngine(collector)
    base = datetime.now(UTC)

    common = TraceEvent(
        trace_id="ta",
        session_id="session-1",
        event_type="session:created",
        timestamp=base,
        data={"mode": "chat", "skills": []},
    )
    await collector.emit(common)
    await collector.emit(_event("ta", "session-1", "provider:request", base + timedelta(seconds=1)))

    common_b = TraceEvent(
        trace_id="tb",
        session_id="session-1",
        event_type="session:created",
        timestamp=base,
        data={"mode": "chat", "skills": []},
    )
    await collector.emit(common_b)
    await collector.emit(_event("tb", "session-1", "tool:invocation", base + timedelta(seconds=1)))
    await collector.flush()

    diff = await replay.diff("ta", "tb")
    assert [event.event_type for event in diff.events_only_in_a] == ["provider:request"]
    assert [event.event_type for event in diff.events_only_in_b] == ["tool:invocation"]
