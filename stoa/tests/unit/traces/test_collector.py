from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from caw.models import Session, SessionMode, TraceEvent
from caw.storage.repository import SessionRepository, TraceEventRepository
from caw.traces.collector import TraceCollector

if TYPE_CHECKING:
    from caw.storage.database import Database


async def _create_session(db: Database, session_id: str = "session-1") -> None:
    repo = SessionRepository(db)
    await repo.create(Session(id=session_id, mode=SessionMode.CHAT))


def _event(trace_id: str, session_id: str, event_type: str, at: datetime) -> TraceEvent:
    return TraceEvent(trace_id=trace_id, session_id=session_id, event_type=event_type, timestamp=at)


async def test_emit_buffers(db: Database) -> None:
    await _create_session(db)
    repo = TraceEventRepository(db)
    collector = TraceCollector(repo, flush_threshold=100)

    await collector.emit(_event("t1", "session-1", "session:created", datetime.now(UTC)))

    stored = await repo.get_by_trace_id("t1")
    assert stored == []


async def test_flush_persists(db: Database) -> None:
    await _create_session(db)
    repo = TraceEventRepository(db)
    collector = TraceCollector(repo)

    await collector.emit(_event("t1", "session-1", "session:created", datetime.now(UTC)))
    await collector.flush()

    stored = await repo.get_by_trace_id("t1")
    assert len(stored) == 1


async def test_auto_flush_on_threshold(db: Database) -> None:
    await _create_session(db)
    repo = TraceEventRepository(db)
    collector = TraceCollector(repo, flush_threshold=5)

    now = datetime.now(UTC)
    for index in range(5):
        await collector.emit(
            _event("t1", "session-1", f"event:{index}", now + timedelta(seconds=index))
        )

    stored = await repo.get_by_trace_id("t1")
    assert len(stored) == 5


async def test_stop_flushes_remaining(db: Database) -> None:
    await _create_session(db)
    repo = TraceEventRepository(db)
    collector = TraceCollector(repo, flush_threshold=10, flush_interval=60)

    await collector.start()
    await collector.emit(_event("t1", "session-1", "session:created", datetime.now(UTC)))
    await collector.stop()

    stored = await repo.get_by_trace_id("t1")
    assert len(stored) == 1


async def test_get_trace(db: Database) -> None:
    await _create_session(db)
    repo = TraceEventRepository(db)
    collector = TraceCollector(repo)

    base = datetime.now(UTC)
    await collector.emit(_event("t1", "session-1", "b", base + timedelta(seconds=2)))
    await collector.emit(_event("t1", "session-1", "a", base + timedelta(seconds=1)))
    await collector.flush()

    events = await collector.get_trace("t1")
    assert [event.event_type for event in events] == ["a", "b"]


async def test_get_session_events_filter(db: Database) -> None:
    await _create_session(db)
    repo = TraceEventRepository(db)
    collector = TraceCollector(repo)

    base = datetime.now(UTC)
    await collector.emit(_event("t1", "session-1", "provider:request", base))
    await collector.emit(_event("t1", "session-1", "tool:invocation", base + timedelta(seconds=1)))
    await collector.emit(_event("t2", "session-1", "provider:request", base + timedelta(seconds=2)))
    await collector.flush()

    events = await collector.get_session_events(
        "session-1",
        event_types=["provider:request"],
        since=base + timedelta(milliseconds=500),
    )
    assert len(events) == 1
    assert events[0].trace_id == "t2"
