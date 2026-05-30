from pathlib import Path

import pytest

from caw.capabilities.workspace.writes import WorkspaceWriter
from caw.core.config import WorkspaceConfig
from caw.core.permissions import PermissionGate
from caw.storage.database import Database
from caw.storage.repository import TraceEventRepository
from caw.traces.collector import TraceCollector


@pytest.mark.asyncio
async def test_write_file(tmp_path: Path, db: Database) -> None:
    config = WorkspaceConfig(
        sandbox_mode="strict", allowed_paths=[str(tmp_path)], confirm_writes=False
    )
    collector = TraceCollector(TraceEventRepository(db), flush_threshold=1)
    writer = WorkspaceWriter(config, collector, PermissionGate(config, collector))
    path = tmp_path / "write.txt"
    await writer.write_file(str(path), "hello", "s1", "t1")
    assert path.read_text(encoding="utf-8") == "hello"


@pytest.mark.asyncio
async def test_move_file(tmp_path: Path, db: Database) -> None:
    config = WorkspaceConfig(
        sandbox_mode="strict", allowed_paths=[str(tmp_path)], confirm_writes=False
    )
    collector = TraceCollector(TraceEventRepository(db), flush_threshold=1)
    writer = WorkspaceWriter(config, collector, PermissionGate(config, collector))
    src = tmp_path / "src.txt"
    dst = tmp_path / "dst.txt"
    src.write_text("data", encoding="utf-8")
    await writer.move_file(str(src), str(dst), "s1", "t1")
    assert not src.exists()
    assert dst.exists()


@pytest.mark.asyncio
async def test_copy_file(tmp_path: Path, db: Database) -> None:
    config = WorkspaceConfig(
        sandbox_mode="strict", allowed_paths=[str(tmp_path)], confirm_writes=False
    )
    collector = TraceCollector(TraceEventRepository(db), flush_threshold=1)
    writer = WorkspaceWriter(config, collector, PermissionGate(config, collector))
    src = tmp_path / "src.txt"
    dst = tmp_path / "copy.txt"
    src.write_text("data", encoding="utf-8")
    await writer.copy_file(str(src), str(dst), "s1", "t1")
    assert src.exists()
    assert dst.read_text(encoding="utf-8") == "data"


@pytest.mark.asyncio
async def test_delete_file(tmp_path: Path, db: Database) -> None:
    config = WorkspaceConfig(
        sandbox_mode="strict",
        allowed_paths=[str(tmp_path)],
        confirm_writes=False,
        confirm_deletes=False,
    )
    collector = TraceCollector(TraceEventRepository(db), flush_threshold=1)
    writer = WorkspaceWriter(config, collector, PermissionGate(config, collector))
    target = tmp_path / "trash.txt"
    target.write_text("data", encoding="utf-8")

    # Delete is intentionally always gated by PermissionGate; disable by monkeypatching behavior.
    writer._gate.requires_approval = lambda level: False  # type: ignore[method-assign]
    await writer.delete_file(str(target), "s1", "t1")
    assert not target.exists()


@pytest.mark.asyncio
async def test_mutations_emit_trace_events(tmp_path: Path, db: Database) -> None:
    config = WorkspaceConfig(
        sandbox_mode="strict", allowed_paths=[str(tmp_path)], confirm_writes=False
    )
    repository = TraceEventRepository(db)
    collector = TraceCollector(repository, flush_threshold=1)
    writer = WorkspaceWriter(config, collector, PermissionGate(config, collector))
    target = tmp_path / "trace.txt"
    await writer.write_file(str(target), "x", "s1", "trace-write")

    events = await repository.get_by_trace_id("trace-write")
    assert len(events) == 1
    assert events[0].event_type == "workspace:write"
