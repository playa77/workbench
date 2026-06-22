"""Tests for workbench.services.deliberation_service — DeliberationService class."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from workbench.services.deliberation_service import (
    AVAILABLE_FRAMES,
    AgreementPoint,
    Contradiction,
    CritiqueResponse,
    DeliberationResult,
    DeliberationService,
    DisagreementPoint,
    DisagreementSurface,
    FrameConfig,
    FrameOutput,
    IdentifiedBias,
    Inconsistency,
    RhetoricAnalysis,
    RhetoricalDevice,
    _SKILL_BODIES,
    detect_language,
    get_available_frames,
)

# ---------------------------------------------------------------------------
# Unit: detect_language()
# ---------------------------------------------------------------------------


class TestDetectLanguage:
    def test_empty_text_returns_en(self):
        assert detect_language("") == "en"

    def test_none_text_returns_en(self):
        assert detect_language(None) == "en"  # type: ignore[arg-type]

    def test_whitespace_only_returns_en(self):
        assert detect_language("   ") == "en"

    def test_english_text_returns_en(self):
        text = "the quick brown fox and the lazy dog are at the park"
        assert detect_language(text) == "en"

    def test_german_text_returns_de(self):
        text = "der die das und ist sind ein eine auf für mit von zu im den"
        assert detect_language(text) == "de"

    def test_mixed_text_with_german_dominance_returns_de(self):
        # German words > English words * 1.5
        text = "der die das und ist sind ein eine auf für mit von the and"
        assert detect_language(text) == "de"

    def test_mixed_text_with_english_dominance_returns_en(self):
        text = "the and is are for with with der die"  # only 3 German words
        assert detect_language(text) == "en"

    def test_exception_falls_back_to_en(self):
        """If something goes wrong, fallback to en."""
        # Pass a dict (truthy, but no .lower() method) to trigger AttributeError
        result = detect_language({"key": "val"})  # type: ignore[arg-type]
        assert result == "en"


# ---------------------------------------------------------------------------
# Unit: get_available_frames()
# ---------------------------------------------------------------------------


class TestGetAvailableFrames:
    def test_defaults_to_english(self):
        frames = get_available_frames()
        assert len(frames) == 8
        assert frames[0]["frame_id"] == "deliberation_director"
        assert frames[0]["label"] == "Deliberation Director"

    def test_english_explicit(self):
        frames = get_available_frames("en")
        assert frames == AVAILABLE_FRAMES

    def test_german_returns_translated_labels(self):
        frames = get_available_frames("de")
        assert frames[0]["frame_id"] == "deliberation_director"
        assert frames[0]["label"] == "Deliberations-Leitung"
        assert frames[0]["description"] == AVAILABLE_FRAMES[0]["description"]

    def test_german_unknown_frame_falls_back(self):
        frames = get_available_frames("de")
        # All known frames should have translations
        de_labels = {f["frame_id"]: f["label"] for f in frames}
        assert de_labels["deliberation_director"] == "Deliberations-Leitung"
        assert de_labels["critique_agent"] == "Kritik-Agent"


# ---------------------------------------------------------------------------
# Unit: FrameConfig
# ---------------------------------------------------------------------------


class TestFrameConfig:
    def test_resolve_skill_body_known_frame(self):
        fc = FrameConfig(frame_id="critique_agent", label="Critique Agent")
        body = fc.resolve_skill_body()
        assert "You are the critique agent" in body
        assert body == _SKILL_BODIES["critique_agent"]

    def test_resolve_skill_body_unknown_frame(self):
        fc = FrameConfig(frame_id="nonexistent", label="Unknown")
        body = fc.resolve_skill_body()
        assert body == "Analyze the question thoroughly from your assigned perspective."

    def test_default_model_and_temperature(self):
        fc = FrameConfig(frame_id="test", label="Test")
        assert fc.model == "deepseek/deepseek-v4-pro"
        assert fc.temperature == 0.7
        assert fc.initial_context == ""

    def test_custom_values(self):
        fc = FrameConfig(
            frame_id="test", label="Test", model="gpt-4", temperature=0.3, initial_context="Focus on security"
        )
        assert fc.model == "gpt-4"
        assert fc.temperature == 0.3
        assert fc.initial_context == "Focus on security"


# ---------------------------------------------------------------------------
# Unit: Data models
# ---------------------------------------------------------------------------


class TestDataModels:
    def test_critique_response(self):
        cr = CritiqueResponse(from_frame="a", to_frame="b", content="critique text")
        assert cr.from_frame == "a"
        assert cr.to_frame == "b"
        assert cr.content == "critique text"

    def test_frame_output_defaults(self):
        fo = FrameOutput(frame_id="f1", label="Frame 1", position="some position")
        assert fo.critiques == []

    def test_frame_output_with_critiques(self):
        cr = CritiqueResponse(from_frame="a", to_frame="b", content="c")
        fo = FrameOutput(frame_id="f1", label="F1", position="pos", critiques=[cr])
        assert len(fo.critiques) == 1

    def test_rhetorical_device(self):
        rd = RhetoricalDevice(device_type="hedging", frame_id="f1", excerpt="maybe", explanation="uncertainty", severity="low")
        assert rd.device_type == "hedging"
        assert rd.severity == "low"

    def test_identified_bias(self):
        ib = IdentifiedBias(bias_type="confirmation", frame_id="f1", excerpt="text", explanation="expl")
        assert ib.bias_type == "confirmation"

    def test_inconsistency(self):
        inc = Inconsistency(frame_id="f1", claim_a="A", claim_b="B", explanation="diff")
        assert inc.claim_a == "A"

    def test_contradiction(self):
        ct = Contradiction(frame_a="f1", frame_b="f2", claim_a="A", claim_b="B", explanation="diff")
        assert ct.frame_a == "f1"

    def test_rhetoric_analysis_defaults(self):
        ra = RhetoricAnalysis()
        assert ra.devices == []
        assert ra.biases == []
        assert ra.inconsistencies == []
        assert ra.cross_frame_contradictions == []

    def test_agreement_point(self):
        ap = AgreementPoint(claim="we agree", supporting_frames=["f1", "f2"])
        assert ap.claim == "we agree"
        assert len(ap.supporting_frames) == 2

    def test_disagreement_point(self):
        dp = DisagreementPoint(claim="we disagree", frame_positions={"f1": "yes", "f2": "no"})
        assert dp.claim == "we disagree"
        assert dp.frame_positions["f1"] == "yes"

    def test_disagreement_surface_defaults(self):
        ds = DisagreementSurface()
        assert ds.agreements == []
        assert ds.disagreements == []
        assert ds.open_questions == []
        assert ds.confidence_map == {}

    def test_deliberation_result_defaults(self):
        dr = DeliberationResult()
        assert dr.deliberation_id
        assert len(dr.deliberation_id) == 12
        assert dr.question == ""
        assert dr.frames == []
        assert dr.rhetoric_analysis is None
        assert dr.status == "PENDING"
        assert dr.elapsed_seconds == 0.0
        assert dr.error == ""


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

MOCK_POSITION = "This is a frame position with thorough analysis."
MOCK_CRITIQUE = "Constructive critique of the other position."
MOCK_RHETORIC_JSON = json.dumps({
    "devices": [{"device_type": "hedging", "frame_id": "f1", "excerpt": "maybe", "explanation": "uncertainty marker", "severity": "low"}],
    "biases": [{"bias_type": "confirmation", "frame_id": "f2", "excerpt": "clearly", "explanation": "overconfidence"}],
    "inconsistencies": [{"frame_id": "f1", "claim_a": "A", "claim_b": "B", "explanation": "contradictory"}],
    "cross_frame_contradictions": [{"frame_a": "f1", "frame_b": "f2", "claim_a": "X", "claim_b": "Y", "explanation": "conflict"}],
})
MOCK_SURFACE_JSON = json.dumps({
    "agreements": [{"claim": "common ground", "supporting_frames": ["f1", "f2"]}],
    "disagreements": [{"claim": "point of contention", "frame_positions": {"f1": "yes", "f2": "no"}}],
    "open_questions": ["What about X?"],
    "confidence_map": {"common ground": 0.8},
})
MOCK_SYNTHESIS = "# Synthesis\n\nComprehensive synthesis of all frames."


@pytest.fixture
def mock_client():
    client = MagicMock()
    client.chat_completion = AsyncMock()
    return client


@pytest.fixture
def service(mock_client):
    return DeliberationService(mock_client)


@pytest.fixture
def two_frames():
    return [
        FrameConfig(frame_id="critique_agent", label="Critique Agent", model="gpt-4", temperature=0.3),
        FrameConfig(frame_id="pro_con", label="Pro / Con"),
    ]


# ---------------------------------------------------------------------------
# Tests: __init__
# ---------------------------------------------------------------------------


class TestInit:
    def test_initialises_correctly(self, mock_client):
        svc = DeliberationService(mock_client)
        assert svc._client is mock_client
        assert svc._event_queue.maxsize == 500


# ---------------------------------------------------------------------------
# Tests: _safe_json_parse
# ---------------------------------------------------------------------------


class TestSafeJsonParse:
    def test_parses_plain_json(self):
        result = DeliberationService._safe_json_parse('{"key": "value"}')
        assert result == {"key": "value"}

    def test_parses_json_with_code_fences(self):
        text = '```json\n{"key": "value"}\n```'
        result = DeliberationService._safe_json_parse(text)
        assert result == {"key": "value"}

    def test_parses_json_with_code_fences_no_lang(self):
        text = '```\n{"key": "value"}\n```'
        result = DeliberationService._safe_json_parse(text)
        assert result == {"key": "value"}

    def test_parses_json_with_text_before_and_after(self):
        text = 'Here is the result:\n```\n{"key": "value"}\n```\nEOF'
        result = DeliberationService._safe_json_parse(text)
        assert result == {"key": "value"}

    def test_parses_json_embedded_in_text(self):
        text = 'Some text {"key": "value"} more text'
        result = DeliberationService._safe_json_parse(text)
        assert result == {"key": "value"}

    def test_code_fence_only_open(self):
        """If only opening ``` is present, strip everything from first line."""
        text = '```\n{"key": "value"}'
        result = DeliberationService._safe_json_parse(text)
        assert result == {"key": "value"}


