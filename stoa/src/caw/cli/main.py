"""Command-line interface for serving and operating CAW locally."""

from __future__ import annotations

import asyncio
from pathlib import Path

import click
import uvicorn
from rich.console import Console

from caw.__version__ import __version__
from caw.api.app import create_app
from caw.api.deps import redact_config_for_display
from caw.capabilities.deliberation.engine import DeliberationEngine
from caw.capabilities.deliberation.frames import FrameConfig
from caw.capabilities.research.ingest import IngestPipeline, SourceInput
from caw.capabilities.research.retrieve import Retriever
from caw.capabilities.research.synthesize import Synthesizer
from caw.core.config import load_config
from caw.core.engine import Engine, ExecutionRequest
from caw.core.permissions import PermissionGate
from caw.core.router import Router
from caw.core.session import SessionManager
from caw.evaluation.comparator import Comparator
from caw.evaluation.runner import EvalRunner
from caw.evaluation.scorer import LatencyScorer, TokenEfficiencyScorer
from caw.evaluation.tasks import load_tasks
from caw.models import SessionMode
from caw.protocols.mock import MockProvider
from caw.protocols.registry import ProviderRegistry
from caw.skills.loader import SkillDocument
from caw.skills.registry import SkillRegistry
from caw.storage.database import Database
from caw.storage.repository import (
    EvalRunRepository,
    MessageRepository,
    SessionRepository,
    SourceRepository,
    TraceEventRepository,
)
from caw.traces.collector import TraceCollector

console = Console()


@click.group()
def cli() -> None:
    """Canonical Agent Workbench CLI entrypoint."""


@cli.command("version")
def version_command() -> None:
    """Print CLI and package version."""
    click.echo(__version__)


@cli.group("config")
def config_group() -> None:
    """Configuration display and management commands."""


@config_group.command("show")
def config_show() -> None:
    """Show current merged config with secret-like values redacted."""
    config = load_config()
    redacted = redact_config_for_display(config)
    console.print_json(data=redacted)


@cli.group("db")
def db_group() -> None:
    """Database lifecycle commands."""


@db_group.command("init")
def db_init() -> None:
    """Initialize configured SQLite database and run migrations."""

    async def _run() -> None:
        config = load_config()
        database = Database(config.storage)
        await database.connect()
        try:
            await database.run_migrations()
        finally:
            await database.close()

    asyncio.run(_run())
    click.echo("Database initialized")


@db_group.command("migrate")
def db_migrate() -> None:
    """Run pending migrations on the configured database."""

    async def _run() -> None:
        config = load_config()
        database = Database(config.storage)
        await database.connect()
        try:
            await database.run_migrations()
        finally:
            await database.close()

    asyncio.run(_run())
    click.echo("Migrations complete")


@cli.command("serve")
@click.option("--host", default=None, type=str)
@click.option("--port", default=None, type=int)
def serve(host: str | None, port: int | None) -> None:
    """Start the CAW FastAPI server with uvicorn."""
    config = load_config()
    app = create_app(config)
    uvicorn.run(app, host=host or config.api.host, port=port or config.api.port)


@cli.command("chat")
def chat() -> None:
    """Run a basic interactive terminal chat loop."""

    async def _chat() -> None:
        config = load_config()
        database = Database(config.storage)
        await database.connect()
        await database.run_migrations()

        trace_repo = TraceEventRepository(database)
        collector = TraceCollector(trace_repo, flush_threshold=1)
        await collector.start()

        try:
            provider_registry = ProviderRegistry(config)
            skill_registry = SkillRegistry(config.skills)
            skill_registry.load()

            session_manager = SessionManager(
                SessionRepository(database), MessageRepository(database)
            )
            engine = Engine(
                config=config,
                session_manager=session_manager,
                router=Router(config, provider_registry),
                permission_gate=PermissionGate(config.workspace, collector),
                skill_registry=skill_registry,
                trace_collector=collector,
                provider_registry=provider_registry,
                message_repo=MessageRepository(database),
            )

            session = await session_manager.create(mode=SessionMode.CHAT)
            while True:
                try:
                    content = click.prompt("You", prompt_suffix="> ")
                except (EOFError, KeyboardInterrupt):
                    click.echo()
                    break

                if content.strip().lower() == "exit":
                    break

                result = await engine.execute(
                    ExecutionRequest(session_id=session.id, content=content)
                )
                click.echo(f"Assistant> {result.content}")
        finally:
            await collector.stop()
            await database.close()

    asyncio.run(_chat())


@cli.group("research")
def research_group() -> None:
    """Research workflow commands."""


@research_group.command("ingest")
@click.argument("path", type=click.Path(exists=True, path_type=Path))
def research_ingest(path: Path) -> None:
    """Ingest a source file into a new research session."""

    async def _run() -> None:
        config = load_config()
        database = Database(config.storage)
        await database.connect()
        await database.run_migrations()

        trace_repo = TraceEventRepository(database)
        collector = TraceCollector(trace_repo, flush_threshold=1)
        await collector.start()

        try:
            session_manager = SessionManager(
                SessionRepository(database), MessageRepository(database)
            )
            session = await session_manager.create(mode=SessionMode.RESEARCH)
            pipeline = IngestPipeline(SourceRepository(database), database, collector)
            source = await pipeline.ingest(SourceInput(session_id=session.id, path=path))
            click.echo(f"Ingested source {source.id} into session {session.id}")
        finally:
            await collector.stop()
            await database.close()

    asyncio.run(_run())


