"""Approval coordination for gated operations."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from caw.errors import PermissionError_
from caw.models import ApprovalRecord, ApprovalRequest, ApprovalStatus, TraceEvent
from caw.storage.approvals import ApprovalRepository
from caw.traces.collector import TraceCollector


class ApprovalManager:
    """Stores and resolves approval requests across API and capability layers."""

    def __init__(self, repository: ApprovalRepository, collector: TraceCollector) -> None:
        self._repository = repository
        self._collector = collector

    async def register(self, request: ApprovalRequest) -> ApprovalRecord:
        """Persist a new pending approval request."""
        return await self._repository.create(ApprovalRecord(request=request))

    async def list_pending(self) -> list[ApprovalRecord]:
        """Return all pending approvals ordered by creation time."""
        now = datetime.now(UTC)
        records = await self._repository.list_pending()
        for record in records:
            if self._expired(record, now):
                await self._expire(record)
        return await self._repository.list_pending()

    async def decide(
        self,
        request_id: str,
        *,
        approved: bool,
        resolved_by: str | None,
        reason: str | None,
    ) -> ApprovalRecord:
        """Approve or deny a pending request."""
        current = await self._repository.get(request_id)
        if current is None:
            raise PermissionError_("Approval request not found", "approval_not_found")
        if current.status is not ApprovalStatus.PENDING:
            return current

        status = ApprovalStatus.APPROVED if approved else ApprovalStatus.DENIED
        resolved = await self._repository.resolve(
            request_id,
            status=status,
            resolved_by=resolved_by,
            reason=reason,
            resolved_at=datetime.now(UTC),
        )
        if resolved is None:
            raise PermissionError_("Approval request not found", "approval_not_found")

        await self._collector.emit(
            TraceEvent(
                trace_id=f"approval-{resolved.request.id}",
                session_id=resolved.request.session_id,
                event_type="gate:approval_resolved",
                data={
                    "approval_request_id": resolved.request.id,
                    "status": resolved.status.value,
                    "resolved_by": resolved.resolved_by,
                },
            )
        )
        return resolved

    async def await_decision(self, request: ApprovalRequest) -> None:
        """Block a gated operation until request is approved or denied/expired."""
        while True:
            record = await self._repository.get(request.id)
            if record is None:
                raise PermissionError_("Approval request not found", "approval_not_found")
            now = datetime.now(UTC)
            if self._expired(record, now):
                record = await self._expire(record)
            if record.status is ApprovalStatus.APPROVED:
                return
            if record.status in {ApprovalStatus.DENIED, ApprovalStatus.EXPIRED}:
                raise PermissionError_(
                    "Workspace mutation requires approval",
                    "approval_required",
                    details={"approval_id": record.request.id, "status": record.status.value},
                )
            await asyncio.sleep(0.05)

    def _expired(self, record: ApprovalRecord, now: datetime) -> bool:
        deadline = record.created_at.timestamp() + record.request.timeout_seconds
        return record.status is ApprovalStatus.PENDING and now.timestamp() > deadline

    async def _expire(self, record: ApprovalRecord) -> ApprovalRecord:
        updated = await self._repository.resolve(
            record.request.id,
            status=ApprovalStatus.EXPIRED,
            resolved_by="system",
            reason="approval timeout exceeded",
            resolved_at=datetime.now(UTC),
        )
        if updated is None:
            raise PermissionError_("Approval request not found", "approval_not_found")
        await self._collector.emit(
            TraceEvent(
                trace_id=f"approval-{updated.request.id}",
                session_id=updated.request.session_id,
                event_type="gate:approval_timeout",
                data={"approval_request_id": updated.request.id},
            )
        )
        return updated