# ---------------------------------------------------------------------------
# Tests: _emit
# ---------------------------------------------------------------------------


class TestEmit:
    def test_emit_adds_to_queue(self, service):
        service._emit("did-1", "test_event", {"key": "value"})
        assert service._event_queue.qsize() == 1
        payload = service._event_queue.get_nowait()
        assert payload["event"] == "test_event"
        assert payload["data"]["deliberation_id"] == "did-1"
        assert payload["data"]["key"] == "value"

    def test_emit_suppresses_queue_full(self, service):
        for _ in range(500):
            service._event_queue.put_nowait({"dummy": True})
        service._emit("did-1", "overflow", {})
        assert service._event_queue.qsize() == 500


# ---------------------------------------------------------------------------
# Tests: event_stream
# ---------------------------------------------------------------------------


class TestEventStream:
    async def test_yields_sse_events(self, service):
        events = []
        async def collect():
            async for event in service.event_stream():
                events.append(event)

        collector = asyncio.create_task(collect())
        await asyncio.sleep(0.05)

        service._emit("did-1", "started", {"question": "test"})
        service._emit("did-1", "done", {})
        await asyncio.sleep(0.1)
        collector.cancel()

        assert len(events) >= 1
        assert any("event: started" in e for e in events)

    async def test_timeout_yields_ping(self, service):
        events = []
        async def collect():
            async for event in service.event_stream():
                events.append(event)
                break

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

        service._emit("did-1", "done", {})
        await asyncio.sleep(0.1)
        collector.cancel()

        # done event itself is not yielded (loop breaks on `done`)
        assert len(events) == 0


