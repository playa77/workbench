"""Tests for workbench.services.planning_service — PlanningService class."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from workbench.services.planning_service import (
    PLAN_TYPES,
    SYSTEM_PROMPTS,
    DeliberationResult,
    PlanningService,
    PlanningState,
    _build_language_instruction,
    _get_section_heading,
    get_plan_types,
)


# ---------------------------------------------------------------------------
# Unit: Module-level functions
# ---------------------------------------------------------------------------


class TestGetPlanTypes:
    def test_returns_copy_of_plan_types(self):
        result = get_plan_types()
        assert result == PLAN_TYPES
        assert result is not PLAN_TYPES  # must be a copy
        assert len(result) == 9


class TestGetSectionHeading:
    def test_german_returns_translation(self):
        assert _get_section_heading("Goal Statement", "de") == "Zielsetzung"

    def test_german_missing_key_falls_back(self):
        assert _get_section_heading("Nonexistent Heading", "de") == "Nonexistent Heading"

    def test_german_variant_de_DE(self):
        assert _get_section_heading("Strengths", "de-DE") == "Stärken"

    def test_german_variant_german(self):
        assert _get_section_heading("Weaknesses", "german") == "Schwächen"

    def test_english_returns_same(self):
        assert _get_section_heading("Goal Statement", "en") == "Goal Statement"

    def test_generic_language_returns_same(self):
        assert _get_section_heading("Risk Assessment", "fr") == "Risk Assessment"


class TestBuildLanguageInstruction:
    def test_german_returns_instruction_block(self):
        result = _build_language_instruction("de")
        assert "WRITING LANGUAGE: German" in result
        assert "Zielsetzung" in result
        assert "Stärken" in result
        assert result.startswith("WRITING LANGUAGE:")

    def test_german_variant_de_DE(self):
        result = _build_language_instruction("de-DE")
        assert "WRITING LANGUAGE: German" in result

    def test_german_variant_german(self):
        result = _build_language_instruction("german")
        assert "WRITING LANGUAGE: German" in result

    def test_english_returns_empty_string(self):
        assert _build_language_instruction("en") == ""

    def test_other_language_returns_empty_string(self):
        assert _build_language_instruction("fr") == ""


# ---------------------------------------------------------------------------
# Unit: Data models
# ---------------------------------------------------------------------------


class TestPlanningState:
    def test_defaults(self):
        state = PlanningState()
        assert state.run_id
        assert len(state.run_id) == 12
        assert state.goal == ""
        assert state.plan_type == "project_plan"
        assert state.status == "PENDING"
        assert state.result == ""
        assert state.model == "deepseek/deepseek-v4-pro"
        assert state.temperature == 0.5
        assert state.started_at == ""
        assert state.completed_at == ""
        assert state.elapsed_seconds == 0.0
        assert state.error == ""

    def test_custom_values(self):
        state = PlanningState(
            run_id="abc123",
            goal="test goal",
            plan_type="swot",
            status="RUNNING",
            result="some result",
            model="gpt-4",
            temperature=0.8,
            started_at="2024-01-01T00:00:00Z",
            completed_at="2024-01-01T01:00:00Z",
            elapsed_seconds=3600.0,
            error="",
        )
        assert state.run_id == "abc123"
        assert state.goal == "test goal"
        assert state.plan_type == "swot"
        assert state.status == "RUNNING"
        assert state.result == "some result"
        assert state.model == "gpt-4"
        assert state.temperature == 0.8


class TestDeliberationResult:
    def test_defaults(self):
        dr = DeliberationResult()
        assert dr.plan_type == ""
        assert dr.content == ""
        assert dr.model == ""
        assert dr.elapsed_seconds == 0.0

    def test_custom_values(self):
        dr = DeliberationResult(
            plan_type="swot",
            content="# SWOT Analysis\n...",
            model="gpt-4",
            elapsed_seconds=12.5,
        )
        assert dr.plan_type == "swot"
        assert dr.content == "# SWOT Analysis\n..."
        assert dr.model == "gpt-4"
        assert dr.elapsed_seconds == 12.5


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

MOCK_LLM_RESPONSE = "# Generated Plan\n\nThis is a test plan."


@pytest.fixture
def mock_client():
    client = MagicMock()
    client.chat_completion = AsyncMock(return_value=MOCK_LLM_RESPONSE)
    return client


@pytest.fixture
def service(mock_client):
    return PlanningService(mock_client)


# ---------------------------------------------------------------------------
# Tests: PlanningService initialisation
# ---------------------------------------------------------------------------


class TestPlanningServiceInit:
    def test_initialises_correctly(self, mock_client):
        svc = PlanningService(mock_client)
        assert svc._client is mock_client
        assert svc._event_queue.maxsize == 500
        assert not svc._stop_flag.is_set()
        assert isinstance(svc.state, PlanningState)

    def test_stop_sets_flag_and_status(self, service):
        assert not service._stop_flag.is_set()
        assert service.state.status == "PENDING"
        service.stop()
        assert service._stop_flag.is_set()
        assert service.state.status == "STOPPED"


# ---------------------------------------------------------------------------
# Tests: PlanningService.run()
# ---------------------------------------------------------------------------


class TestPlanningServiceRun:
    async def test_happy_path_project_plan(self, service, mock_client):
        result = await service.run(goal="Build a website", plan_type="project_plan")

        assert isinstance(result, DeliberationResult)
        assert result.plan_type == "project_plan"
        assert result.content == MOCK_LLM_RESPONSE
        assert result.model == "deepseek/deepseek-v4-pro"
        assert result.elapsed_seconds >= 0

        # Verify LLM was called with correct messages
        mock_client.chat_completion.assert_awaited_once()
        call_kwargs = mock_client.chat_completion.await_args.kwargs
        assert call_kwargs["model"] == "deepseek/deepseek-v4-pro"
        assert call_kwargs["temperature"] == 0.5
        msgs = call_kwargs["messages"]
        assert msgs[0]["role"] == "system"
        assert msgs[1]["role"] == "user"
        assert "Build a website" in msgs[1]["content"]

        # Verify state
        assert service.state.status == "COMPLETED"
        assert service.state.result == MOCK_LLM_RESPONSE
        assert service.state.elapsed_seconds >= 0

    async def test_happy_path_swot(self, service, mock_client):
        result = await service.run(
            goal="Analyze our startup", plan_type="swot", model="gpt-4", temperature=0.8
        )
        assert result.plan_type == "swot"
        assert result.model == "gpt-4"
        # Verify correct prompt was used
        call_kwargs = mock_client.chat_completion.await_args.kwargs
        assert call_kwargs["temperature"] == 0.8
        assert "SWOT" in call_kwargs["messages"][0]["content"]

    async def test_invalid_plan_type_falls_back_to_project_plan(self, service, mock_client):
        result = await service.run(goal="Test", plan_type="nonexistent")
        assert result.plan_type == "nonexistent"  # stored as-is in result
        # but the system prompt used should be project_plan
        call_kwargs = mock_client.chat_completion.await_args.kwargs
        sys_content = call_kwargs["messages"][0]["content"]
        assert "SMART" in sys_content  # characteristic of project_plan prompt

    async def test_german_language_adds_instruction(self, service, mock_client):
        await service.run(goal="Test", plan_type="project_plan", language="de")
        call_kwargs = mock_client.chat_completion.await_args.kwargs
        sys_content = call_kwargs["messages"][0]["content"]
        assert "WRITING LANGUAGE: German" in sys_content
        assert "Zielsetzung" in sys_content

    async def test_custom_model_and_temperature(self, service, mock_client):
        await service.run(
            goal="Test", plan_type="project_plan", model="custom-model", temperature=0.1
        )
        call_kwargs = mock_client.chat_completion.await_args.kwargs
        assert call_kwargs["model"] == "custom-model"
        assert call_kwargs["temperature"] == 0.1

    async def test_emits_started_phase_completed_done(self, service, mock_client):
        # Collect events
        events = []

        async def collect_events():
            async for event in service.event_stream():
                events.append(event)

        collector = asyncio.create_task(collect_events())
        await asyncio.sleep(0.05)  # let collector start

        await service.run(goal="Test", plan_type="project_plan")

        # Drain remaining events
        await asyncio.sleep(0.1)
        collector.cancel()

        event_types = []
        for e in events:
            line = e.split("\n")[0]
            if line.startswith("event: "):
                event_types.append(line[7:])

        assert "started" in event_types
        assert "phase" in event_types
        assert "completed" in event_types
        # "done" is not yielded — it breaks the stream loop

    async def test_llm_error_propagates(self, service, mock_client):
        mock_client.chat_completion.side_effect = RuntimeError("API failure")

        with pytest.raises(RuntimeError, match="API failure"):
            await service.run(goal="Test", plan_type="project_plan")

        assert service.state.status == "ERROR"
        assert service.state.error == "API failure"

    async def test_error_emits_error_and_done(self, service, mock_client):
        mock_client.chat_completion.side_effect = RuntimeError("API failure")

        events = []

        async def collect_events():
            async for event in service.event_stream():
                events.append(event)

        collector = asyncio.create_task(collect_events())
        await asyncio.sleep(0.05)

        with pytest.raises(RuntimeError):
            await service.run(goal="Test", plan_type="project_plan")

        await asyncio.sleep(0.1)
        collector.cancel()

        event_types = []
        for e in events:
            line = e.split("\n")[0]
            if line.startswith("event: "):
                event_types.append(line[7:])

        assert "error" in event_types
        # "done" is not yielded — it breaks the stream loop

    async def test_completed_at_set_on_success(self, service, mock_client):
        await service.run(goal="Test", plan_type="project_plan")
        assert service.state.completed_at != ""

    async def test_completed_at_set_on_error(self, service, mock_client):
        mock_client.chat_completion.side_effect = RuntimeError("fail")
        with pytest.raises(RuntimeError):
            await service.run(goal="Test", plan_type="project_plan")
        assert service.state.completed_at != ""

    async def test_run_id_preserved_across_runs(self, service, mock_client):
        run_id = service.state.run_id
        await service.run(goal="First", plan_type="project_plan")
        assert service.state.run_id == run_id
        # Second run should reset state but keep run_id
        await service.run(goal="Second", plan_type="project_plan")
        assert service.state.run_id == run_id
        assert service.state.goal == "Second"


# ---------------------------------------------------------------------------
# Tests: event_stream
# ---------------------------------------------------------------------------


class TestEventStream:
    async def test_yields_sse_events(self, service, mock_client):
        events = []

        async def collect():
            async for event in service.event_stream():
                events.append(event)

        collector = asyncio.create_task(collect())
        await asyncio.sleep(0.05)

        # Trigger some events
        service._emit("run-1", "started", {"plan_type": "test"})
        service._emit("run-1", "done", {})
        await asyncio.sleep(0.1)
        collector.cancel()

        assert len(events) >= 1
        assert all(e.startswith("event: ") for e in events)
        # "done" triggers stream exit, not yielded; events before it are delivered
        assert any("started" in e.split("\n")[0] for e in events)

    async def test_timeout_yields_ping(self, service):
        """If no event for 30s, a ping event is yielded."""
        events = []

        async def collect():
            async for event in service.event_stream():
                events.append(event)
                break  # stop after first event

        with patch.object(service._event_queue, "get", side_effect=asyncio.TimeoutError):
            collector = asyncio.create_task(collect())
            await asyncio.sleep(0.1)
            collector.cancel()

        assert len(events) == 1
        assert "event: ping" in events[0]
        assert "data: {}" in events[0]

    async def test_done_breaks_loop(self, service):
        events = []

        async def collect():
            async for event in service.event_stream():
                events.append(event)

        collector = asyncio.create_task(collect())
        await asyncio.sleep(0.05)

        service._emit("run-1", "done", {})
        await asyncio.sleep(0.1)

        # The "done" event causes the stream to break, so collector finishes
        assert len(events) == 0  # no events yielded before done
        collector.cancel()

    async def test_multiple_events_are_delivered(self, service):
        events = []

        async def collect():
            async for event in service.event_stream():
                events.append(event)

        collector = asyncio.create_task(collect())
        await asyncio.sleep(0.05)

        for i in range(3):
            service._emit("run-1", f"event_{i}", {"idx": i})
        service._emit("run-1", "done", {})
        await asyncio.sleep(0.1)
        collector.cancel()

        assert len(events) == 3  # 3 events before "done" (done not yielded)
        assert all("event: event_" in e for e in events)


# ---------------------------------------------------------------------------
# Tests: _emit
# ---------------------------------------------------------------------------


class TestEmit:
    def test_emit_adds_to_queue(self, service):
        service._emit("run-1", "test_event", {"key": "value"})
        assert service._event_queue.qsize() == 1
        payload = service._event_queue.get_nowait()
        assert payload["event"] == "test_event"
        assert payload["data"]["run_id"] == "run-1"
        assert payload["data"]["key"] == "value"

    def test_emit_suppresses_queue_full(self, service):
        """If queue is full, emit should not raise."""
        # Fill the queue past maxsize
        for _ in range(500):
            service._event_queue.put_nowait({"dummy": True})

        # This should not raise
        service._emit("run-1", "overflow", {})
        assert service._event_queue.qsize() == 500  # unchanged
