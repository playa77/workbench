"""Comparison utilities for evaluation runs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from caw.models import EvalRun
    from caw.storage.repository import EvalRunRepository


@dataclass(frozen=True)
class ComparisonResult:
    """Side-by-side score comparison across run IDs."""

    run_ids: list[str]
    dimensions: list[str]
    matrix: dict[str, dict[str, float]]


class Comparator:
    """Compares stored eval runs across selected score dimensions."""

    def __init__(self, eval_repo: EvalRunRepository) -> None:
        self._eval_repo = eval_repo

    async def compare(
        self,
        run_ids: list[str],
        dimensions: list[str] | None = None,
    ) -> ComparisonResult:
        runs: list[EvalRun] = []
        for run_id in run_ids:
            run = await self._eval_repo.get(run_id)
            if run is not None:
                runs.append(run)

        available_dims = sorted({key for run in runs for key in run.scores})
        selected = dimensions or available_dims
        matrix: dict[str, dict[str, float]] = {
            run.id: {dimension: float(run.scores.get(dimension, 0.0)) for dimension in selected}
            for run in runs
        }
        return ComparisonResult(
            run_ids=[run.id for run in runs],
            dimensions=selected,
            matrix=matrix,
        )
