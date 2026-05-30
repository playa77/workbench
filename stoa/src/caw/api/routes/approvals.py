"""Approval queue API routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from caw.api.deps import AppServices, get_services
from caw.api.schemas import APIResponse

router = APIRouter(prefix="/api/v1/approvals", tags=["approvals"])


class ApprovalDecisionRequest(BaseModel):
    approved: bool
    resolved_by: str | None = "user"
    reason: str | None = None


@router.get("/pending")
async def list_pending(
    services: Annotated[AppServices, Depends(get_services)],
) -> APIResponse[list[dict[str, object]]]:
    records = await services.approval_manager.list_pending()
    return APIResponse(
        data=[
            {
                "id": record.request.id,
                "session_id": record.request.session_id,
                "action": record.request.action,
                "permission_level": record.request.permission_level.value,
                "resources": record.request.resources,
                "reversible": record.request.reversible,
                "timeout_seconds": record.request.timeout_seconds,
                "created_at": record.created_at.isoformat(),
            }
            for record in records
        ]
    )


@router.post("/{request_id}")
async def decide(
    request_id: str,
    payload: ApprovalDecisionRequest,
    services: Annotated[AppServices, Depends(get_services)],
) -> APIResponse[dict[str, object]]:
    record = await services.approval_manager.decide(
        request_id,
        approved=payload.approved,
        resolved_by=payload.resolved_by,
        reason=payload.reason,
    )
    return APIResponse(
        data={
            "id": record.request.id,
            "status": record.status.value,
            "resolved_by": record.resolved_by,
            "reason": record.reason,
        }
    )