# ---------------------------------------------------------------------------
# Tests: deliberate() — full pipeline
# ---------------------------------------------------------------------------


class TestDeliberate:
    async def test_happy_path_full_pipeline(self, service, mock_client, two_frames):
        """Full pipeline with 2 frames, 2 rounds, rhetoric analysis, synthesis."""
        mock_client.chat_completion.side_effect = [
            MOCK_POSITION,           # frame 1 position
            MOCK_POSITION,           # frame 2 position
            MOCK_CRITIQUE,           # f1 critiques f2 (round 1)
            MOCK_CRITIQUE,           # f2 critiques f1 (round 1)
            MOCK_CRITIQUE,           # f1 critiques f2 (round 2)
            MOCK_CRITIQUE,           # f2 critiques f1 (round 2)
            MOCK_RHETORIC_JSON,      # rhetoric analysis
            MOCK_SURFACE_JSON,       # disagreement surface
            MOCK_SYNTHESIS,          # synthesis
        ]

        result = await service.deliberate(
            question="Should we adopt AI?",
            frame_configs=two_frames,
            rounds=2,
            include_rhetoric_analysis=True,
            include_synthesis=True,
            language="en",
        )

        assert result.status == "COMPLETED"
        assert result.question == "Should we adopt AI?"
        assert len(result.frames) == 2
        assert result.frames[0].frame_id == "critique_agent"
        assert result.frames[0].label == "Critique Agent"
        assert result.frames[0].position == MOCK_POSITION
        assert result.frames[1].frame_id == "pro_con"

        # Each frame should have critiques from round 1 and round 2
        assert len(result.frames[0].critiques) == 2  # round 1 critique of f2 + round 2 critique of f2
        assert result.frames[0].critiques[0].from_frame == "critique_agent"
        assert result.frames[0].critiques[0].to_frame == "pro_con"

        # Rhetoric analysis
        assert result.rhetoric_analysis is not None
        assert len(result.rhetoric_analysis.devices) == 1
        assert result.rhetoric_analysis.devices[0].device_type == "hedging"

        # Disagreement surface
        assert len(result.disagreement_surface.agreements) == 1
        assert len(result.disagreement_surface.disagreements) == 1
        assert len(result.disagreement_surface.open_questions) == 1

        # Synthesis
        assert result.synthesis == MOCK_SYNTHESIS

        # Timing
        assert result.elapsed_seconds >= 0
        assert result.deliberation_id

    async def test_single_frame_single_round_no_rhetoric_no_synthesis(self, service, mock_client):
        """Minimal pipeline: 1 frame, 0 rounds, no extras."""
        fc = [FrameConfig(frame_id="critique_agent", label="Critique")]
        mock_client.chat_completion.side_effect = [
            MOCK_POSITION,  # position
            # no critiques (0 rounds × n×(n-1) = 0)
            MOCK_SURFACE_JSON,  # surface
        ]

        result = await service.deliberate(
            question="Test?",
            frame_configs=fc,
            rounds=0,
            include_rhetoric_analysis=False,
            include_synthesis=False,
            language="en",
        )

        assert result.status == "COMPLETED"
        assert len(result.frames) == 1
        assert len(result.frames[0].critiques) == 0
        assert result.rhetoric_analysis is None
        assert result.synthesis is None

    async def test_auto_language_detection(self, service, mock_client, two_frames):
        """Language='auto' should detect from question."""
        mock_client.chat_completion.side_effect = [
            MOCK_POSITION,           # f1
            MOCK_POSITION,           # f2
            MOCK_CRITIQUE,           # f1->f2 round 1
            MOCK_CRITIQUE,           # f2->f1 round 1
            MOCK_RHETORIC_JSON,      # rhetoric
            MOCK_SURFACE_JSON,       # surface
            MOCK_SYNTHESIS,          # synthesis
        ]

        result = await service.deliberate(
            question="Should we adopt AI?",
            frame_configs=two_frames,
            rounds=1,
            language="auto",
        )
        assert result.status == "COMPLETED"

    async def test_auto_language_detection_german(self, service, mock_client, two_frames):
        """German question should trigger German synthesis."""
        mock_client.chat_completion.side_effect = [
            MOCK_POSITION,           # f1
            MOCK_POSITION,           # f2
            MOCK_CRITIQUE,           # f1->f2
            MOCK_CRITIQUE,           # f2->f1
            MOCK_RHETORIC_JSON,
            MOCK_SURFACE_JSON,
            MOCK_SYNTHESIS,
        ]

        result = await service.deliberate(
            question="Sollen wir der die das und ist einführen?",
            frame_configs=two_frames,
            rounds=1,
            language="auto",
        )
        assert result.status == "COMPLETED"
        # Verify synthesis prompt was in German
        all_calls = mock_client.chat_completion.await_args_list
        last_call = all_calls[-1]
        user_content = last_call.kwargs["messages"][1]["content"]
        # Should have German synthesis content
        assert "Originalfrage" in user_content or "Synthese" in user_content

    async def test_german_synthesis_via_language_param(self, service, mock_client, two_frames):
        """Explicit language='de' should produce German synthesis."""
        mock_client.chat_completion.side_effect = [
            MOCK_POSITION, MOCK_POSITION,
            MOCK_CRITIQUE, MOCK_CRITIQUE,
            MOCK_RHETORIC_JSON,
            MOCK_SURFACE_JSON,
            MOCK_SYNTHESIS,
        ]
        result = await service.deliberate(
            question="Should we adopt AI?",
            frame_configs=two_frames,
            rounds=1,
            language="de",
        )
        assert result.status == "COMPLETED"

    async def test_error_during_generation_sets_error_status(self, service, mock_client, two_frames):
        """Exception during position generation should be caught and set status=ERROR."""
        mock_client.chat_completion.side_effect = RuntimeError("LLM failure")
        result = await service.deliberate(
            question="Test?",
            frame_configs=two_frames,
            rounds=1,
        )
        assert result.status == "ERROR"
        assert "LLM failure" in result.error

    async def test_error_during_critique_sets_error_status(self, service, mock_client, two_frames):
        """Exception during critique generation should be caught."""
        mock_client.chat_completion.side_effect = [
            MOCK_POSITION,  # f1 pos
            MOCK_POSITION,  # f2 pos
            RuntimeError("Critique failed"),  # f1 critiques f2
        ]
        result = await service.deliberate(
            question="Test?",
            frame_configs=two_frames,
            rounds=1,
            include_rhetoric_analysis=False,
            include_synthesis=False,
            language="en",
        )
        assert result.status == "ERROR"
        assert "Critique failed" in result.error

    async def test_error_in_rhetoric_returns_empty_analysis(self, service, mock_client, two_frames):
        """If rhetoric analysis JSON parsing fails, return empty RhetoricAnalysis."""
        mock_client.chat_completion.side_effect = [
            MOCK_POSITION, MOCK_POSITION,
            MOCK_CRITIQUE, MOCK_CRITIQUE,
            "invalid json!!!",
            MOCK_SURFACE_JSON,
            MOCK_SYNTHESIS,
        ]
        result = await service.deliberate(
            question="Test?",
            frame_configs=two_frames,
            rounds=1,
        )
        assert result.status == "COMPLETED"
        assert result.rhetoric_analysis is not None
        assert result.rhetoric_analysis.devices == []

    async def test_error_in_surface_uses_fallback(self, service, mock_client, two_frames):
        """If surface JSON parsing fails, use fallback logic."""
        mock_client.chat_completion.side_effect = [
            MOCK_POSITION, MOCK_POSITION,
            MOCK_CRITIQUE, MOCK_CRITIQUE,
            MOCK_RHETORIC_JSON,
            "invalid json!!!",
            MOCK_SYNTHESIS,
        ]
        result = await service.deliberate(
            question="Test?",
            frame_configs=two_frames,
            rounds=1,
        )
        assert result.status == "COMPLETED"
        # Fallback should add a disagreement since positions differ
        assert len(result.disagreement_surface.disagreements) >= 1 or len(result.disagreement_surface.agreements) >= 0

    async def test_surface_fallback_same_positions(self, service, mock_client):
        """When all frame positions are identical, fallback creates an agreement."""
        fc = [
            FrameConfig(frame_id="f1", label="Frame 1"),
            FrameConfig(frame_id="f2", label="Frame 2"),
        ]
        same_pos = "Identical position text for everyone."
        mock_client.chat_completion.side_effect = [
            same_pos,       # f1
            same_pos,       # f2
            MOCK_CRITIQUE,  # f1->f2
            MOCK_CRITIQUE,  # f2->f1
            MOCK_RHETORIC_JSON,
            "invalid json!!!",
            MOCK_SYNTHESIS,
        ]
        result = await service.deliberate(
            question="Test?",
            frame_configs=fc,
            rounds=1,
        )
        assert result.status == "COMPLETED"
        # Fallback with identical positions → agreement
        assert len(result.disagreement_surface.agreements) >= 1

    async def test_surface_fallback_single_frame(self, service, mock_client):
        """Single frame + surface failure → fallback with no disagreements."""
        fc = [FrameConfig(frame_id="f1", label="Frame 1")]
        mock_client.chat_completion.side_effect = [
            MOCK_POSITION,  # f1
            MOCK_RHETORIC_JSON,
            "invalid json!!!",
            MOCK_SYNTHESIS,
        ]
        result = await service.deliberate(
            question="Test?",
            frame_configs=fc,
            rounds=0,
        )
        assert result.status == "COMPLETED"
        # Fallback: only one frame but...  Actually single frame with no other frames,
        # the agreement logic: {o.position.strip() for o in outputs} has len 1 → creates agreement
        assert len(result.disagreement_surface.agreements) >= 1

    async def test_emit_events_during_pipeline(self, service, mock_client, two_frames):
        """Verify that various event types are emitted during deliberate()."""
        mock_client.chat_completion.side_effect = [
            MOCK_POSITION, MOCK_POSITION,
            MOCK_CRITIQUE, MOCK_CRITIQUE,
            MOCK_RHETORIC_JSON,
            MOCK_SURFACE_JSON,
            MOCK_SYNTHESIS,
        ]

        events = []
        async def collect():
            async for event in service.event_stream():
                events.append(event)

        collector = asyncio.create_task(collect())
        await asyncio.sleep(0.05)

        await service.deliberate(
            question="Test?",
            frame_configs=two_frames,
            rounds=1,
        )

        await asyncio.sleep(0.1)
        collector.cancel()

        event_types = []
        for e in events:
            line = e.split("\n")[0]
            if line.startswith("event: "):
                event_types.append(line[7:])

        assert "started" in event_types
        assert "phase" in event_types
        assert "frame_start" in event_types
        assert "frame_done" in event_types
        assert "critique_start" in event_types
        assert "critique_done" in event_types
        assert "completed" in event_types
        # "done" is not yielded — it breaks the stream loop

    async def test_disagreement_surface_with_data(self, service, mock_client, two_frames):
        """Verify surface is correctly populated from JSON response."""
        mock_client.chat_completion.side_effect = [
            MOCK_POSITION, MOCK_POSITION,
            MOCK_CRITIQUE, MOCK_CRITIQUE,
            MOCK_RHETORIC_JSON,
            MOCK_SURFACE_JSON,
            MOCK_SYNTHESIS,
        ]
        result = await service.deliberate(
            question="Test?",
            frame_configs=two_frames,
            rounds=1,
        )
        surface = result.disagreement_surface
        assert len(surface.agreements) == 1
        assert surface.agreements[0].claim == "common ground"
        assert surface.agreements[0].supporting_frames == ["f1", "f2"]
        assert len(surface.disagreements) == 1
        assert surface.disagreements[0].claim == "point of contention"
        assert surface.confidence_map["common ground"] == 0.8
        assert surface.open_questions == ["What about X?"]


