import pytest

from caw.core.config import WorkspaceConfig
from caw.core.permissions import PermissionGate
from caw.models import PermissionLevel
from caw.storage.database import Database
from caw.storage.repository import TraceEventRepository
from caw.traces.collector import TraceCollector


@pytest.mark.asyncio
async def test_read_no_approval(db: Database) -> None:
    collector = TraceCollector(TraceEventRepository(db), flush_threshold=1)
    gate = PermissionGate(WorkspaceConfig(confirm_writes=True, confirm_executions=True), collector)
    approval = await gate.check(PermissionLevel.READ, "read", ["a"], "t1", "s1")
    assert approval is None


@pytest.mark.asyncio
async def test_delete_always_approval(db: Database) -> None:
    collector = TraceCollector(TraceEventRepository(db), flush_threshold=1)
    gate = PermissionGate(
        WorkspaceConfig(confirm_writes=False, confirm_executions=False), collector
    )
    approval = await gate.check(PermissionLevel.DELETE, "delete", ["a"], "t1", "s1")
    assert approval is not None
    assert approval.permission_level is PermissionLevel.DELETE


@pytest.mark.asyncio
async def test_write_configurable(db: Database) -> None:
    collector = TraceCollector(TraceEventRepository(db), flush_threshold=1)
    gated = PermissionGate(
        WorkspaceConfig(confirm_writes=True, confirm_executions=False), collector
    )
    open_gate = PermissionGate(
        WorkspaceConfig(confirm_writes=False, confirm_executions=False), collector
    )
    assert await gated.check(PermissionLevel.WRITE, "write", [], "t1", "s1") is not None
    assert await open_gate.check(PermissionLevel.WRITE, "write", [], "t2", "s2") is None


@pytest.mark.asyncio
async def test_execute_configurable(db: Database) -> None:
    collector = TraceCollector(TraceEventRepository(db), flush_threshold=1)
    gated = PermissionGate(
        WorkspaceConfig(confirm_writes=False, confirm_executions=True), collector
    )
    open_gate = PermissionGate(
        WorkspaceConfig(confirm_writes=False, confirm_executions=False), collector
    )
    assert await gated.check(PermissionLevel.EXECUTE, "exec", [], "t1", "s1") is not None
    assert await open_gate.check(PermissionLevel.EXECUTE, "exec", [], "t2", "s2") is None


@pytest.mark.asyncio
async def test_trace_event_emitted(db: Database) -> None:
    repository = TraceEventRepository(db)
    collector = TraceCollector(repository, flush_threshold=1)
    gate = PermissionGate(WorkspaceConfig(confirm_writes=True, confirm_executions=True), collector)
    approval = await gate.check(PermissionLevel.WRITE, "write", ["file"], "trace-1", "session-1")
    assert approval is not None

    events = await repository.get_by_trace_id("trace-1")
    assert len(events) == 1
    assert events[0].event_type == "gate:approval_required"
