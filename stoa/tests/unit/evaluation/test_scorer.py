from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from caw.core.engine import ExecutionResult
from caw.evaluation.scorer import CompositeScorer, LatencyScorer, TokenEfficiencyScorer
from caw.evaluation.tasks import load_task
from caw.models import TraceEvent

TASK = load_task(Path("tests/fixtures/tasks/sample_task.toml"))


@pytest.mark.asyncio
async def test_latency_scorer() -> None:
    start = datetime.now(UTC)
    trace = [
        TraceEvent(trace_id="t", session_id="s", timestamp=start),
        TraceEvent(
            trace_id="t",
            session_id="s",
            timestamp=start + timedelta(milliseconds=500),
        ),
    ]
    result = ExecutionResult("s", "m", "ok", "model", "provider", 10, 10, 500, "t")

    score = await LatencyScorer().score(TASK, result, trace)
    assert score.scorer_id == "latency"
    assert 0.94 <= score.value <= 0.96


@pytest.mark.asyncio
async def test_token_efficiency_scorer() -> None:
    result = ExecutionResult("s", "m", "word " * 50, "model", "provider", 20, 30, 10, "t")

    score = await TokenEfficiencyScorer().score(TASK, result, [])
    assert score.scorer_id == "token_efficiency"
    assert 0.0 < score.value <= 1.0


@pytest.mark.asyncio
async def test_composite_scorer() -> None:
    result = ExecutionResult("s", "m", "word " * 50, "model", "provider", 20, 30, 10, "t")
    scorers = [LatencyScorer(), TokenEfficiencyScorer()]

    composite = await CompositeScorer(
        scorers,
        {"latency": 2.0, "token_efficiency": 1.0},
    ).score(TASK, result, [])
    assert composite.scorer_id == "composite"
    assert 0.0 < composite.value <= 1.0
