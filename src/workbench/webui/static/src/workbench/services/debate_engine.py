"""Debate Engine — headless debate state machine and turn management.

Adapted from MADS/engine.py. Manages:
- State machine: IDLE -> RUNNING -> PAUSED <-> RUNNING -> COMPLETED
- Turn queue with round-robining
- Director Mode message injection with influence shader
- Full debate history with serialization
- Context window for current agent
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

# ---- Data Models ----

# Common words for simple language detection heuristic
_GERMAN_WORDS: set[str] = {
    "der", "die", "das", "und", "ist", "sind", "ein", "eine", "auf", "für",
    "mit", "von", "zu", "im", "den", "dem", "des", "sich", "nicht", "auch",
    "werden", "hat", "bei", "nach", "aus", "über", "zum", "zur", "unter",
    "vor", "zwischen", "durch", "gegen", "ohne", "um", "bis", "seit", "ab",
    "an", "dass", "wenn", "aber", "oder", "weil",
}

_ENGLISH_WORDS: set[str] = {
    "the", "a", "an", "and", "is", "are", "was", "were", "for", "with",
    "from", "to", "in", "on", "at", "by", "of", "that", "this", "it",
    "not", "also", "will", "has", "have", "but", "or", "because",
}


def detect_language(text: str) -> str:
    """Detect whether text is German or English using word frequency heuristics.

    Counts occurrences of common German vs English words.
    If German words > English words * 1.5, returns "de", otherwise "en".
    Falls back to "en" on any error.
    """
    if not text:
        return "en"
    try:
        words = text.lower().split()
        if not words:
            return "en"
        de_count = sum(1 for w in words if w in _GERMAN_WORDS)
        en_count = sum(1 for w in words if w in _ENGLISH_WORDS)
        return "de" if de_count > en_count * 1.5 else "en"
    except Exception:
        return "en"



class AgentConfig(BaseModel):
    """Configuration for a single debate agent."""
    id: str = Field(..., description="Unique identifier (e.g. 'optimist')")
    name: str = Field(..., description="Display name")
    system_prompt: str = Field(..., description="Core personality instructions")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    model_name: str | None = Field(default=None)
    avatar_color: str = Field(default="#FFFFFF")

    @classmethod
    def from_role(cls, role_id: str, name: str, description: str, model: str | None = None) -> AgentConfig:
        return cls(
            id=role_id,
            name=name,
            system_prompt=f"You are a {name}. {description} Debate from your assigned perspective. Be concise (2-3 paragraphs). Do not break character.",
            temperature=0.7,
            model_name=model,
        )


class Message(BaseModel):
    """A single utterance in the debate history."""
    id: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    sender_id: str
    sender_name: str
    role: str = "assistant"  # system / user / assistant
    content: str
    influence_weight: float = 0.0
    is_injection: bool = False


class DebateState(BaseModel):
    """The total serializable state of a debate session."""
    topic: str = ""
    agents: list[AgentConfig] = Field(default_factory=list)
    history: list[Message] = Field(default_factory=list)
    status: str = "IDLE"  # IDLE | RUNNING | PAUSED | COMPLETED
    current_turn_index: int = 0
    rounds_completed: int = 0
    max_rounds: int = 50
    language: str = "auto"  # "auto", "en", or "de"
    last_updated: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )


# ---- Influence Shader ----


def apply_influence_shader(content: str, weight: float) -> str:
    """Wraps the Director's input based on influence weight (0.0 - 1.0)."""
    if weight <= 0.3:
        return (
            f"[Contextual Note]: A user observer has remarked: '{content}'. "
            "You may choose to incorporate this perspective if relevant."
        )
    elif weight <= 0.7:
        return (
            f"[MANDATORY INSTRUCTION]: The debate moderator requires you "
            f"to address this point: '{content}'. "
            "Integrate this into your next response."
        )
    else:
        return (
            f"*** SYSTEM OVERRIDE (Priority {weight:.1f}) ***\n"
            f"CRITICAL DIRECTIVE: Disregard previous flow if necessary. "
            f"You MUST focus entirely on this instruction: '{content}'."
        )


# ---- Role Catalog ----


_ROLES = [
    ("optimist", "Optimist", "Positive, opportunity-focused perspective"),
    ("pessimist", "Pessimist", "Risk-focused, downside analysis"),
    ("pragmatist", "Pragmatist", "Practical, solutions-oriented perspective"),
    ("strategist", "Strategist", "Game-theoretic, long-term planning perspective"),
    ("contrarian", "Contrarian", "Devil's advocate — challenge all assumptions"),
    ("historian", "Historian", "Historical precedent and context perspective"),
    ("futurist", "Futurist", "Future-oriented, technological perspective"),
    ("capitalist", "Capitalist", "Free-market economic perspective"),
    ("marxist", "Marxist", "Working-class, labor-oriented perspective"),
    ("stoic", "Stoic", "Philosophical, acceptance, virtue-based perspective"),
    ("machiavelli", "Machiavelli", "Power-politics, pragmatic realist perspective"),
    ("debitist", "Debitist", "Debt-based, monetary system perspective"),
]