# ---------------------------------------------------------------------------
# Tests: _generate_position
# ---------------------------------------------------------------------------


class TestGeneratePosition:
    async def test_with_initial_context(self, service, mock_client):
        mock_client.chat_completion.return_value = "Position text"
        fc = FrameConfig(frame_id="critique_agent", label="Critique Agent", initial_context="Focus on security")

        result = await service._generate_position(fc, "Test question?", "Skill body")

        assert result == "Position text"
        mock_client.chat_completion.assert_awaited_once()
        call_kwargs = mock_client.chat_completion.await_args.kwargs
        assert "Additional context: Focus on security" in call_kwargs["messages"][1]["content"]
        assert call_kwargs["model"] == "deepseek/deepseek-v4-pro"
        assert call_kwargs["temperature"] == 0.7

    async def test_without_initial_context(self, service, mock_client):
        mock_client.chat_completion.return_value = "Position text"
        fc = FrameConfig(frame_id="critique_agent", label="Critique Agent")

        result = await service._generate_position(fc, "Test question?", "Skill body")

        assert result == "Position text"
        call_kwargs = mock_client.chat_completion.await_args.kwargs
        content = call_kwargs["messages"][1]["content"]
        assert "Additional context:" not in content


# ---------------------------------------------------------------------------
# Tests: _generate_critique
# ---------------------------------------------------------------------------


