"""Persistence repository for approval gate records."""

from __future__ import annotations

import json
from datetime import datetime

from caw.models import ApprovalRecord, ApprovalRequest, ApprovalStatus, PermissionLevel
from caw.storage.repository import _from_iso, _to_iso


class ApprovalRepository:
    """CRUD operations for approval requests tracked in SQLite."""

    def __init__(self, db: object) -> None:
        self._db = db

    async def create(self, record: ApprovalRecord) -> ApprovalRecord:
        conn = self._db.connection()
        await conn.execute(
            (
                "INSERT INTO approvals ("
                "id, session_id, action, permission_level, resources_json, reversible, preview, "
                "timeout_seconds, status, created_at, resolved_at, resolved_by, reason"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
            ),
            (
                record.request.id,
                record.request.session_id,
                record.request.action,
                record.request.permission_level.value,
                json.dumps(record.request.resources),
                1 if record.request.reversible else 0,
                record.request.preview,
                record.request.timeout_seconds,
                record.status.value,
                _to_iso(record.created_at),
                _to_iso(record.resolved_at),
                record.resolved_by,
                record.reason,
            ),
        )
        await conn.commit()
        return record

    async def get(self, request_id: str) -> ApprovalRecord | None:
        conn = self._db.connection()
        row = await (await conn.execute("SELECT * FROM approvals WHERE id = ?", (request_id,))).fetchone()
        if row is None:
            return None
        return _from_row(row)

    async def list_pending(self) -> list[ApprovalRecord]:
        conn = self._db.connection()
        rows = await (
            await conn.execute(
                "SELECT * FROM approvals WHERE status = ? ORDER BY created_at ASC",
                (ApprovalStatus.PENDING.value,),
            )
        ).fetchall()
        return [_from_row(row) for row in rows]

    async def resolve(
        self,
        request_id: str,
        *,
        status: ApprovalStatus,
        resolved_by: str | None,
        reason: str | None,
        resolved_at: datetime,
    ) -> ApprovalRecord | None:
        conn = self._db.connection()
        await conn.execute(
            "UPDATE approvals SET status = ?, resolved_at = ?, resolved_by = ?, reason = ? WHERE id = ?",
            (status.value, _to_iso(resolved_at), resolved_by, reason, request_id),
        )
        await conn.commit()
        return await self.get(request_id)


def _from_row(row: object) -> ApprovalRecord:
    request = ApprovalRequest(
        id=str(row["id"]),
        session_id=str(row["session_id"]),
        action=str(row["action"]),
        permission_level=PermissionLevel(str(row["permission_level"])),
        resources=json.loads(str(row["resources_json"])),
        reversible=bool(int(row["reversible"])),
        preview=str(row["preview"]) if row["preview"] is not None else None,
        timeout_seconds=int(row["timeout_seconds"]),
    )
    return ApprovalRecord(
        request=request,
        status=ApprovalStatus(str(row["status"])),
        created_at=_from_iso(str(row["created_at"])) or datetime.min,
        resolved_at=_from_iso(str(row["resolved_at"])) if row["resolved_at"] is not None else None,
        resolved_by=str(row["resolved_by"]) if row["resolved_by"] is not None else None,
        reason=str(row["reason"]) if row["reason"] is not None else None,
    )
