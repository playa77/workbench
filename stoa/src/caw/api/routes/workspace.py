"""Workspace capability API routes."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from caw.api.deps import AppServices, get_services
from caw.api.schemas import APIResponse
from caw.capabilities.workspace.executor import CommandExecutor
from caw.capabilities.workspace.local import LocalWorkspace
from caw.capabilities.workspace.patch import PatchProposal, WorkspacePatcher
from caw.capabilities.workspace.writes import WorkspaceWriter

router = APIRouter(prefix="/api/v1/workspace", tags=["workspace"])

_PATCHES: dict[str, PatchProposal] = {}


class ListRequest(BaseModel):
    path: str
    recursive: bool = False
    session_id: str = "workspace"
    trace_id: str = "workspace-list"


class ReadRequest(BaseModel):
    path: str
    session_id: str = "workspace"
    trace_id: str = "workspace-read"


class WriteRequest(BaseModel):
    path: str
    content: str
    session_id: str = "workspace"
    trace_id: str = "workspace-write"


class PatchRequest(BaseModel):
    path: str
    replacement_text: str
    description: str = "Proposed workspace patch"


class ExecuteRequest(BaseModel):
    command: str
    working_dir: str | None = None
    timeout_seconds: int = 30
    session_id: str = "workspace"
    trace_id: str = "workspace-execute"


@router.post("/list")
async def list_files(
    request: ListRequest,
    services: Annotated[AppServices, Depends(get_services)],
) -> APIResponse[dict[str, Any]]:
    workspace = LocalWorkspace(services.config.workspace, services.trace_collector)
    result = await workspace.list_files(
        path=request.path,
        recursive=request.recursive,
        session_id=request.session_id,
        trace_id=request.trace_id,
    )
    return APIResponse(data={"files": [item.__dict__ for item in result]})


@router.post("/read")
async def read_file(
    request: ReadRequest,
    services: Annotated[AppServices, Depends(get_services)],
) -> APIResponse[dict[str, Any]]:
    workspace = LocalWorkspace(services.config.workspace, services.trace_collector)
    result = await workspace.read_file(
        path=request.path,
        session_id=request.session_id,
        trace_id=request.trace_id,
    )
    return APIResponse(data={"file": result.__dict__})


@router.post("/write")
async def write_file(
    request: WriteRequest,
    services: Annotated[AppServices, Depends(get_services)],
) -> APIResponse[dict[str, Any]]:
    writer = WorkspaceWriter(
        services.config.workspace,
        services.trace_collector,
        services.permission_gate,
        services.approval_manager,
    )
    result = await writer.write_file(
        request.path, request.content, request.session_id, request.trace_id
    )
    return APIResponse(data={"result": result.__dict__})


@router.post("/patch")
async def create_patch(
    request: PatchRequest,
    services: Annotated[AppServices, Depends(get_services)],
) -> APIResponse[dict[str, Any]]:
    patcher = WorkspacePatcher(
        services.config.workspace, services.trace_collector, services.permission_gate
    )
    patch = patcher.create_patch(request.path, request.replacement_text, request.description)
    _PATCHES[patch.id] = patch
    return APIResponse(
        data={"patch_id": patch.id, "hunks": len(patch.hunks), "description": patch.description}
    )


@router.post("/patch/{patch_id}/apply")
async def apply_patch(
    patch_id: str,
    services: Annotated[AppServices, Depends(get_services)],
) -> APIResponse[dict[str, Any]]:
    patch = _PATCHES[patch_id]
    patcher = WorkspacePatcher(
        services.config.workspace, services.trace_collector, services.permission_gate
    )
    result = await patcher.apply_patch(patch, session_id="workspace", trace_id=f"patch-{patch_id}")
    return APIResponse(data={"result": result.__dict__})


@router.post("/execute")
async def execute(
    request: ExecuteRequest,
    services: Annotated[AppServices, Depends(get_services)],
) -> APIResponse[dict[str, Any]]:
    executor = CommandExecutor(
        services.config.workspace, services.trace_collector, services.permission_gate
    )
    result = await executor.execute_command(
        command=request.command,
        working_dir=request.working_dir,
        timeout_seconds=request.timeout_seconds,
        session_id=request.session_id,
        trace_id=request.trace_id,
    )
    return APIResponse(data={"result": result.__dict__})
