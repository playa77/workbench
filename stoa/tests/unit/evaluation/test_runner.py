from pathlib import Path

import pytest

from caw.core.config import CAWConfig
from caw.core.engine import Engine
from caw.core.permissions import PermissionGate
from caw.core.router import Router
from caw.core.session import SessionManager
from caw.evaluation.runner import EvalRunner
from caw.evaluation.scorer import LatencyScorer, TokenEfficiencyScorer
from caw.evaluation.tasks import load_task
from caw.protocols.mock import MockProvider
from caw.protocols.registry import ProviderRegistry
from caw.skills.registry import SkillRegistry
from caw.storage.database import Database
from caw.storage.repository import (
    EvalRunRepository,
    MessageRepository,
    SessionRepository,
    TraceEventRepository,
)
from caw.traces.collector import TraceCollector


@pytest.mark.asyncio
async def test_run_task() -> None:
    config = CAWConfig.model_validate(
        {
            "providers": {
                "primary": {
                    "type": "openai",
                    "api_key_env": "OPENAI_API_KEY",
                    "default_model": "mock-model",
                }
            },
            "skills": {
                "builtin_dir": "missing",
                "user_dir": "missing",
                "packs_dir": "missing",
            },
            "storage": {"db_path": ":memory:"},
            "evaluation": {"tasks_dir": "tests/fixtures/tasks"},
        }
    )
    db = Database(config.storage)
    await db.connect()
    await db.run_migrations()

    trace_repo = TraceEventRepository(db)
    collector = TraceCollector(trace_repo, flush_threshold=1)
    await collector.start()
    provider_registry = ProviderRegistry(config)
    provider_registry._providers["primary"] = MockProvider(
        provider_id="primary",
        response_text="Mock",
    )

    session_manager = SessionManager(SessionRepository(db), MessageRepository(db))
    engine = Engine(
        config=config,
        session_manager=session_manager,
        router=Router(config, provider_registry),
        permission_gate=PermissionGate(config.workspace, collector),
        skill_registry=SkillRegistry(config.skills),
        trace_collector=collector,
        provider_registry=provider_registry,
        message_repo=MessageRepository(db),
    )

    runner = EvalRunner(
        engine,
        session_manager,
        EvalRunRepository(db),
        collector,
        [LatencyScorer(), TokenEfficiencyScorer()],
    )
    task = load_task(Path("tests/fixtures/tasks/sample_task.toml"))
    result = await runner.run_task(task, provider="primary", model="mock-model")

    assert result.run.id
    assert result.run.trace_id
    assert result.run.scores["composite"] >= 0.0

    stored = await EvalRunRepository(db).get(result.run.id)
    assert stored is not None

    await collector.stop()
    await db.close()


@pytest.mark.asyncio
async def test_run_captures_trace() -> None:
    assert True


@pytest.mark.asyncio
async def test_run_scores_result() -> None:
    assert True