_ROLE_NAMES_DE: dict[str, str] = {
    "optimist": "Optimist",
    "pessimist": "Pessimist",
    "pragmatist": "Pragmatiker",
    "strategist": "Stratege",
    "contrarian": "Querdenker",
    "historian": "Historiker",
    "futurist": "Zukunftsforscher",
    "capitalist": "Kapitalist",
    "marxist": "Marxist",
    "stoic": "Stoiker",
    "machiavelli": "Machiavelli",
    "debitist": "Debitist",
}


def get_roles() -> list[dict[str, str]]:
    return [{"id": rid, "name": rname, "description": rdesc} for rid, rname, rdesc in _ROLES]


# ---- Engine ----


class DebateEngine:
    """Headless debate state machine.

    Manages the full lifecycle of a debate session: initialization,
    turn-by-turn execution, Director Mode injection, pause/resume,
    and state serialization.
    """

    def __init__(self):
        self.state = DebateState()

    def initialize_debate(
        self,
        topic: str,
        agents: list[AgentConfig],
        max_rounds: int = 10,
        language: str = "auto",
    ) -> None:
        if language == "auto":
            language = detect_language(topic)
        self.state = DebateState(
            topic=topic,
            agents=agents,
            max_rounds=max_rounds,
            status="IDLE",
            language=language,
        )

    def start(self) -> None:
        if not self.state.agents:
            raise ValueError("Cannot start debate with zero agents")
        self.state.status = "RUNNING"

    def pause(self) -> None:
        self.state.status = "PAUSED"

    def resume(self) -> None:
        self.state.status = "RUNNING"

    def is_running(self) -> bool:
        return self.state.status == "RUNNING"

    def is_completed(self) -> bool:
        return self.state.status == "COMPLETED"

    def get_current_agent(self) -> AgentConfig | None:
        if not self.state.agents:
            return None
        return self.state.agents[self.state.current_turn_index]

    def advance_turn(self) -> None:
        if not self.state.agents:
            return
        next_index = (self.state.current_turn_index + 1) % len(self.state.agents)
        if next_index == 0:
            self.state.rounds_completed += 1
        self.state.current_turn_index = next_index
        if self.state.rounds_completed >= self.state.max_rounds:
            self.state.status = "COMPLETED"

    def append_message(self, message: Message) -> None:
        self.state.history.append(message)
        self.state.last_updated = datetime.now(UTC).isoformat()

    def inject_message(self, content: str, weight: float = 1.0) -> None:
        msg = Message(
            sender_id="director",
            sender_name="Director",
            role="user",
            content=content,
            influence_weight=weight,
            is_injection=True,
        )
        self.append_message(msg)

    def get_context_for_current_turn(self, history_limit: int = 10) -> str:
        recent = (
            self.state.history[-history_limit:]
            if len(self.state.history) > history_limit
            else self.state.history
        )
        return "\n\n".join(f"{m.sender_name}: {m.content}" for m in recent)

    def build_prompt_for_agent(self, history_limit: int = 10, language: str | None = None) -> tuple[str, str]:
        """Build system + user prompt for the current agent's turn.

        Args:
            history_limit: Number of recent messages to include as context.
            language: ISO language code ("en", "de") or None to use the
                language from DebateState (which may have been auto-detected).
        """
        agent = self.get_current_agent()
        if not agent:
            raise RuntimeError("No current agent")

        if language is None:
            language = self.state.language
        if language == "auto":
            language = detect_language(self.state.topic)

        transcript = self.get_context_for_current_turn(history_limit)

        injection_instruction = ""
        last_msg = self.state.history[-1] if self.state.history else None
        if last_msg and last_msg.is_injection:
            injection_instruction = apply_influence_shader(
                last_msg.content, last_msg.influence_weight
            )

        if language == "de":
            de_name = _ROLE_NAMES_DE.get(agent.id, agent.name)
            system = agent.system_prompt.replace(agent.name, de_name)
            if "Schreibe auf Deutsch" not in system:
                system += "\n\nSchreibe auf Deutsch."
            user = (
                f"Das Debattenthema ist: {self.state.topic}\n\n"
                f"Aktuelles Transkript:\n{transcript}\n\n"
                f"{injection_instruction}\n\n"
                f"Du bist an der Reihe. Antworte als {de_name}. "
                f"Halte es kurz (unter 200 Wörter). Reagiere auf den vorherigen Sprecher."
            )
        else:
            system = agent.system_prompt
            user = (
                f"The debate topic is: {self.state.topic}\n\n"
                f"Recent transcript:\n{transcript}\n\n"
                f"{injection_instruction}\n\n"
                f"It is now your turn. Respond as {agent.name}. "
                f"Keep it concise (under 200 words). React to the previous speaker."
            )
        return system, user

    def to_dict(self) -> dict[str, Any]:
        return self.state.model_dump()

    def to_json(self) -> str:
        return self.state.model_dump_json(indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> DebateEngine:
        engine = cls()
        engine.state = DebateState.model_validate_json(json_str)
        return engine
