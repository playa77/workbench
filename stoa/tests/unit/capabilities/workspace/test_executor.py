from pathlib import Path

import pytest

from caw.capabilities.workspace.executor import CommandExecutor
from caw.core.config import WorkspaceConfig
from caw.core.permissions import PermissionGate
from caw.storage.database import Database
from caw.storage.repository import TraceEventRepository
from caw.traces.collector import TraceCollector


@pytest.mark.asyncio
async def test_execute_simple(tmp_path: Path, db: Database) -> None:
    config = WorkspaceConfig(allowed_paths=[str(tmp_path)], confirm_executions=False)
    collector = TraceCollector(TraceEventRepository(db), flush_threshold=1)
    executor = CommandExecutor(config, collector, PermissionGate(config, collector))
    result = await executor.execute_command("echo hello", "s1", "t1")
    assert result.exit_code == 0
    assert "hello" in result.stdout


@pytest.mark.asyncio
async def test_execute_timeout(tmp_path: Path, db: Database) -> None:
    config = WorkspaceConfig(allowed_paths=[str(tmp_path)], confirm_executions=False)
    collector = TraceCollector(TraceEventRepository(db), flush_threshold=1)
    executor = CommandExecutor(config, collector, PermissionGate(config, collector))
    result = await executor.execute_command("sleep 60", "s1", "t1", timeout_seconds=1)
    assert result.timed_out is True


@pytest.mark.asyncio
async def test_execute_working_dir(tmp_path: Path, db: Database) -> None:
    config = WorkspaceConfig(
        allowed_paths=[str(tmp_path)], confirm_executions=False, sandbox_mode="strict"
    )
    collector = TraceCollector(TraceEventRepository(db), flush_threshold=1)
    executor = CommandExecutor(config, collector, PermissionGate(config, collector))
    result = await executor.execute_command("pwd", "s1", "t1", working_dir=str(tmp_path))
    assert str(tmp_path) in result.stdout.strip()


@pytest.mark.asyncio
async def test_execute_failure(tmp_path: Path, db: Database) -> None:
    config = WorkspaceConfig(allowed_paths=[str(tmp_path)], confirm_executions=False)
    collector = TraceCollector(TraceEventRepository(db), flush_threshold=1)
    executor = CommandExecutor(config, collector, PermissionGate(config, collector))
    result = await executor.execute_command("false", "s1", "t1")
    assert result.exit_code == 1


@pytest.mark.asyncio
async def test_execute_traced(tmp_path: Path, db: Database) -> None:
    config = WorkspaceConfig(allowed_paths=[str(tmp_path)], confirm_executions=False)
    repository = TraceEventRepository(db)
    collector = TraceCollector(repository, flush_threshold=1)
    executor = CommandExecutor(config, collector, PermissionGate(config, collector))
    await executor.execute_command("echo hi", "s1", "trace-exec")
    events = await repository.get_by_trace_id("trace-exec")
    assert len(events) == 1
    assert events[0].event_type == "workspace:execute"
