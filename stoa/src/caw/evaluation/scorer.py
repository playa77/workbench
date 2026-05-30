"""Scoring framework for evaluation runs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from caw.core.engine import ExecutionResult
    from caw.evaluation.tasks import EvalTask
    from caw.models import TraceEvent


@dataclass(frozen=True)
class Score:
    """A single scorer output in the normalized range [0.0, 1.0]."""

    scorer_id: str
    value: float
    explanation: str
    details: dict[str, object] | None = None


@runtime_checkable
class Scorer(Protocol):
    """Interface implemented by all quality-dimension scorers."""

    @property
    def scorer_id(self) -> str: ...

    async def score(
        self,
        task: EvalTask,
        result: ExecutionResult,
        trace: list[TraceEvent],
    ) -> Score: ...


class LatencyScorer:
    """Score latency using trace wall-clock duration, where lower latency scores higher."""

    scorer_id = "latency"

    async def score(
        self,
        task: EvalTask,
        result: ExecutionResult,
        trace: list[TraceEvent],
    ) -> Score:
        del task
        duration_ms = result.latency_ms
        if trace:
            duration_ms = int((trace[-1].timestamp - trace[0].timestamp).total_seconds() * 1000)

        value = max(0.0, min(1.0, 1.0 - (duration_ms / 10_000.0)))
        return Score(
            scorer_id=self.scorer_id,
            value=value,
            explanation=f"Lower latency produces higher score ({duration_ms}ms observed).",
            details={"duration_ms": duration_ms},
        )


class TokenEfficiencyScorer:
    """Score token efficiency as inverse of tokens consumed per unit of quality."""

    scorer_id = "token_efficiency"

    async def score(
        self,
        task: EvalTask,
        result: ExecutionResult,
        trace: list[TraceEvent],
    ) -> Score:
        del task, trace
        quality_hint = 0.5
        if result.content.strip():
            quality_hint = min(1.0, max(0.1, len(result.content.split()) / 100.0))

        tokens_used = max(1, result.tokens_in + result.tokens_out)
        ratio = tokens_used / quality_hint
        value = 1.0 / (1.0 + ratio / 1000.0)
        return Score(
            scorer_id=self.scorer_id,
            value=value,
            explanation="Fewer tokens per quality unit produce a higher efficiency score.",
            details={"tokens_used": tokens_used, "quality_hint": quality_hint, "ratio": ratio},
        )


class CompositeScorer:
    """Aggregates multiple scorers into a weighted composite score."""

    def __init__(self, scorers: list[Scorer], weights: dict[str, float] | None = None) -> None:
        self._scorers = scorers
        self._weights = weights or {}

    async def score(
        self,
        task: EvalTask,
        result: ExecutionResult,
        trace: list[TraceEvent],
    ) -> Score:
        if not self._scorers:
            return Score(
                scorer_id="composite",
                value=0.0,
                explanation="No scorers were configured.",
                details={"scores": {}},
            )

        weighted_sum = 0.0
        total_weight = 0.0
        per_scorer: dict[str, float] = {}

        for scorer in self._scorers:
            score = await scorer.score(task, result, trace)
            weight = self._weights.get(score.scorer_id, 1.0)
            per_scorer[score.scorer_id] = score.value
            weighted_sum += score.value * weight
            total_weight += weight

        composite = weighted_sum / total_weight if total_weight > 0 else 0.0
        return Score(
            scorer_id="composite",
            value=composite,
            explanation="Weighted aggregate across configured scorers.",
            details={"scores": per_scorer, "weights": self._weights},
        )
