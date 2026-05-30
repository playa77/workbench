"""Permission gate checks and approval request creation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from caw.models import ApprovalRequest, PermissionLevel, TraceEvent

if TYPE_CHECKING:
    from caw.core.config import WorkspaceConfig
    from caw.traces.collector import TraceCollector


class PermissionGate:
    """Checks whether an operation needs explicit user approval."""

    def __init__(self, config: WorkspaceConfig, collector: TraceCollector) -> None:
        self._config = config
        self._collector = collector

    async def check(
        self,
        level: PermissionLevel,
        action: str,
        resources: list[str],
        trace_id: str,
        session_id: str,
    ) -> ApprovalRequest | None:
        """Evaluate an action and optionally return an approval request."""
        if not self.requires_approval(level):
            return None

        approval = ApprovalRequest(
            session_id=session_id,
            action=action,
            permission_level=level,
            resources=list(resources),
            reversible=level not in {PermissionLevel.DELETE, PermissionLevel.ADMIN},
        )

        await self._collector.emit(
            TraceEvent(
                trace_id=trace_id,
                session_id=session_id,
                event_type="gate:approval_required",
                data={
                    "action": action,
                    "permission_level": level.value,
                    "resources": resources,
                    "approval_request_id": approval.id,
                },
            )
        )
        return approval

    def requires_approval(self, level: PermissionLevel) -> bool:
        """Check whether a permission level is gated by current config."""
        if level in {PermissionLevel.READ, PermissionLevel.SUGGEST}:
            return False
        if level in {PermissionLevel.DELETE, PermissionLevel.ADMIN}:
            return True
        if level is PermissionLevel.WRITE:
            return self._config.confirm_writes
        if level is PermissionLevel.EXECUTE:
            return self._config.confirm_executions
        return True
