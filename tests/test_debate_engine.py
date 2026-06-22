"""Tests for debate_engine — 100% coverage of the pure state machine."""

from __future__ import annotations

import json

import pytest

from workbench.services.debate_engine import (
    AgentConfig,
    DebateEngine,
    DebateState,
    Message,
    _GERMAN_WORDS,
    _ROLE_NAMES_DE,
    apply_influence_shader,
    detect_language,
    get_roles,
)


# =============================================================================
# detect_language
# =============================================================================


class TestDetectLanguage:
    def test_empty_string_returns_en(self):
        assert detect_language("") == "en"

    def test_none_triggers_except_returns_en(self):
        """not None is True, so we get early return "en"."""
        assert detect_language(None) == "en"  # type: ignore[arg-type]

    def test_whitespace_only_returns_en(self):
        assert detect_language("   ") == "en"

    def test_non_string_type_triggers_except_returns_en(self):
        """An int passes the `not text` gate and then .lower() fails → except."""
        assert detect_language(123) == "en"  # type: ignore[arg-type]

    def test_english_dominant_returns_en(self):
        text = "the quick brown fox jumps over the lazy dog"
        assert detect_language(text) == "en"

    def test_german_dominant_returns_de(self):
        text = "der die das und ist sind ein eine auf für mit von zu im den dem"
        assert detect_language(text) == "de"

    def test_german_just_over_threshold_returns_de(self):
        """de_count > en_count * 1.5 → de."""
        text = "der der der der the the"  # 4 de, 2 en → 4 > 3 → de
        assert detect_language(text) == "de"

    def test_german_not_over_threshold_returns_en(self):
        """de_count <= en_count * 1.5 → en."""
        text = "der der der the the the"  # 3 de, 3 en → 3 <= 4.5 → en
        assert detect_language(text) == "en"

    def test_no_known_words_returns_en(self):
        text = "xyzzy frobnicate quux"
        assert detect_language(text) == "en"


# =============================================================================
# apply_influence_shader
# =============================================================================


class TestApplyInfluenceShader:
    def test_weight_zero(self):
        result = apply_influence_shader("Hello", 0.0)
        assert "Contextual Note" in result
        assert "Hello" in result

    def test_weight_zero_three(self):
        result = apply_influence_shader("Hello", 0.3)
        assert "Contextual Note" in result
        assert "Hello" in result

    def test_weight_just_above_three(self):
        result = apply_influence_shader("Point taken", 0.31)
        assert "MANDATORY INSTRUCTION" in result
        assert "Point taken" in result

    def test_weight_zero_seven(self):
        result = apply_influence_shader("Do this", 0.7)
        assert "MANDATORY INSTRUCTION" in result
        assert "Do this" in result

    def test_weight_just_above_seven(self):
        result = apply_influence_shader("Override!", 0.71)
        assert "SYSTEM OVERRIDE" in result
        assert "Override!" in result
        assert "Priority 0.7" in result

    def test_weight_one(self):
        result = apply_influence_shader("Max power", 1.0)
        assert "SYSTEM OVERRIDE" in result
        assert "Max power" in result
        assert "Priority 1.0" in result


# =============================================================================
# get_roles
# =============================================================================


class TestGetRoles:
    def test_returns_list_of_dicts(self):
        roles = get_roles()
        assert isinstance(roles, list)
        assert len(roles) > 0
        for r in roles:
            assert "id" in r
            assert "name" in r
            assert "description" in r
        # Spot-check a few well-known roles
        ids = [r["id"] for r in roles]
        assert "optimist" in ids
        assert "pessimist" in ids
        assert "pragmatist" in ids


# =============================================================================
# AgentConfig
# =============================================================================


class TestAgentConfig:
    def test_minimal_creation(self):
        agent = AgentConfig(id="test", name="Tester", system_prompt="You are a tester.")
        assert agent.id == "test"
        assert agent.name == "Tester"
        assert agent.system_prompt == "You are a tester."
        assert agent.temperature == 0.7
        assert agent.model_name == "deepseek/deepseek-v4-pro"
        assert agent.avatar_color == "#FFFFFF"

    def test_custom_values(self):
        agent = AgentConfig(
            id="custom",
            name="Custom",
            system_prompt="Be custom.",
            temperature=1.5,
            model_name="gpt-4",
            avatar_color="#123456",
        )
        assert agent.temperature == 1.5
        assert agent.model_name == "gpt-4"
        assert agent.avatar_color == "#123456"

    def test_from_role_default_model(self):
        agent = AgentConfig.from_role("optimist", "Optimist", "Positive vibes")
        assert agent.id == "optimist"
        assert agent.name == "Optimist"
        assert "Optimist" in agent.system_prompt
        assert "Positive vibes" in agent.system_prompt
        assert agent.temperature == 0.7
        assert agent.model_name == "deepseek/deepseek-v4-pro"

    def test_from_role_custom_model(self):
        agent = AgentConfig.from_role(
            "pessimist", "Pessimist", "Doom", model="claude-3"
        )
        assert agent.model_name == "claude-3"