@research_group.command("query")
@click.argument("question", type=str)
def research_query(question: str) -> None:
    """Run retrieval + synthesis for a question over existing research sources."""

    async def _run() -> None:
        config = load_config()
        database = Database(config.storage)
        await database.connect()
        await database.run_migrations()

        trace_repo = TraceEventRepository(database)
        collector = TraceCollector(trace_repo, flush_threshold=1)
        await collector.start()

        try:
            provider_registry = ProviderRegistry(config)
            if not provider_registry.list_providers():
                provider_registry._providers["primary"] = MockProvider()
            session_manager = SessionManager(
                SessionRepository(database), MessageRepository(database)
            )
            session = await session_manager.create(mode=SessionMode.RESEARCH)

            retriever = Retriever(database, collector)
            retrieval_results = await retriever.retrieve(question, session.id)
            provider_key = provider_registry.list_providers()[0]
            synthesis = await Synthesizer(
                provider=provider_registry.get(provider_key),
                trace_collector=collector,
                model=config.providers.get(provider_key).default_model
                if provider_key in config.providers
                else "mock-model",
            ).synthesize(question, retrieval_results, session_id=session.id)
            for claim in synthesis.claims:
                click.echo(f"- {claim.text} ({', '.join(claim.citation_ids)})")
        finally:
            await collector.stop()
            await database.close()

    asyncio.run(_run())


@cli.command("deliberate")
@click.argument("question", type=str)
def deliberate(question: str) -> None:
    """Run a deliberation workflow over a question and print the result."""

    async def _run() -> None:
        config = load_config()
        database = Database(config.storage)
        await database.connect()
        await database.run_migrations()

        trace_repo = TraceEventRepository(database)
        collector = TraceCollector(trace_repo, flush_threshold=1)
        await collector.start()

        try:
            provider_registry = ProviderRegistry(config)
            if not provider_registry.list_providers():
                provider_registry._providers["primary"] = MockProvider()

            skill_registry = SkillRegistry(config.skills)
            skill_registry.load()
            if not skill_registry.list_skills():
                skill_registry._skills["caw.deliberation.pro"] = SkillDocument(
                    skill_id="caw.deliberation.pro",
                    version="1.0.0",
                    name="Pro",
                    description="Supportive frame",
                    author="caw",
                    body="Argue in favor of practical execution.",
                )
                skill_registry._skills["caw.deliberation.con"] = SkillDocument(
                    skill_id="caw.deliberation.con",
                    version="1.0.0",
                    name="Con",
                    description="Critical frame",
                    author="caw",
                    body="Challenge assumptions and identify risks.",
                )

            engine = DeliberationEngine(provider_registry, skill_registry, collector)
            result = await engine.deliberate(
                question=question,
                frames=[
                    FrameConfig(frame_id="pro", skill_id="caw.deliberation.pro", label="Pro"),
                    FrameConfig(frame_id="con", skill_id="caw.deliberation.con", label="Con"),
                ],
                session_id="cli-deliberation",
            )
            click.echo(f"Question: {result.question}")
            for frame in result.frames:
                click.echo(f"[{frame.label}] {frame.position}")
        finally:
            await collector.stop()
            await database.close()

    asyncio.run(_run())


@cli.group("eval")
def eval_group() -> None:
    """Evaluation workflow commands."""


@eval_group.command("run")
@click.argument("task_id", type=str)
def eval_run(task_id: str) -> None:
    """Run one evaluation task by task ID."""

    async def _run() -> None:
        config = load_config()
        database = Database(config.storage)
        await database.connect()
        await database.run_migrations()

        trace_repo = TraceEventRepository(database)
        collector = TraceCollector(trace_repo, flush_threshold=1)
        await collector.start()

        try:
            provider_registry = ProviderRegistry(config)
            if not provider_registry.list_providers():
                provider_registry._providers["primary"] = MockProvider()

            skill_registry = SkillRegistry(config.skills)
            skill_registry.load()

            session_manager = SessionManager(
                SessionRepository(database),
                MessageRepository(database),
            )
            engine = Engine(
                config=config,
                session_manager=session_manager,
                router=Router(config, provider_registry),
                permission_gate=PermissionGate(config.workspace, collector),
                skill_registry=skill_registry,
                trace_collector=collector,
                provider_registry=provider_registry,
                message_repo=MessageRepository(database),
            )

            task = next(
                (
                    item
                    for item in load_tasks(Path(config.evaluation.tasks_dir))
                    if item.task_id == task_id
                ),
                None,
            )
            if task is None:
                click.echo(f"Task not found: {task_id}")
                return

            runner = EvalRunner(
                engine=engine,
                session_manager=session_manager,
                eval_repo=EvalRunRepository(database),
                trace_collector=collector,
                scorers=[LatencyScorer(), TokenEfficiencyScorer()],
            )
            result = await runner.run_task(task)
            click.echo(f"Run: {result.run.id}")
            click.echo(f"Scores: {result.run.scores}")
        finally:
            await collector.stop()
            await database.close()

    asyncio.run(_run())


@eval_group.command("compare")
@click.argument("run_id_a", type=str)
@click.argument("run_id_b", type=str)
def eval_compare(run_id_a: str, run_id_b: str) -> None:
    """Compare two evaluation runs by ID."""

    async def _run() -> None:
        config = load_config()
        database = Database(config.storage)
        await database.connect()
        await database.run_migrations()
        try:
            result = await Comparator(EvalRunRepository(database)).compare([run_id_a, run_id_b])
            click.echo(result.matrix)
        finally:
            await database.close()

    asyncio.run(_run())
