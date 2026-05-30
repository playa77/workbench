"""Evaluation runner that executes tasks and persists eval-run records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from caw.core.engine import Engine, ExecutionRequest, ExecutionResult
from caw.evaluation.scorer import CompositeScorer, Score, Scorer
from caw.evaluation.tasks import EvalTask, load_task
from caw.models import EvalRun, SessionMode

if TYPE_CHECKING:
    from pathlib import Path

    from caw.core.session import SessionManager
    from caw.storage.repository import EvalRunRepository
    from caw.traces.collector import TraceCollector


@dataclass(frozen=True)
class EvalRunResult:
    """Combined execution, scoring, and persisted-run metadata."""

    run: EvalRun
    execution: ExecutionResult
    scores: list[Score]


class EvalRunner:
    """Executes a task, captures trace events, and computes evaluation scores."""

    def __init__(
        self,
        engine: Engine,
        session_manager: SessionManager,
        eval_repo: EvalRunRepository,
        trace_collector: TraceCollector,
        scorers: list[Scorer],
    ) -> None:
        self._engine = engine
        self._session_manager = session_manager
        self._eval_repo = eval_repo
        self._trace_collector = trace_collector
        self._scorers = scorers

    async def run_task(
        self,
        task: EvalTask,
        provider: str | None = None,
        model: str | None = None,
    ) -> EvalRunResult:
        """Run one evaluation task and persist an ``EvalRun`` row."""
        session = await self._session_manager.create(mode=SessionMode.CHAT)
        run = await self._eval_repo.create(
            EvalRun(
                task_id=task.task_id,
                provider=provider or "default",
                model=model or "default",
                started_at=datetime.now(UTC),
                status="running",
                metadata={"task_file": str(task.source_path)},
            )
        )

        execution = await self._engine.execute(
            ExecutionRequest(
                session_id=session.id,
                content=task.input.query or "Run evaluation task.",
                provider=provider,
                model=model,
            )
        )
        trace = await self._trace_collector.get_trace(execution.trace_id)

        scores = [await scorer.score(task, execution, trace) for scorer in self._scorers]
        composite = await CompositeScorer(self._scorers, task.scoring.weights).score(
            task,
            execution,
            trace,
        )
        score_map = {score.scorer_id: score.value for score in scores}
        score_map[composite.scorer_id] = composite.value

        run.status = "completed"
        run.completed_at = datetime.now(UTC)
        run.provider = execution.provider
        run.model = execution.model
        run.trace_id = execution.trace_id
        run.scores = score_map
        run.metadata = {**run.metadata, "message_id": execution.message_id}
        run = await self._eval_repo.update(run)

        return EvalRunResult(run=run, execution=execution, scores=[*scores, composite])

    async def run_task_file(
        self,
        task_file: Path,
        provider: str | None = None,
        model: str | None = None,
    ) -> EvalRunResult:
        """Load a task from disk then execute it."""
        return await self.run_task(load_task(task_file), provider=provider, model=model)
