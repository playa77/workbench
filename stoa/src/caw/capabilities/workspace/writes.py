"""Workspace mutation operations (write/move/copy/delete)."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from typing import TYPE_CHECKING

from caw.capabilities.workspace.local import PathPolicy
from caw.core.approvals import ApprovalManager
from caw.errors import PermissionError_
from caw.models import PermissionLevel, TraceEvent

if TYPE_CHECKING:
    from caw.core.config import WorkspaceConfig
    from caw.core.permissions import PermissionGate
    from caw.traces.collector import TraceCollector


@dataclass(slots=True)
class MutationResult:
    path: str
    success: bool


class WorkspaceWriter:
    def __init__(
        self,
        config: WorkspaceConfig,
        collector: TraceCollector,
        gate: PermissionGate,
        approval_manager: ApprovalManager | None = None,
    ) -> None:
        self._policy = PathPolicy(config)
        self._collector = collector
        self._gate = gate
        self._approval_manager = approval_manager

    async def write_file(
        self, path: str, content: str, session_id: str, trace_id: str
    ) -> MutationResult:
        target = self._policy.validate(path)
        await self._ensure_allowed(
            PermissionLevel.WRITE,
            "workspace.write_file",
            [str(target)],
            trace_id,
            session_id,
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        await self._emit(trace_id, session_id, "write_file", [str(target)])
        return MutationResult(path=str(target), success=True)

    async def move_file(self, src: str, dst: str, session_id: str, trace_id: str) -> MutationResult:
        source = self._policy.validate(src)
        destination = self._policy.validate(dst)
        await self._ensure_allowed(
            PermissionLevel.WRITE,
            "workspace.move_file",
            [str(source), str(destination)],
            trace_id,
            session_id,
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(destination))
        await self._emit(trace_id, session_id, "move_file", [str(source), str(destination)])
        return MutationResult(path=str(destination), success=True)

    async def copy_file(self, src: str, dst: str, session_id: str, trace_id: str) -> MutationResult:
        source = self._policy.validate(src)
        destination = self._policy.validate(dst)
        await self._ensure_allowed(
            PermissionLevel.WRITE,
            "workspace.copy_file",
            [str(source), str(destination)],
            trace_id,
            session_id,
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        await self._emit(trace_id, session_id, "copy_file", [str(source), str(destination)])
        return MutationResult(path=str(destination), success=True)

    async def delete_file(self, path: str, session_id: str, trace_id: str) -> MutationResult:
        target = self._policy.validate(path)
        await self._ensure_allowed(
            PermissionLevel.DELETE,
            "workspace.delete_file",
            [str(target)],
            trace_id,
            session_id,
        )
        target.unlink()
        await self._emit(trace_id, session_id, "delete_file", [str(target)])
        return MutationResult(path=str(target), success=True)

    async def _ensure_allowed(
        self,
        level: PermissionLevel,
        action: str,
        resources: list[str],
        trace_id: str,
        session_id: str,
    ) -> None:
        approval = await self._gate.check(level, action, resources, trace_id, session_id)
        if approval is not None:
            if self._approval_manager is None:
                raise PermissionError_(
                    "Workspace mutation requires approval",
                    "approval_required",
                    details={"approval_id": approval.id, "action": action},
                )
            await self._approval_manager.register(approval)
            await self._approval_manager.await_decision(approval)

    async def _emit(
        self,
        trace_id: str,
        session_id: str,
        action: str,
        resources: list[str],
    ) -> None:
        await self._collector.emit(
            TraceEvent(
                trace_id=trace_id,
                session_id=session_id,
                event_type="workspace:write",
                data={"action": action, "resources": resources},
            )
        )
