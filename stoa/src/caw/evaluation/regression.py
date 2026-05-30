"""Regression detection utilities for evaluation performance trends."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from caw.storage.repository import EvalRunRepository


@dataclass(frozen=True)
class RegressionReport:
    """Result of checking whether a latest run regressed vs baseline history."""

    task_id: str
    latest_run_id: str
    scorer_id: str
    latest_score: float
    baseline_median: float
    baseline_iqr: float
    threshold: float
    regressed: bool


class RegressionDetector:
    """Detect regressions using median and IQR robust statistics."""

    def __init__(self, eval_repo: EvalRunRepository, scorer_id: str = "composite") -> None:
        self._eval_repo = eval_repo
        self._scorer_id = scorer_id

    async def check_regression(
        self,
        task_id: str,
        latest_run_id: str,
        baseline_window: int = 10,
    ) -> RegressionReport:
        runs = await self._eval_repo.list_by_task(task_id, limit=baseline_window + 10)
        latest = next((run for run in runs if run.id == latest_run_id), None)
        latest_score = float(latest.scores.get(self._scorer_id, 0.0)) if latest is not None else 0.0

        baseline_scores = [
            float(run.scores.get(self._scorer_id, 0.0)) for run in runs if run.id != latest_run_id
        ][:baseline_window]

        if baseline_scores:
            baseline_median = median(baseline_scores)
            sorted_scores = sorted(baseline_scores)
            lower_half = sorted_scores[: len(sorted_scores) // 2]
            upper_half = sorted_scores[(len(sorted_scores) + 1) // 2 :]
            q1 = median(lower_half) if lower_half else baseline_median
            q3 = median(upper_half) if upper_half else baseline_median
            iqr = q3 - q1
        else:
            baseline_median = 0.0
            iqr = 0.0

        threshold = baseline_median - 1.5 * iqr
        return RegressionReport(
            task_id=task_id,
            latest_run_id=latest_run_id,
            scorer_id=self._scorer_id,
            latest_score=latest_score,
            baseline_median=baseline_median,
            baseline_iqr=iqr,
            threshold=threshold,
            regressed=latest_score < threshold,
        )