# =============================================================================
# Message
# =============================================================================


class TestMessage:
    def test_minimal_creation(self):
        msg = Message(sender_id="a", sender_name="Alice", content="Hello")
        assert msg.sender_id == "a"
        assert msg.sender_name == "Alice"
        assert msg.content == "Hello"
        assert msg.role == "assistant"
        assert msg.influence_weight == 0.0
        assert msg.is_injection is False
        assert msg.id is not None
        assert msg.timestamp is not None

    def test_custom_values(self):
        msg = Message(
            sender_id="b",
            sender_name="Bob",
            role="user",
            content="Hi",
            influence_weight=0.5,
            is_injection=True,
            id="msg-1",
            timestamp="2025-01-01T00:00:00",
        )
        assert msg.id == "msg-1"
        assert msg.timestamp == "2025-01-01T00:00:00"
        assert msg.influence_weight == 0.5
        assert msg.is_injection is True


# =============================================================================
# DebateState
# =============================================================================


class TestDebateState:
    def test_defaults(self):
        state = DebateState()
        assert state.topic == ""
        assert state.agents == []
        assert state.history == []
        assert state.status == "IDLE"
        assert state.current_turn_index == 0
        assert state.rounds_completed == 0
        assert state.max_rounds == 50
        assert state.language == "auto"
        assert state.last_updated is not None


# =============================================================================
# DebateEngine
# =============================================================================


class TestDebateEngineInit:
    def test_initial_state(self):
        engine = DebateEngine()
        assert isinstance(engine.state, DebateState)
        assert engine.state.status == "IDLE"


class TestInitializeDebate:
    def test_auto_detect_language_english(self):
        engine = DebateEngine()
        agents = [AgentConfig(id="a", name="A", system_prompt="")]
        engine.initialize_debate("The future of AI", agents, max_rounds=5, language="auto")
        assert engine.state.topic == "The future of AI"
        assert len(engine.state.agents) == 1
        assert engine.state.max_rounds == 5
        assert engine.state.language == "en"
        assert engine.state.status == "IDLE"

    def test_auto_detect_language_german(self):
        engine = DebateEngine()
        agents = [AgentConfig(id="a", name="A", system_prompt="")]
        engine.initialize_debate("Der Einfluss der KI auf die Gesellschaft", agents, language="auto")
        assert engine.state.language == "de"

    def test_explicit_english(self):
        engine = DebateEngine()
        agents = [AgentConfig(id="a", name="A", system_prompt="")]
        engine.initialize_debate("Topic", agents, language="en")
        assert engine.state.language == "en"

    def test_explicit_german(self):
        engine = DebateEngine()
        agents = [AgentConfig(id="a", name="A", system_prompt="")]
        engine.initialize_debate("Topic", agents, language="de")
        assert engine.state.language == "de"


class TestStart:
    def test_start_sets_status(self):
        engine = DebateEngine()
        engine.initialize_debate("Topic", [AgentConfig(id="a", name="A", system_prompt="")])
        engine.start()
        assert engine.state.status == "RUNNING"

    def test_start_with_no_agents_raises(self):
        engine = DebateEngine()
        engine.state.agents = []
        with pytest.raises(ValueError, match="Cannot start debate with zero agents"):
            engine.start()


class TestPauseResume:
    def test_pause(self):
        engine = DebateEngine()
        engine.state.status = "RUNNING"
        engine.pause()
        assert engine.state.status == "PAUSED"

    def test_resume(self):
        engine = DebateEngine()
        engine.state.status = "PAUSED"
        engine.resume()
        assert engine.state.status == "RUNNING"


class TestIsRunning:
    def test_is_running_true(self):
        engine = DebateEngine()
        engine.state.status = "RUNNING"
        assert engine.is_running() is True

    def test_is_running_false(self):
        engine = DebateEngine()
        engine.state.status = "IDLE"
        assert engine.is_running() is False


class TestIsCompleted:
    def test_is_completed_true(self):
        engine = DebateEngine()
        engine.state.status = "COMPLETED"
        assert engine.is_completed() is True

    def test_is_completed_false(self):
        engine = DebateEngine()
        engine.state.status = "RUNNING"
        assert engine.is_completed() is False


