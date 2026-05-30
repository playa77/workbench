from pathlib import Path

import pytest

from caw.capabilities.workspace.local import LocalWorkspace
from caw.core.config import WorkspaceConfig
from caw.errors import WorkspaceError
from caw.storage.database import Database
from caw.storage.repository import TraceEventRepository
from caw.traces.collector import TraceCollector


@pytest.mark.asyncio
async def test_list_files(tmp_path: Path, db: Database) -> None:
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    workspace = LocalWorkspace(
        WorkspaceConfig(sandbox_mode="strict", allowed_paths=[str(tmp_path)]),
        TraceCollector(TraceEventRepository(db), flush_threshold=1),
    )

    files = await workspace.list_files(str(tmp_path))
    assert any(Path(item.path).name == "a.txt" for item in files)


@pytest.mark.asyncio
async def test_read_file(tmp_path: Path, db: Database) -> None:
    target = tmp_path / "note.txt"
    target.write_text("hello", encoding="utf-8")
    workspace = LocalWorkspace(
        WorkspaceConfig(sandbox_mode="strict", allowed_paths=[str(tmp_path)]),
        TraceCollector(TraceEventRepository(db), flush_threshold=1),
    )

    result = await workspace.read_file(str(target))
    assert result.content == "hello"


@pytest.mark.asyncio
async def test_search_files(tmp_path: Path, db: Database) -> None:
    (tmp_path / "a.md").write_text("a", encoding="utf-8")
    (tmp_path / "b.txt").write_text("b", encoding="utf-8")
    workspace = LocalWorkspace(
        WorkspaceConfig(sandbox_mode="strict", allowed_paths=[str(tmp_path)]),
        TraceCollector(TraceEventRepository(db), flush_threshold=1),
    )

    result = await workspace.search_files("*.md", str(tmp_path))
    assert len(result) == 1
    assert result[0].path.endswith("a.md")


@pytest.mark.asyncio
async def test_path_validation_strict(tmp_path: Path, db: Database) -> None:
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("nope", encoding="utf-8")
    workspace = LocalWorkspace(
        WorkspaceConfig(sandbox_mode="strict", allowed_paths=[str(tmp_path)]),
        TraceCollector(TraceEventRepository(db), flush_threshold=1),
    )

    with pytest.raises(WorkspaceError):
        await workspace.read_file(str(outside))


@pytest.mark.asyncio
async def test_path_validation_permissive(tmp_path: Path, db: Database) -> None:
    outside = tmp_path.parent / "outside-perm.txt"
    outside.write_text("ok", encoding="utf-8")
    workspace = LocalWorkspace(
        WorkspaceConfig(sandbox_mode="permissive", allowed_paths=[str(tmp_path)]),
        TraceCollector(TraceEventRepository(db), flush_threshold=1),
    )

    result = await workspace.read_file(str(outside))
    assert result.content == "ok"


@pytest.mark.asyncio
async def test_trace_event_emitted(tmp_path: Path, db: Database) -> None:
    target = tmp_path / "trace.txt"
    target.write_text("x", encoding="utf-8")
    repository = TraceEventRepository(db)
    collector = TraceCollector(repository, flush_threshold=1)
    workspace = LocalWorkspace(
        WorkspaceConfig(sandbox_mode="strict", allowed_paths=[str(tmp_path)]),
        collector,
    )

    await workspace.read_file(str(target), trace_id="trace-local", session_id="s1")
    events = await repository.get_by_trace_id("trace-local")
    assert len(events) == 1
    assert events[0].event_type == "workspace:read"