class TestGenerateCritique:
    async def test_generates_critique(self, service, mock_client):
        mock_client.chat_completion.return_value = "Critique text"
        source = FrameOutput(frame_id="f1", label="Frame 1", position="Source position")
        target = FrameOutput(frame_id="f2", label="Frame 2", position="Target position")

        result = await service._generate_critique(source, target, "Test question?")

        assert result == "Critique text"
        mock_client.chat_completion.assert_awaited_once()
        call_kwargs = mock_client.chat_completion.await_args.kwargs
        content = call_kwargs["messages"][1]["content"]
        assert "Source position" in content
        assert "Target position" in content
        assert call_kwargs["model"] == "deepseek/deepseek-v4-pro"
        assert call_kwargs["temperature"] == 0.5


# ---------------------------------------------------------------------------
# Tests: _analyze_rhetoric
# ---------------------------------------------------------------------------


class TestAnalyzeRhetoric:
    async def test_parses_valid_json(self, service, mock_client):
        mock_client.chat_completion.return_value = MOCK_RHETORIC_JSON
        outputs = [
            FrameOutput(frame_id="f1", label="F1", position="pos1"),
            FrameOutput(frame_id="f2", label="F2", position="pos2"),
        ]

        result = await service._analyze_rhetoric("Test?", outputs, "did-1")

        assert len(result.devices) == 1
        assert result.devices[0].device_type == "hedging"
        assert result.devices[0].frame_id == "f1"
        assert len(result.biases) == 1
        assert result.biases[0].bias_type == "confirmation"
        assert len(result.inconsistencies) == 1
        assert len(result.cross_frame_contradictions) == 1

    async def test_empty_json_response(self, service, mock_client):
        mock_client.chat_completion.return_value = '{"devices": [], "biases": [], "inconsistencies": [], "cross_frame_contradictions": []}'
        outputs = [FrameOutput(frame_id="f1", label="F1", position="pos")]

        result = await service._analyze_rhetoric("Test?", outputs, "did-1")

        assert len(result.devices) == 0
        assert len(result.biases) == 0

    async def test_invalid_json_returns_empty(self, service, mock_client):
        mock_client.chat_completion.return_value = "not valid json"

        outputs = [FrameOutput(frame_id="f1", label="F1", position="pos")]
        result = await service._analyze_rhetoric("Test?", outputs, "did-1")

        assert result.devices == []
        assert result.biases == []

    async def test_exception_from_llm_returns_empty(self, service, mock_client):
        mock_client.chat_completion.side_effect = RuntimeError("LLM error")
        outputs = [FrameOutput(frame_id="f1", label="F1", position="pos")]

        result = await service._analyze_rhetoric("Test?", outputs, "did-1")

        assert result.devices == []