class TestGetCurrentAgent:
    def test_no_agents(self):
        engine = DebateEngine()
        engine.state.agents = []
        assert engine.get_current_agent() is None

    def test_single_agent(self):
        engine = DebateEngine()
        agent = AgentConfig(id="a", name="A", system_prompt="")
        engine.state.agents = [agent]
        assert engine.get_current_agent() == agent

    def test_multiple_agents_respects_index(self):
        engine = DebateEngine()
        a1 = AgentConfig(id="a1", name="A1", system_prompt="")
        a2 = AgentConfig(id="a2", name="A2", system_prompt="")
        engine.state.agents = [a1, a2]
        engine.state.current_turn_index = 1
        assert engine.get_current_agent() == a2


class TestAdvanceTurn:
    def test_no_agents_does_nothing(self):
        engine = DebateEngine()
        engine.state.agents = []
        engine.state.current_turn_index = 5
        engine.advance_turn()
        assert engine.state.current_turn_index == 5

    def test_single_agent_wraps_and_increments_rounds(self):
        engine = DebateEngine()
        engine.state.agents = [AgentConfig(id="a", name="A", system_prompt="")]
        engine.state.current_turn_index = 0
        engine.state.rounds_completed = 0
        engine.advance_turn()
        assert engine.state.current_turn_index == 0  # (0+1)%1 = 0
        assert engine.state.rounds_completed == 1

    def test_two_agents_alternates(self):
        engine = DebateEngine()
        engine.state.agents = [
            AgentConfig(id="a", name="A", system_prompt=""),
            AgentConfig(id="b", name="B", system_prompt=""),
        ]
        engine.state.current_turn_index = 0
        engine.advance_turn()
        assert engine.state.current_turn_index == 1
        assert engine.state.rounds_completed == 0

        engine.advance_turn()
        assert engine.state.current_turn_index == 0  # wrapped
        assert engine.state.rounds_completed == 1

    def test_max_rounds_sets_completed(self):
        engine = DebateEngine()
        engine.state.agents = [AgentConfig(id="a", name="A", system_prompt="")]
        engine.state.rounds_completed = 4
        engine.state.max_rounds = 5
        engine.advance_turn()
        assert engine.state.rounds_completed == 5
        assert engine.state.status == "COMPLETED"

    def test_not_yet_max_rounds_stays_running(self):
        engine = DebateEngine()
        engine.state.status = "RUNNING"
        engine.state.agents = [AgentConfig(id="a", name="A", system_prompt="")]
        engine.state.rounds_completed = 3
        engine.state.max_rounds = 5
        engine.advance_turn()
        assert engine.state.status == "RUNNING"


class TestAppendMessage:
    def test_appends_to_history(self):
        engine = DebateEngine()
        msg = Message(sender_id="a", sender_name="Alice", content="Hello")
        engine.append_message(msg)
        assert len(engine.state.history) == 1
        assert engine.state.history[0] == msg

    def test_updates_last_updated(self):
        engine = DebateEngine()
        original = engine.state.last_updated
        msg = Message(sender_id="a", sender_name="Alice", content="Hi")
        engine.append_message(msg)
        assert engine.state.last_updated != original


class TestInjectMessage:
    def test_creates_director_message_default_weight(self):
        engine = DebateEngine()
        engine.inject_message("Interjection!")
        assert len(engine.state.history) == 1
        msg = engine.state.history[0]
        assert msg.sender_id == "director"
        assert msg.sender_name == "Director"
        assert msg.role == "user"
        assert msg.content == "Interjection!"
        assert msg.influence_weight == 1.0
        assert msg.is_injection is True

    def test_creates_director_message_custom_weight(self):
        engine = DebateEngine()
        engine.inject_message("Soft hint", weight=0.2)
        msg = engine.state.history[0]
        assert msg.influence_weight == 0.2


class TestGetContextForCurrentTurn:
    def test_no_history(self):
        engine = DebateEngine()
        ctx = engine.get_context_for_current_turn(history_limit=5)
        assert ctx == ""

    def test_fewer_than_limit(self):
        engine = DebateEngine()
        engine.state.history = [
            Message(sender_id="a", sender_name="Alice", content="Hi"),
            Message(sender_id="b", sender_name="Bob", content="Hello"),
        ]
        ctx = engine.get_context_for_current_turn(history_limit=10)
        assert "Alice: Hi" in ctx
        assert "Bob: Hello" in ctx

    def test_more_than_limit_returns_last_n(self):
        engine = DebateEngine()
        for i in range(10):
            engine.state.history.append(
                Message(sender_id=str(i), sender_name=f"User{i}", content=f"Msg{i}")
            )
        ctx = engine.get_context_for_current_turn(history_limit=3)
        # Should have only the last 3
        assert "User7: Msg7" in ctx
        assert "User8: Msg8" in ctx
        assert "User9: Msg9" in ctx
        assert "User0: Msg0" not in ctx


