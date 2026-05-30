from pathlib import Path

import pytest

from caw.capabilities.workspace.patch import WorkspacePatcher
from caw.core.config import WorkspaceConfig
from caw.core.permissions import PermissionGate
from caw.errors import WorkspaceError
from caw.storage.database import Database
from caw.storage.repository import TraceEventRepository
from caw.traces.collector import TraceCollector


@pytest.mark.asyncio
async def test_create_patch(tmp_path: Path, db: Database) -> None:
    target = tmp_path / "a.txt"
    target.write_text("old\ntext", encoding="utf-8")
    collector = TraceCollector(TraceEventRepository(db), flush_threshold=1)
    patcher = WorkspacePatcher(
        WorkspaceConfig(sandbox_mode="strict", allowed_paths=[str(tmp_path)], confirm_writes=False),
        collector,
        PermissionGate(
            WorkspaceConfig(
                sandbox_mode="strict", allowed_paths=[str(tmp_path)], confirm_writes=False
            ),
            collector,
        ),
    )

    patch = patcher.create_patch(str(target), "new\ntext", "update a.txt")
    assert patch.hunks
    assert patch.hunks[0].context_before


@pytest.mark.asyncio
async def test_apply_patch(tmp_path: Path, db: Database) -> None:
    target = tmp_path / "a.txt"
    target.write_text("old", encoding="utf-8")
    config = WorkspaceConfig(
        sandbox_mode="strict", allowed_paths=[str(tmp_path)], confirm_writes=False
    )
    collector = TraceCollector(TraceEventRepository(db), flush_threshold=1)
    patcher = WorkspacePatcher(config, collector, PermissionGate(config, collector))

    patch = patcher.create_patch(str(target), "new", "update")
    await patcher.apply_patch(patch, session_id="s1", trace_id="t1")
    assert target.read_text(encoding="utf-8") == "new"


@pytest.mark.asyncio
async def test_patch_conflict(tmp_path: Path, db: Database) -> None:
    target = tmp_path / "a.txt"
    target.write_text("old", encoding="utf-8")
    config = WorkspaceConfig(
        sandbox_mode="strict", allowed_paths=[str(tmp_path)], confirm_writes=False
    )
    collector = TraceCollector(TraceEventRepository(db), flush_threshold=1)
    patcher = WorkspacePatcher(config, collector, PermissionGate(config, collector))

    patch = patcher.create_patch(str(target), "new", "update")
    target.write_text("changed", encoding="utf-8")
    with pytest.raises(WorkspaceError):
        await patcher.apply_patch(patch, session_id="s1", trace_id="t1")


@pytest.mark.asyncio
async def test_reverse_patch(tmp_path: Path, db: Database) -> None:
    target = tmp_path / "a.txt"
    target.write_text("old", encoding="utf-8")
    config = WorkspaceConfig(
        sandbox_mode="strict", allowed_paths=[str(tmp_path)], confirm_writes=False
    )
    collector = TraceCollector(TraceEventRepository(db), flush_threshold=1)
    patcher = WorkspacePatcher(config, collector, PermissionGate(config, collector))

    patch = patcher.create_patch(str(target), "new", "update")
    await patcher.apply_patch(patch, session_id="s1", trace_id="t1")
    assert patch.reverse_patch is not None
    await patcher.apply_patch(patch.reverse_patch, session_id="s1", trace_id="t2")
    assert target.read_text(encoding="utf-8") == "old"