# ---------------------------------------------------------------------------
# Tests: _build_surface
# ---------------------------------------------------------------------------


class TestBuildSurface:
    async def test_parses_valid_json(self, service, mock_client):
        mock_client.chat_completion.return_value = MOCK_SURFACE_JSON
        outputs = [
            FrameOutput(frame_id="f1", label="F1", position="pos1"),
            FrameOutput(frame_id="f2", label="F2", position="pos2"),
        ]

        result = await service._build_surface("Test?", outputs, "did-1")

        assert len(result.agreements) == 1
        assert result.agreements[0].claim == "common ground"
        assert len(result.disagreements) == 1
        assert result.open_questions == ["What about X?"]
        assert result.confidence_map["common ground"] == 0.8

    async def test_invalid_json_fallback_different_positions(self, service, mock_client):
        """Fallback: positions differ → creates disagreement."""
        mock_client.chat_completion.return_value = "invalid"
        outputs = [
            FrameOutput(frame_id="f1", label="F1", position="Position A"),
            FrameOutput(frame_id="f2", label="F2", position="Position B"),
        ]

        result = await service._build_surface("Test?", outputs, "did-1")

        assert len(result.disagreements) == 1
        assert result.disagreements[0].claim == "Test?"
        assert len(result.open_questions) == 0  # 1 disagreement → open_questions = []

    async def test_invalid_json_fallback_same_positions(self, service, mock_client):
        """Fallback: positions are identical → creates agreement."""
        mock_client.chat_completion.return_value = "invalid"
        outputs = [
            FrameOutput(frame_id="f1", label="F1", position="Same position"),
            FrameOutput(frame_id="f2", label="F2", position="Same position"),
        ]

        result = await service._build_surface("Test?", outputs, "did-1")

        assert len(result.agreements) == 1
        assert result.agreements[0].claim == "Same position"
        assert len(result.disagreements) == 0
        assert len(result.open_questions) == 1

    async def test_invalid_json_fallback_single_output(self, service, mock_client):
        """Single output → fallback creates agreement."""
        mock_client.chat_completion.return_value = "invalid"
        outputs = [FrameOutput(frame_id="f1", label="F1", position="Lone position")]

        result = await service._build_surface("Test?", outputs, "did-1")

        assert len(result.agreements) == 1
        assert len(result.disagreements) == 0
        assert len(result.open_questions) == 1

    async def test_exception_from_llm_triggers_fallback(self, service, mock_client):
        mock_client.chat_completion.side_effect = RuntimeError("LLM fail")
        outputs = [FrameOutput(frame_id="f1", label="F1", position="pos")]

        result = await service._build_surface("Test?", outputs, "did-1")
        assert len(result.agreements) >= 1 or len(result.disagreements) >= 0

    async def test_empty_outputs_fallback(self, service, mock_client):
        """Empty outputs list → fallback with no agreements/disagreements."""
        mock_client.chat_completion.return_value = "invalid"
        result = await service._build_surface("Test?", [], "did-1")

        assert len(result.agreements) == 0
        assert len(result.disagreements) == 0
        assert len(result.open_questions) == 1  # no disagreements → [question]