class TestBuildPromptForAgent:
    def test_no_agent_raises(self):
        engine = DebateEngine()
        engine.state.agents = []
        with pytest.raises(RuntimeError, match="No current agent"):
            engine.build_prompt_for_agent()

    def test_language_none_uses_state_language(self):
        engine = DebateEngine()
        engine.state.agents = [AgentConfig(id="a", name="AgentA", system_prompt="You are AgentA.")]
        engine.initialize_debate("Test topic", engine.state.agents, language="de")
        system, user = engine.build_prompt_for_agent(language=None)
        assert "Schreibe auf Deutsch" in system
        assert "Du bist an der Reihe" in user

    def test_language_auto_detects_from_topic(self):
        engine = DebateEngine()
        engine.state.agents = [AgentConfig(id="a", name="AgentA", system_prompt="You are AgentA.")]
        engine.initialize_debate("Der Himmel ist blau", engine.state.agents, language="auto")
        system, user = engine.build_prompt_for_agent(language="auto")
        assert "Schreibe auf Deutsch" in system
        assert "Du bist an der Reihe" in user

    def test_english_prompt_build(self):
        engine = DebateEngine()
        agent = AgentConfig(id="a", name="AgentA", system_prompt="You are AgentA. Be helpful.")
        engine.state.agents = [agent]
        engine.state.topic = "Climate change"
        engine.state.language = "en"
        engine.state.history.append(
            Message(sender_id="b", sender_name="Bob", content="I disagree.")
        )
        system, user = engine.build_prompt_for_agent()
        assert system == "You are AgentA. Be helpful."
        assert "The debate topic is: Climate change" in user
        assert "Recent transcript:" in user
        assert "Bob: I disagree." in user
        assert "It is now your turn" in user
        assert "Respond as AgentA" in user

    def test_german_prompt_build_replaces_name_with_different_name(self):
        engine = DebateEngine()
        agent = AgentConfig(
            id="pragmatist", name="Pragmatist", system_prompt="You are Pragmatist."
        )
        engine.state.agents = [agent]
        engine.state.topic = "Die Zukunft"
        engine.state.language = "de"
        system, user = engine.build_prompt_for_agent()
        assert "Pragmatist" not in system
        assert "Pragmatiker" in system

    def test_german_prompt_appends_de_instruction(self):
        engine = DebateEngine()
        agent = AgentConfig(
            id="pragmatist", name="Pragmatist", system_prompt="You are Pragmatist."
        )
        engine.state.agents = [agent]
        engine.state.topic = "Test"
        engine.state.language = "de"
        system, user = engine.build_prompt_for_agent()
        assert "Schreibe auf Deutsch." in system
        assert "Du bist an der Reihe" in user
        assert "Antworte als Pragmatiker" in user

    def test_german_prompt_does_not_duplicate_instruction(self):
        engine = DebateEngine()
        agent = AgentConfig(
            id="pragmatist",
            name="Pragmatist",
            system_prompt="You are Pragmatist.\n\nSchreibe auf Deutsch.",
        )
        engine.state.agents = [agent]
        engine.state.topic = "Test"
        engine.state.language = "de"
        system, user = engine.build_prompt_for_agent()
        # Only one occurrence
        assert system.count("Schreibe auf Deutsch.") == 1

    def test_injection_message_includes_shader(self):
        engine = DebateEngine()
        agent = AgentConfig(id="a", name="AgentA", system_prompt="You are AgentA.")
        engine.state.agents = [agent]
        engine.state.topic = "Topic"
        engine.state.language = "en"
        engine.state.history.append(
            Message(
                sender_id="director",
                sender_name="Director",
                role="user",
                content="Focus on economics",
                influence_weight=0.5,
                is_injection=True,
            )
        )
        system, user = engine.build_prompt_for_agent()
        assert "MANDATORY INSTRUCTION" in user
        assert "Focus on economics" in user

    def test_no_injection_no_shader(self):
        engine = DebateEngine()
        agent = AgentConfig(id="a", name="AgentA", system_prompt="You are AgentA.")
        engine.state.agents = [agent]
        engine.state.topic = "Topic"
        engine.state.language = "en"
        engine.state.history.append(
            Message(sender_id="b", sender_name="Bob", content="Normal message")
        )
        system, user = engine.build_prompt_for_agent()
        assert "MANDATORY INSTRUCTION" not in user
        assert "SYSTEM OVERRIDE" not in user
        assert "Contextual Note" not in user


