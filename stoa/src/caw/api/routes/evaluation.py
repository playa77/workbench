"""Evaluation API routes for running, comparing, and regression checking."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from caw.api.deps import AppServices, get_services
from caw.api.schemas import APIResponse
from caw.evaluation.comparator import Comparator
from caw.evaluation.regression import RegressionDetector
from caw.evaluation.runner import EvalRunner
from caw.evaluation.scorer import LatencyScorer, TokenEfficiencyScorer
from caw.evaluation.tasks import load_tasks
from caw.storage.repository import EvalRunRepository

router = APIRouter(prefix="/api/v1/eval", tags=["evaluation"])


class EvalRunRequest(BaseModel):
    task_id: str
    provider: str | None = None
    model: str | None = None


class EvalCompareRequest(BaseModel):
    run_ids: list[str]
    dimensions: list[str] | None = None


class EvalRegressionRequest(BaseModel):
    task_id: str
    latest_run_id: str
    baseline_window: int = 10


@router.post("/run")
async def run_eval(
    request: EvalRunRequest,
    services: Annotated[AppServices, Depends(get_services)],
) -> APIResponse[dict[str, object]]:
    tasks = load_tasks(Path(services.config.evaluation.tasks_dir))
    task = next((item for item in tasks if item.task_id == request.task_id), None)
    if task is None:
        return APIResponse(
            status="error",
            error_code="eval_task_not_found",
            message=request.task_id,
        )

    runner = EvalRunner(
        engine=services.engine,
        session_manager=services.session_manager,
        eval_repo=EvalRunRepository(services.database),
        trace_collector=services.trace_collector,
        scorers=[LatencyScorer(), TokenEfficiencyScorer()],
    )
    result = await runner.run_task(task=task, provider=request.provider, model=request.model)
    return APIResponse(
        data={
            "run_id": result.run.id,
            "task_id": result.run.task_id,
            "trace_id": result.run.trace_id,
            "status": result.run.status,
            "scores": result.run.scores,
        }
    )


@router.get("/runs")
async def list_runs(
    task_id: str,
    services: Annotated[AppServices, Depends(get_services)],
) -> APIResponse[list[dict[str, object]]]:
    runs = await EvalRunRepository(services.database).list_by_task(task_id)
    return APIResponse(
        data=[
            {
                "id": run.id,
                "task_id": run.task_id,
                "provider": run.provider,
                "model": run.model,
                "status": run.status,
                "scores": run.scores,
            }
            for run in runs
        ]
    )


@router.get("/runs/{run_id}")
async def get_run(
    run_id: str,
    services: Annotated[AppServices, Depends(get_services)],
) -> APIResponse[dict[str, object] | None]:
    run = await EvalRunRepository(services.database).get(run_id)
    return APIResponse(data=run.__dict__ if run is not None else None)


@router.post("/compare")
async def compare_runs(
    request: EvalCompareRequest,
    services: Annotated[AppServices, Depends(get_services)],
) -> APIResponse[dict[str, object]]:
    result = await Comparator(EvalRunRepository(services.database)).compare(
        run_ids=request.run_ids,
        dimensions=request.dimensions,
    )
    return APIResponse(data=result.__dict__)


@router.post("/regression")
async def detect_regression(
    request: EvalRegressionRequest,
    services: Annotated[AppServices, Depends(get_services)],
) -> APIResponse[dict[str, object]]:
    report = await RegressionDetector(EvalRunRepository(services.database)).check_regression(
        task_id=request.task_id,
        latest_run_id=request.latest_run_id,
        baseline_window=request.baseline_window,
    )
    return APIResponse(data=report.__dict__)