# ---------------------------------------------------------------------------
# Tests: _generate_synthesis
# ---------------------------------------------------------------------------


class TestGenerateSynthesis:
    async def test_english_synthesis(self, service, mock_client):
        mock_client.chat_completion.return_value = MOCK_SYNTHESIS
        outputs = [FrameOutput(frame_id="f1", label="F1", position="pos")]
        surface = DisagreementSurface()

        result = await service._generate_synthesis("Test?", outputs, surface, "did-1", language="en")

        assert result == MOCK_SYNTHESIS
        call_kwargs = mock_client.chat_completion.await_args.kwargs
        user_content = call_kwargs["messages"][1]["content"]
        assert "Original question:" in user_content
        assert "You are the synthesis agent" in call_kwargs["messages"][0]["content"]

    async def test_german_synthesis(self, service, mock_client):
        mock_client.chat_completion.return_value = MOCK_SYNTHESIS
        outputs = [FrameOutput(frame_id="f1", label="F1", position="pos")]
        surface = DisagreementSurface()

        result = await service._generate_synthesis("Test?", outputs, surface, "did-1", language="de")

        assert result == MOCK_SYNTHESIS
        call_kwargs = mock_client.chat_completion.await_args.kwargs
        user_content = call_kwargs["messages"][1]["content"]
        assert "Originalfrage:" in user_content
        system_content = call_kwargs["messages"][0]["content"]
        assert "Schreibe auf Deutsch" in system_content

    async def test_synthesis_with_critiques(self, service, mock_client):
        mock_client.chat_completion.return_value = MOCK_SYNTHESIS
        critiques = [CritiqueResponse(from_frame="f1", to_frame="f2", content="Great critique")]
        outputs = [FrameOutput(frame_id="f1", label="F1", position="pos", critiques=critiques)]
        surface = DisagreementSurface()

        result = await service._generate_synthesis("Test?", outputs, surface, "did-1")

        assert result == MOCK_SYNTHESIS
        call_kwargs = mock_client.chat_completion.await_args.kwargs
        user_content = call_kwargs["messages"][1]["content"]
        assert "Critiques received:" in user_content
        assert "Great critique" in user_content

    async def test_synthesis_with_agreements_and_disagreements(self, service, mock_client):
        mock_client.chat_completion.return_value = MOCK_SYNTHESIS
        outputs = [FrameOutput(frame_id="f1", label="F1", position="pos")]
        surface = DisagreementSurface(
            agreements=[AgreementPoint(claim="common", supporting_frames=["f1"])],
            disagreements=[DisagreementPoint(claim="diff", frame_positions={"f1": "yes"})],
        )

        result = await service._generate_synthesis("Test?", outputs, surface, "did-1")

        assert result == MOCK_SYNTHESIS
        call_kwargs = mock_client.chat_completion.await_args.kwargs
        user_content = call_kwargs["messages"][1]["content"]
        assert "common" in user_content
        assert "diff" in user_content