class TestSerialization:
    def test_to_dict(self):
        engine = DebateEngine()
        engine.state.topic = "Test"
        d = engine.to_dict()
        assert d["topic"] == "Test"
        assert d["status"] == "IDLE"

    def test_to_json(self):
        engine = DebateEngine()
        engine.state.topic = "Test"
        j = engine.to_json()
        parsed = json.loads(j)
        assert parsed["topic"] == "Test"

    def test_from_json_roundtrip(self):
        engine = DebateEngine()
        agent = AgentConfig(id="a", name="A", system_prompt="P.")
        engine.initialize_debate("Topic", [agent])
        engine.start()
        engine.state.history.append(Message(sender_id="a", sender_name="A", content="Hi"))
        json_str = engine.to_json()

        restored = DebateEngine.from_json(json_str)
        assert restored.state.topic == "Topic"
        assert restored.state.status == "RUNNING"
        assert len(restored.state.agents) == 1
        assert restored.state.agents[0].id == "a"
        assert len(restored.state.history) == 1
        assert restored.state.history[0].content == "Hi"


# =============================================================================
# End-to-end integration flows
# =============================================================================


class TestFullDebateFlow:
    def test_basic_two_agent_debate(self):
        engine = DebateEngine()
        optimist = AgentConfig.from_role("optimist", "Optimist", "Positive")
        pessimist = AgentConfig.from_role("pessimist", "Pessimist", "Negative")
        engine.initialize_debate("Is AI good?", [optimist, pessimist], max_rounds=2)
        assert engine.state.status == "IDLE"
        assert engine.state.language == "en"

        engine.start()
        assert engine.is_running()

        # Turn 1: Agent 0 (optimist)
        assert engine.get_current_agent() == optimist
        engine.state.history.append(Message(sender_id="optimist", sender_name="Optimist", content="AI is great!"))
        engine.advance_turn()

        # Turn 2: Agent 1 (pessimist)
        assert engine.get_current_agent() == pessimist
        assert engine.state.rounds_completed == 0
        engine.state.history.append(Message(sender_id="pessimist", sender_name="Pessimist", content="AI is risky!"))
        engine.advance_turn()

        # Round 1 complete, starting round 2
        assert engine.state.rounds_completed == 1

        # Turn 3: Agent 0 (optimist)
        assert engine.get_current_agent() == optimist
        engine.state.history.append(Message(sender_id="optimist", sender_name="Optimist", content="But it helps!"))
        engine.advance_turn()

        # Turn 4: Agent 1 (pessimist)
        assert engine.get_current_agent() == pessimist
        engine.state.history.append(Message(sender_id="pessimist", sender_name="Pessimist", content="Too risky!"))
        engine.advance_turn()

        # Round 2 complete, max_rounds=2 → COMPLETED
        assert engine.state.rounds_completed == 2
        assert engine.is_completed()

    def test_inject_message_during_debate(self):
        engine = DebateEngine()
        agent = AgentConfig(id="a", name="A", system_prompt="You are A.")
        engine.initialize_debate("Topic", [agent])
        engine.start()

        engine.inject_message("Stay on track", weight=0.8)
        assert len(engine.state.history) == 1
        msg = engine.state.history[0]
        assert msg.is_injection

        # Build prompt — should pick up the injection
        system, user = engine.build_prompt_for_agent()
        assert "SYSTEM OVERRIDE" in user

    def test_pause_resume_flow(self):
        engine = DebateEngine()
        agent = AgentConfig(id="a", name="A", system_prompt="")
        engine.initialize_debate("Topic", [agent])
        engine.start()
        assert engine.is_running()

        engine.pause()
        assert not engine.is_running()
        assert engine.state.status == "PAUSED"

        engine.resume()
        assert engine.is_running()

    def test_context_window_pagination(self):
        engine = DebateEngine()
        agent = AgentConfig(id="a", name="A", system_prompt="")
        engine.initialize_debate("Topic", [agent])
        for i in range(20):
            engine.state.history.append(
                Message(sender_id="a", sender_name="A", content=f"Message {i}")
            )
        ctx = engine.get_context_for_current_turn(history_limit=5)
        assert "Message 15" in ctx
        assert "Message 19" in ctx
        assert "Message 0" not in ctx
        # Exactly 5 newlines separating 5 messages = 4 newlines in join
        assert ctx.count("\n\n") == 4
