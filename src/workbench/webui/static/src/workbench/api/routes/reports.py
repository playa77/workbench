"""Report history routes — list, view, delete stored research reports."""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from workbench.core.auth import get_current_user
from workbench.core.db import get_session
from workbench.core.encryption import decrypt_report_content
from workbench.core.models import StoredReport, User

router = APIRouter()


class ReportSummary(BaseModel):
    id: str
    title: str
    created_at: str
    content_length: int
    word_count: int
    metadata: dict


class ReportDetail(BaseModel):
    id: str
    title: str
    content: str
    content_format: str
    created_at: str
    metadata: dict


@router.get("/reports", response_model=list[ReportSummary])
async def list_reports(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    result = await session.execute(
        select(StoredReport)
        .where(StoredReport.user_id == user.id)
        .order_by(StoredReport.created_at.desc())
        .limit(100)
    )
    reports = result.scalars().all()
    return [
        ReportSummary(
            id=str(r.id),
            title=r.title,
            created_at=r.created_at.isoformat() if r.created_at else "",
            content_length=len(r.content),
            word_count=len(r.content.split()) if r.content else 0,
            metadata=r.metadata_json or {},
        )
        for r in reports
    ]


@router.get("/reports/{report_id}", response_model=ReportDetail)
async def get_report(
    report_id: str,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    result = await session.execute(
        select(StoredReport).where(
            StoredReport.id == UUID(report_id),
            StoredReport.user_id == user.id,
        )
    )
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return ReportDetail(
        id=str(report.id),
        title=report.title,
        content=decrypt_report_content(report.content),
        content_format=report.content_format,
        created_at=report.created_at.isoformat() if report.created_at else "",
        metadata=report.metadata_json or {},
    )


@router.delete("/reports/{report_id}")
async def delete_report(
    report_id: str,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    result = await session.execute(
        select(StoredReport).where(
            StoredReport.id == UUID(report_id),
            StoredReport.user_id == user.id,
        )
    )
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    await session.delete(report)
    await session.commit()
    return {"status": "ok"}
