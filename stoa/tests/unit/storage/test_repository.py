from datetime import timedelta

import pytest

from caw.models import (
    Artifact,
    ArtifactType,
    Citation,
    Message,
    Session,
    SessionMode,
    SessionState,
    Source,
    TraceEvent,
    _utcnow,
)
from caw.storage.database import Database
from caw.storage.repository import (
    ArtifactRepository,
    CitationRepository,
    MessageRepository,
    SessionRepository,
    SourceRepository,
    TraceEventRepository,
)


@pytest.mark.asyncio
async def test_session_create_and_get(db: Database) -> None:
    repo = SessionRepository(db)
    session = Session(state=SessionState.ACTIVE, mode=SessionMode.RESEARCH)
    await repo.create(session)
    fetched = await repo.get(session.id)
    assert fetched is not None
    assert fetched.state == SessionState.ACTIVE


@pytest.mark.asyncio
async def test_session_update(db: Database) -> None:
    repo = SessionRepository(db)
    session = Session()
    await repo.create(session)
    session.state = SessionState.PAUSED
    session.updated_at = _utcnow() + timedelta(seconds=1)
    await repo.update(session)
    fetched = await repo.get(session.id)
    assert fetched is not None
    assert fetched.state == SessionState.PAUSED


@pytest.mark.asyncio
async def test_session_list_by_state(db: Database) -> None:
    repo = SessionRepository(db)
    await repo.create(Session(state=SessionState.ACTIVE))
    await repo.create(Session(state=SessionState.FAILED))
    active = await repo.list_by_state(SessionState.ACTIVE)
    assert len(active) == 1


@pytest.mark.asyncio
async def test_session_list_by_mode(db: Database) -> None:
    repo = SessionRepository(db)
    await repo.create(Session(mode=SessionMode.CHAT))
    await repo.create(Session(mode=SessionMode.RESEARCH))
    found = await repo.list_by_mode(SessionMode.RESEARCH)
    assert len(found) == 1


@pytest.mark.asyncio
async def test_message_ordering(db: Database) -> None:
    srepo = SessionRepository(db)
    mrepo = MessageRepository(db)
    session = Session()
    await srepo.create(session)
    await mrepo.create(Message(session_id=session.id, sequence_num=2, content="b"))
    await mrepo.create(Message(session_id=session.id, sequence_num=1, content="a"))
    messages = await mrepo.list_by_session(session.id)
    assert [m.sequence_num for m in messages] == [1, 2]


@pytest.mark.asyncio
async def test_message_count(db: Database) -> None:
    srepo = SessionRepository(db)
    mrepo = MessageRepository(db)
    session = Session()
    await srepo.create(session)
    for i in range(3):
        await mrepo.create(Message(session_id=session.id, sequence_num=i, content=str(i)))
    assert await mrepo.count_by_session(session.id) == 3


@pytest.mark.asyncio
async def test_artifact_create_and_list(db: Database) -> None:
    srepo = SessionRepository(db)
    arepo = ArtifactRepository(db)
    session = Session()
    await srepo.create(session)
    await arepo.create(Artifact(session_id=session.id, type=ArtifactType.REPORT, name="r"))
    assert len(await arepo.list_by_session(session.id)) == 1


@pytest.mark.asyncio
async def test_trace_event_batch_create(db: Database) -> None:
    srepo = SessionRepository(db)
    trepo = TraceEventRepository(db)
    session = Session()
    await srepo.create(session)
    events = [
        TraceEvent(trace_id="t1", session_id=session.id, event_type="a"),
        TraceEvent(trace_id="t1", session_id=session.id, event_type="b"),
    ]
    await trepo.create_batch(events)
    fetched = await trepo.get_by_trace_id("t1")
    assert len(fetched) == 2


@pytest.mark.asyncio
async def test_trace_event_filter_by_type(db: Database) -> None:
    srepo = SessionRepository(db)
    trepo = TraceEventRepository(db)
    session = Session()
    await srepo.create(session)
    await trepo.create_batch(
        [
            TraceEvent(trace_id="t2", session_id=session.id, event_type="x"),
            TraceEvent(trace_id="t2", session_id=session.id, event_type="y"),
        ]
    )
    filtered = await trepo.get_by_trace_id("t2", event_types=["x"])
    assert len(filtered) == 1


@pytest.mark.asyncio
async def test_source_find_by_hash(db: Database) -> None:
    srepo = SessionRepository(db)
    src_repo = SourceRepository(db)
    session = Session()
    await srepo.create(session)
    source = Source(session_id=session.id, type="text", content_hash="abc")
    await src_repo.create(source)
    assert await src_repo.find_by_hash("abc") is not None


@pytest.mark.asyncio
async def test_source_find_by_hash_not_found(db: Database) -> None:
    src_repo = SourceRepository(db)
    assert await src_repo.find_by_hash("missing") is None


@pytest.mark.asyncio
async def test_citation_roundtrip(db: Database) -> None:
    srepo = SessionRepository(db)
    mrepo = MessageRepository(db)
    src_repo = SourceRepository(db)
    crepo = CitationRepository(db)
    session = Session()
    await srepo.create(session)
    message = await mrepo.create(Message(session_id=session.id, sequence_num=1, content="hello"))
    source = await src_repo.create(Source(session_id=session.id, type="text"))
    citation = Citation(message_id=message.id, source_id=source.id, claim="claim")
    await crepo.create(citation)
    assert len(await crepo.list_by_message(message.id)) == 1
    assert len(await crepo.list_by_source(source.id)) == 1


@pytest.mark.asyncio
async def test_json_field_roundtrip(db: Database) -> None:
    repo = SessionRepository(db)
    session = Session(config_overrides={"a": {"nested": [1, 2]}}, metadata={"x": True})
    await repo.create(session)
    fetched = await repo.get(session.id)
    assert fetched is not None
    assert fetched.config_overrides["a"] == {"nested": [1, 2]}


@pytest.mark.asyncio
async def test_datetime_serialization(db: Database) -> None:
    repo = SessionRepository(db)
    session = Session()
    await repo.create(session)
    fetched = await repo.get(session.id)
    assert fetched is not None
    assert fetched.created_at.tzinfo is not None


@pytest.mark.asyncio
async def test_enum_serialization(db: Database) -> None:
    repo = SessionRepository(db)
    for state in SessionState:
        session = Session(state=state)
        await repo.create(session)
        fetched = await repo.get(session.id)
        assert fetched is not None
        assert fetched.state == state
