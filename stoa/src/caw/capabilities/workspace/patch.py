"""Patch proposal and application support for workspace files."""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from caw.capabilities.workspace.local import PathPolicy
from caw.errors import PermissionError_, WorkspaceError
from caw.models import PermissionLevel, TraceEvent

if TYPE_CHECKING:
    from caw.core.config import WorkspaceConfig
    from caw.core.permissions import PermissionGate
    from caw.traces.collector import TraceCollector


@dataclass(slots=True)
class PatchHunk:
    start_line: int
    end_line: int
    original_lines: list[str]
    replacement_lines: list[str]
    context_before: list[str]
    context_after: list[str]


@dataclass(slots=True)
class PatchProposal:
    target_path: str
    original_content_hash: str
    hunks: list[PatchHunk]
    description: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    reversible: bool = False
    reverse_patch: PatchProposal | None = None


@dataclass(slots=True)
class PatchResult:
    applied: bool
    path: str


class WorkspacePatcher:
    def __init__(
        self,
        config: WorkspaceConfig,
        collector: TraceCollector,
        gate: PermissionGate,
    ) -> None:
        self._policy = PathPolicy(config)
        self._collector = collector
        self._gate = gate

    def create_patch(
        self, target_path: str, replacement_text: str, description: str
    ) -> PatchProposal:
        target = self._policy.validate(target_path)
        if not target.exists():
            raise WorkspaceError("File not found", "file_not_found", details={"path": str(target)})

        original = target.read_text(encoding="utf-8")
        original_lines = original.splitlines()
        replacement_lines = replacement_text.splitlines()
        content_hash = hashlib.sha256(original.encode("utf-8")).hexdigest()

        proposal = PatchProposal(
            target_path=str(target),
            original_content_hash=content_hash,
            hunks=[
                PatchHunk(
                    start_line=1,
                    end_line=max(1, len(original_lines)),
                    original_lines=original_lines,
                    replacement_lines=replacement_lines,
                    context_before=original_lines[:3],
                    context_after=original_lines[-3:] if original_lines else [],
                )
            ],
            description=description,
            reversible=True,
        )
        proposal.reverse_patch = PatchProposal(
            target_path=str(target),
            original_content_hash=hashlib.sha256(replacement_text.encode("utf-8")).hexdigest(),
            hunks=[
                PatchHunk(
                    start_line=1,
                    end_line=max(1, len(replacement_lines)),
                    original_lines=replacement_lines,
                    replacement_lines=original_lines,
                    context_before=replacement_lines[:3],
                    context_after=replacement_lines[-3:] if replacement_lines else [],
                )
            ],
            description=f"Reverse patch for {description}",
            reversible=False,
            reverse_patch=None,
        )
        return proposal

    async def apply_patch(
        self, patch: PatchProposal, session_id: str, trace_id: str
    ) -> PatchResult:
        approval = await self._gate.check(
            PermissionLevel.WRITE,
            action="workspace.apply_patch",
            resources=[patch.target_path],
            trace_id=trace_id,
            session_id=session_id,
        )
        if approval is not None:
            raise PermissionError_(
                "Patch application requires approval",
                "approval_required",
                details={"approval_id": approval.id},
            )

        target = self._policy.validate(Path(patch.target_path))
        current = target.read_text(encoding="utf-8")
        current_hash = hashlib.sha256(current.encode("utf-8")).hexdigest()
        if current_hash != patch.original_content_hash:
            raise WorkspaceError(
                "Patch conflict detected",
                "patch_conflict",
                details={"expected_hash": patch.original_content_hash, "actual_hash": current_hash},
            )

        replacement: list[str] = []
        for hunk in patch.hunks:
            replacement.extend(hunk.replacement_lines)
        target.write_text("\n".join(replacement), encoding="utf-8")

        await self._collector.emit(
            TraceEvent(
                trace_id=trace_id,
                session_id=session_id,
                event_type="workspace:write",
                data={"action": "apply_patch", "path": str(target), "patch_id": patch.id},
            )
        )
        return PatchResult(applied=True, path=str(target))
