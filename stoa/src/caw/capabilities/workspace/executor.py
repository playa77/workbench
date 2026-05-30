"""Constrained command execution for workspace capability."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from caw.capabilities.workspace.local import PathPolicy
from caw.errors import PermissionError_
from caw.models import PermissionLevel, TraceEvent

if TYPE_CHECKING:
    from caw.core.config import WorkspaceConfig
    from caw.core.permissions import PermissionGate
    from caw.traces.collector import TraceCollector


@dataclass(slots=True)
class ExecutionResult:
    stdout: str
    stderr: str
    exit_code: int
    duration_ms: int
    timed_out: bool = False


class CommandExecutor:
    def __init__(
        self,
        config: WorkspaceConfig,
        collector: TraceCollector,
        gate: PermissionGate,
    ) -> None:
        self._policy = PathPolicy(config)
        self._collector = collector
        self._gate = gate

    async def execute_command(
        self,
        command: str,
        session_id: str,
        trace_id: str,
        working_dir: str | None = None,
        timeout_seconds: int = 30,
        env: dict[str, str] | None = None,
    ) -> ExecutionResult:
        approval = await self._gate.check(
            PermissionLevel.EXECUTE,
            action="workspace.execute_command",
            resources=[command],
            trace_id=trace_id,
            session_id=session_id,
        )
        if approval is not None:
            raise PermissionError_(
                "Command execution requires approval",
                "approval_required",
                details={"approval_id": approval.id},
            )

        cwd_path = self._policy.validate(working_dir) if working_dir is not None else None
        start = time.perf_counter()
        process = await asyncio.create_subprocess_shell(
            command,
            cwd=str(cwd_path) if cwd_path is not None else None,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        timed_out = False
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(), timeout=timeout_seconds
            )
        except TimeoutError:
            timed_out = True
            process.kill()
            stdout_bytes, stderr_bytes = await process.communicate()

        duration_ms = int((time.perf_counter() - start) * 1000)
        result = ExecutionResult(
            stdout=stdout_bytes.decode("utf-8", errors="replace"),
            stderr=stderr_bytes.decode("utf-8", errors="replace"),
            exit_code=process.returncode if process.returncode is not None else 1,
            duration_ms=duration_ms,
            timed_out=timed_out,
        )
        await self._collector.emit(
            TraceEvent(
                trace_id=trace_id,
                session_id=session_id,
                event_type="workspace:execute",
                data={
                    "command": command,
                    "exit_code": result.exit_code,
                    "duration_ms": duration_ms,
                    "timed_out": timed_out,
                },
            )
        )
        return result
