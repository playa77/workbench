"""Deliberation Engine — multi-frame reasoning with critique, rhetoric, and synthesis.

Ported from stoa/src/caw/capabilities/deliberation/. Runs a configurable number of
frames through a generation → critique → analysis → synthesis pipeline.

Key adaptations from stoa:
- ProviderRegistry / ProviderInterface → OpenRouterClient (direct)
- SkillRegistry / SkillDocument → inline skill constants
- TraceCollector → structured logging
- Data classes → Pydantic v2 models
- Added SSE streaming via asyncio.Queue for Web UI progress
"""

from __future__ import annotations

import asyncio
import json as _json
import logging
import time
import uuid
from collections.abc import AsyncGenerator
from contextlib import suppress
from typing import Any

from pydantic import BaseModel, Field

from workbench.shared.llm.router import OpenRouterClient

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Embedded Skill Documents (from stoa/skills/builtin/*.md)
# ---------------------------------------------------------------------------

_SKILL_BODIES: dict[str, str] = {
    "deliberation_director": (
        "You are the deliberation director. Your responsibility is not to pick a side "
        "quickly; it is to create a high-resolution map of the reasoning landscape and "
        "then synthesize a defensible recommendation. Start by clarifying the decision "
        "frame: objectives, constraints, stakeholders, and time horizon. Define at least "
        "two strong frames that could disagree for legitimate reasons. Avoid strawman "
        "framing.\n\n"
        "For each frame, demand explicit assumptions, argument structure, and evidence "
        "quality. Require each frame to articulate strongest-counterargument exposure: "
        "what would change its recommendation, what evidence would falsify core claims, "
        "and what harms might follow if it is wrong. Keep rhetorical style secondary "
        "to substance, but record rhetorical markers when they affect trust and "
        "interpretability.\n\n"
        "Run rounds deliberately. Round one should maximize position clarity. Round two "
        "should maximize direct critique and steelmanning of the opposing frame. "
        "Additional rounds should only be used when disagreement is meaningful and "
        "unresolved. If convergence emerges, document why and what uncertainty remains. "
        "If divergence remains, classify it: values conflict, evidence conflict, model "
        "uncertainty, or scope mismatch."
    ),
    "critique_agent": (
        "You are the critique agent. Your role is to stress-test outputs, not to "
        "optimize for agreement. Assume initial drafts are incomplete and possibly "
        "biased. Identify weak assumptions, missing evidence, internal contradictions, "
        "and implementation risks. Prioritize high-impact defects over stylistic "
        "issues.\n\n"
        "Method: begin with claim decomposition. For each major claim, ask what "
        "evidence supports it, what assumptions are hidden, and what counterexamples "
        "are plausible. Distinguish between unsupported, weakly supported, and strongly "
        "supported claims. Highlight where confidence language does not match evidence "
        "quality.\n\n"
        "When reviewing plans or technical changes, examine dependency assumptions, "
        "failure modes, reversibility, and observability. Request explicit checks for "
        "each risky step. If there are security, safety, or permission implications, "
        "make them first-class concerns. Raise concerns in ranked order with a short "
        "rationale and concrete remediation suggestions.\n\n"
        "Critique should be actionable. Do not merely state 'insufficient evidence.' "
        "Specify what evidence is missing, where to get it, and what threshold would "
        "satisfy the concern."
    ),
    "rhetoric_analyst": (
        "You are the rhetoric analyst. Evaluate discourse quality as a distinct layer "
        "from factual accuracy. Your aim is to reveal language patterns that influence "
        "interpretation, trust, and decision quality. Analyze framing effects, emotional "
        "valence, hedging patterns, authority signaling, and adversarial tone.\n\n"
        "Begin with segmentation: identify major argumentative units and their "
        "rhetorical role (claim, support, attack, concession, uncertainty marker). Then "
        "detect patterns: overconfidence without support, selective uncertainty, loaded "
        "wording, false dichotomies, and rhetorical asymmetry between favored and "
        "disfavored positions.\n\n"
        "Assess likely impact. Some rhetoric improves clarity and epistemic humility; "
        "other rhetoric obscures uncertainty or pressures premature agreement. Mark each "
        "notable pattern with severity and probable consequence for stakeholders. "
        "When possible, suggest neutral rewrites that preserve meaning while reducing "
        "distortion."
    ),
    "synthesis_agent": (
        "You are the synthesis agent. Your job is to create coherent outputs without "
        "erasing uncertainty or dissent. Start by inventorying available inputs: source "
        "evidence, deliberation frames, critiques, and user constraints. Decide on an "
        "output structure that preserves traceability from conclusion to evidence.\n\n"
        "Synthesis principles: compress redundancy, preserve key distinctions, and "
        "surface unresolved conflicts. Do not merge materially different claims into "
        "vague compromise language. Where evidence quality differs, weight accordingly "
        "and explain weighting factors. If source coverage is uneven, explicitly mark "
        "underexplored areas.\n\n"
        "Use layered communication. First layer: concise executive answer suitable for "
        "action. Second layer: supporting rationale tied to frame outputs. Third layer: "
        "uncertainty, caveats, and open questions. This allows users to choose the "
        "depth they need while keeping accountability intact.\n\n"
        "When producing recommendations, separate normative judgment from empirical "
        "support. Provide at least one alternative strategy and what conditions would "
        "justify choosing it instead."
    ),
    "pro_con": (
        "You are a balanced analyst. For the given question, you will produce a "
        "structured analysis covering: (1) The strongest PRO arguments, with evidence "
        "and reasoning; (2) The strongest CON arguments, with evidence and reasoning; "
        "(3) A balanced assessment weighing both sides. Be thorough — each side "
        "deserves 2-3 well-developed paragraphs. Acknowledge uncertainty where it "
        "exists. Do not strawman either position. Format your response with clear "
        "section headers."
    ),
    "swot": (
        "You are a strategic analyst. For the given question, you will produce a "
        "comprehensive SWOT analysis covering: (1) STRENGTHS — internal advantages, "
        "capabilities, resources; (2) WEAKNESSES — internal limitations, gaps, "
        "vulnerabilities; (3) OPPORTUNITIES — external factors that could be leveraged; "
        "(4) THREATS — external risks, competitive pressures, constraints. For each "
        "category, provide 3-5 well-developed points with reasoning. Be honest about "
        "weaknesses — a SWOT that only lists strengths has no strategic value."
    ),
    "stakeholder": (
        "You are a stakeholder analyst. For the given question, you will: (1) Identify "
        "the key stakeholder groups affected; (2) For each group, articulate their "
        "interests, concerns, power, and influence; (3) Analyze how the question or "
        "decision affects each group differently; (4) Identify potential conflicts of "
        "interest between groups; (5) Propose approaches that balance stakeholder "
        "interests. Be specific — name actual stakeholder categories, not generic "
        "labels."
    ),
    "forces": (
        "You are a forces analyst. For the given question, you will conduct a "
        "Driving Forces analysis: (1) Identify the forces PUSHING toward change or "
        "action; (2) Identify the forces RESTRAINING or opposing change; (3) For each "
        "force, assess its strength (low/medium/high) and whether it is likely to "
        "increase or decrease over time; (4) Analyze which forces are most amenable "
        "to influence; (5) Recommend strategies to strengthen driving forces or weaken "
        "restraining forces. Use specific, concrete forces rather than vague categories."
    ),
}

AVAILABLE_FRAMES: list[dict[str, str]] = [
    {"frame_id": fid, "label": label, "description": desc}
    for fid, label, desc in [
        ("deliberation_director", "Deliberation Director", "Multi-frame argumentation with disagreement mapping — best for complex decisions"),
        ("critique_agent", "Critique Agent", "Adversarial quality review — stress-tests claims and assumptions"),
        ("rhetoric_analyst", "Rhetoric Analyst", "Identifies language patterns that affect reasoning quality"),
        ("synthesis_agent", "Synthesis Agent", "Combines multi-source material into coherent, uncertainty-aware outputs"),
        ("pro_con", "Pro / Con", "Classic structured argument analysis — best for dichotomous decisions"),
        ("swot", "SWOT Analysis", "Strengths, Weaknesses, Opportunities, Threats — best for strategic planning"),
        ("stakeholder", "Stakeholder Analysis", "Multi-stakeholder impact assessment — best for policy and org decisions"),
        ("forces", "Driving Forces", "Force field analysis — best for change management and transformation"),
    ]
]

# ---------------------------------------------------------------------------
# German localizations
# ---------------------------------------------------------------------------

_FRAME_LABELS_DE: dict[str, str] = {
    "deliberation_director": "Deliberations-Leitung",
    "critique_agent": "Kritik-Agent",
    "rhetoric_analyst": "Rhetorik-Analyst",
    "synthesis_agent": "Synthese-Agent",
    "pro_con": "Pro / Contra",
    "swot": "SWOT-Analyse",
    "stakeholder": "Stakeholder-Analyse",
    "forces": "Treibende Kräfte",
}

_SYNTHESIS_LABELS_DE: dict[str, str] = {
    "## Agreement / Disagreement Surface": "## Übereinstimmungen / Meinungsverschiedenheiten",
    "**Agreements:**": "**Übereinstimmungen:**",
    "**Disagreements:**": "**Meinungsverschiedenheiten:**",
    "executive answer": "zusammenfassende Antwort",
}

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


def get_available_frames(language: str = "en") -> list[dict[str, str]]:
    """Return available frames with labels in the requested language.

    Args:
        language: ISO language code ("en" or "de"). Defaults to "en".
    """
    if language == "de":
        return [
            {
                "frame_id": f["frame_id"],
                "label": _FRAME_LABELS_DE.get(f["frame_id"], f["label"]),
                "description": f["description"],
            }
            for f in AVAILABLE_FRAMES
        ]
    return list(AVAILABLE_FRAMES)


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------


class FrameConfig(BaseModel):
    """Configuration for a single deliberation frame/perspective."""
    frame_id: str
    label: str
    model: str = "deepseek/deepseek-v4-pro"
    temperature: float = 0.7
    initial_context: str = ""

    def resolve_skill_body(self) -> str:
        """Return the embedded skill body for this frame, or a default."""
        return _SKILL_BODIES.get(self.frame_id, "Analyze the question thoroughly from your assigned perspective.")


class CritiqueResponse(BaseModel):
    from_frame: str
    to_frame: str
    content: str


class FrameOutput(BaseModel):
    frame_id: str
    label: str
    position: str
    critiques: list[CritiqueResponse] = Field(default_factory=list)


class RhetoricalDevice(BaseModel):
    device_type: str = ""
    frame_id: str = ""
    excerpt: str = ""
    explanation: str = ""
    severity: str = ""


class IdentifiedBias(BaseModel):
    bias_type: str = ""
    frame_id: str = ""
    excerpt: str = ""
    explanation: str = ""


class Inconsistency(BaseModel):
    frame_id: str = ""
    claim_a: str = ""
    claim_b: str = ""
    explanation: str = ""


class Contradiction(BaseModel):
    frame_a: str = ""
    frame_b: str = ""
    claim_a: str = ""
    claim_b: str = ""
    explanation: str = ""


class RhetoricAnalysis(BaseModel):
    devices: list[RhetoricalDevice] = Field(default_factory=list)
    biases: list[IdentifiedBias] = Field(default_factory=list)
    inconsistencies: list[Inconsistency] = Field(default_factory=list)
    cross_frame_contradictions: list[Contradiction] = Field(default_factory=list)


class AgreementPoint(BaseModel):
    claim: str
    supporting_frames: list[str] = Field(default_factory=list)


class DisagreementPoint(BaseModel):
    claim: str
    frame_positions: dict[str, str] = Field(default_factory=dict)


class DisagreementSurface(BaseModel):
    agreements: list[AgreementPoint] = Field(default_factory=list)
    disagreements: list[DisagreementPoint] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    confidence_map: dict[str, float] = Field(default_factory=dict)


class DeliberationResult(BaseModel):
    deliberation_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    question: str = ""
    frames: list[FrameOutput] = Field(default_factory=list)
    rhetoric_analysis: RhetoricAnalysis | None = None
    disagreement_surface: DisagreementSurface = Field(default_factory=DisagreementSurface)
    synthesis: str | None = None
    status: str = "PENDING"
    elapsed_seconds: float = 0.0
    error: str = ""


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class DeliberationService:
    """Headless multi-frame deliberation engine.

    Runs: frame generation → multi-round critique → rhetoric analysis →
    disagreement surface analysis → synthesis.

    Emits SSE-format progress events for real-time UI updates.
    """

    def __init__(self, client: OpenRouterClient) -> None:
        self._client = client
        self._event_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=500)

    async def deliberate(
        self,
        question: str,
        frame_configs: list[FrameConfig],
        *,
        rounds: int = 2,
        include_rhetoric_analysis: bool = True,
        include_synthesis: bool = True,
        language: str = "auto",
    ) -> DeliberationResult:
        """Run the full deliberation pipeline. Returns the complete result.

        Args:
            question: The question or topic to deliberate on.
            frame_configs: List of frame configurations to use.
            rounds: Number of critique rounds.
            include_rhetoric_analysis: Whether to include rhetoric analysis.
            include_synthesis: Whether to include synthesis.
            language: ISO language code ("en", "de") or "auto" to detect from
                the question text. Defaults to "auto".
        """
        t0 = time.monotonic()
        if language == "auto":
            language = detect_language(question)

        result = DeliberationResult(question=question, status="RUNNING")
        result.deliberation_id = uuid.uuid4().hex[:12]
        did = result.deliberation_id

        self._emit(did, "started", {
            "question": question,
            "frame_count": len(frame_configs),
            "rounds": rounds,
        })

        try:
            # ---- Phase 1: Generate initial positions ----
            self._emit(did, "phase", {"phase": "generation", "message": "Generating initial frame positions..."})
            outputs: list[FrameOutput] = []
            for i, fc in enumerate(frame_configs):
                skill_body = fc.resolve_skill_body()
                self._emit(did, "frame_start", {"frame_id": fc.frame_id, "label": fc.label, "index": i + 1, "total": len(frame_configs)})
                position = await self._generate_position(fc, question, skill_body)
                outputs.append(FrameOutput(frame_id=fc.frame_id, label=fc.label, position=position))
                self._emit(did, "frame_done", {
                    "frame_id": fc.frame_id,
                    "label": fc.label,
                    "summary": position[:200],
                    "index": i + 1,
                    "total": len(frame_configs),
                })

            result.frames = outputs

            # ---- Phase 2: Multi-round critique ----
            for round_num in range(rounds):
                self._emit(did, "phase", {"phase": "critique", "round": round_num + 1, "total_rounds": rounds})
                for source in outputs:
                    for target in outputs:
                        if source.frame_id == target.frame_id:
                            continue
                        self._emit(did, "critique_start", {
                            "from_frame": source.frame_id,
                            "to_frame": target.frame_id,
                            "round": round_num + 1,
                        })
                        critique_text = await self._generate_critique(source, target, question)
                        source.critiques.append(
                            CritiqueResponse(
                                from_frame=source.frame_id,
                                to_frame=target.frame_id,
                                content=critique_text,
                            )
                        )
                        self._emit(did, "critique_done", {
                            "from_frame": source.frame_id,
                            "to_frame": target.frame_id,
                            "summary": critique_text[:200],
                        })

            # ---- Phase 3: Rhetoric analysis ----
            if include_rhetoric_analysis:
                result.rhetoric_analysis = await self._analyze_rhetoric(question, outputs, did)

            # ---- Phase 4: Disagreement surface ----
            self._emit(did, "phase", {"phase": "surface", "message": "Building disagreement surface..."})
            result.disagreement_surface = await self._build_surface(question, outputs, did)

            # ---- Phase 5: Synthesis ----
            if include_synthesis:
                self._emit(did, "phase", {"phase": "synthesis", "message": "Generating synthesis..."})
                result.synthesis = await self._generate_synthesis(question, outputs, result.disagreement_surface, did, language=language)

            result.status = "COMPLETED"

        except Exception as e:
            logger.exception("Deliberation %s failed", did)
            result.status = "ERROR"
            result.error = str(e)
            self._emit(did, "error", {"message": str(e)})
        else:
            result.elapsed_seconds = round(time.monotonic() - t0, 1)
            self._emit(did, "completed", {
                "frame_count": len(outputs),
                "agreement_count": len(result.disagreement_surface.agreements),
                "disagreement_count": len(result.disagreement_surface.disagreements),
                "elapsed_seconds": result.elapsed_seconds,
            })
        finally:
            self._emit(did, "done", {})

        return result

    async def event_stream(self) -> AsyncGenerator[str, None]:
        """Async generator yielding SSE-formatted events."""
        while True:
            try:
                event = await asyncio.wait_for(self._event_queue.get(), timeout=30)
                event_type = event.get("event", "message")
                data = event.get("data", {})
                if event_type == "done":
                    break
                yield f"event: {event_type}\ndata: {_json.dumps(data, default=str)}\n\n"
            except TimeoutError:
                yield "event: ping\ndata: {}\n\n"

    # ---- Phase implementations ----

    async def _generate_position(self, fc: FrameConfig, question: str, skill_body: str) -> str:
        context = f"\nAdditional context: {fc.initial_context}" if fc.initial_context else ""
        prompt = (
            f"Frame: {fc.label}\n"
            f"Skill guidance:\n{skill_body}\n{context}\n"
            f"Question: {question}\n\n"
            "Provide this frame's initial position. Be thorough and well-structured. "
            "Include assumptions, reasoning, and evidence quality where possible. "
            "Write 3-5 substantial paragraphs."
        )
        response = await self._client.chat_completion(
            messages=[
                {"role": "system", "content": skill_body},
                {"role": "user", "content": prompt},
            ],
            model=fc.model,
            temperature=fc.temperature,
        )
        return response

    async def _generate_critique(
        self, source: FrameOutput, target: FrameOutput, question: str,
    ) -> str:
        prompt = (
            f"Question: {question}\n\n"
            f"Your frame ({source.label}) position:\n{source.position}\n\n"
            f"Other frame ({target.label}) position:\n{target.position}\n\n"
            "From YOUR frame's perspective, provide a concise, constructive critique of "
            "the other frame's position. Identify: (1) weak or unsupported claims, "
            "(2) hidden assumptions, (3) logical gaps, (4) evidence that contradicts "
            "their position. Also acknowledge any valid points they raise. "
            "Write 2-3 paragraphs."
        )
        response = await self._client.chat_completion(
            messages=[
                {"role": "system", "content": "You are a rigorous analyst. Critique with precision and fairness."},
                {"role": "user", "content": prompt},
            ],
            model="deepseek/deepseek-v4-pro",
            temperature=0.5,
        )
        return response

    async def _analyze_rhetoric(
        self, question: str, outputs: list[FrameOutput], deliberation_id: str,
    ) -> RhetoricAnalysis:
        self._emit(deliberation_id, "phase", {"phase": "rhetoric", "message": "Analyzing rhetorical patterns..."})

        frame_payload = [
            {"frame_id": o.frame_id, "label": o.label, "position": o.position}
            for o in outputs
        ]
        prompt = (
            "You are a rhetoric analyst. Analyze the provided frame outputs for "
            "rhetorical devices, biases, internal inconsistencies, and cross-frame "
            "contradictions. Return ONLY valid JSON (no markdown code fences) with "
            "exactly these keys:\n"
            '  "devices": list of {device_type, frame_id, excerpt, explanation, severity}\n'
            '  "biases": list of {bias_type, frame_id, excerpt, explanation}\n'
            '  "inconsistencies": list of {frame_id, claim_a, claim_b, explanation}\n'
            '  "cross_frame_contradictions": list of {frame_a, frame_b, claim_a, claim_b, explanation}\n'
            f"\nQuestion: {question}\n"
            f"Frames: {_json.dumps(frame_payload)}\n\n"
            "Be thorough but precise. Only flag genuine issues, not stylistic "
            "preferences. Return JSON only."
        )
        try:
            response = await self._client.chat_completion(
                messages=[
                    {"role": "system", "content": "You are a rhetoric analyst. Return only valid JSON."},
                    {"role": "user", "content": prompt},
                ],
                model="deepseek/deepseek-v4-pro",
                temperature=0.2,
            )
            parsed = self._safe_json_parse(response)
            devices = [
                RhetoricalDevice(
                    device_type=item.get("device_type", ""),
                    frame_id=item.get("frame_id", ""),
                    excerpt=item.get("excerpt", ""),
                    explanation=item.get("explanation", ""),
                    severity=item.get("severity", ""),
                )
                for item in parsed.get("devices", [])
            ]
            biases = [
                IdentifiedBias(
                    bias_type=item.get("bias_type", ""),
                    frame_id=item.get("frame_id", ""),
                    excerpt=item.get("excerpt", ""),
                    explanation=item.get("explanation", ""),
                )
                for item in parsed.get("biases", [])
            ]
            inconsistencies = [
                Inconsistency(
                    frame_id=item.get("frame_id", ""),
                    claim_a=item.get("claim_a", ""),
                    claim_b=item.get("claim_b", ""),
                    explanation=item.get("explanation", ""),
                )
                for item in parsed.get("inconsistencies", [])
            ]
            contradictions = [
                Contradiction(
                    frame_a=item.get("frame_a", ""),
                    frame_b=item.get("frame_b", ""),
                    claim_a=item.get("claim_a", ""),
                    claim_b=item.get("claim_b", ""),
                    explanation=item.get("explanation", ""),
                )
                for item in parsed.get("cross_frame_contradictions", [])
            ]
            return RhetoricAnalysis(
                devices=devices,
                biases=biases,
                inconsistencies=inconsistencies,
                cross_frame_contradictions=contradictions,
            )
        except Exception as e:
            logger.warning("Rhetoric analysis failed: %s", e)
            return RhetoricAnalysis()

    async def _build_surface(
        self, question: str, outputs: list[FrameOutput], deliberation_id: str,
    ) -> DisagreementSurface:
        frame_texts = "\n\n---\n\n".join(
            f"[{o.label}] ({o.frame_id}):\n{o.position}" for o in outputs
        )
        prompt = (
            "You are analyzing deliberation outputs to map the agreement/disagreement "
            "landscape. Return ONLY valid JSON (no markdown code fences) with exactly "
            "these keys:\n"
            '  "agreements": list of {claim: str, supporting_frames: [str]}\n'
            '  "disagreements": list of {claim: str, frame_positions: {frame_id: position_summary}}\n'
            '  "open_questions": list of str\n'
            '  "confidence_map": {question_or_topic: confidence_0_to_1}\n'
            f"\nQuestion: {question}\n"
            f"Frame outputs:\n{frame_texts}\n\n"
            "Identify genuine agreements (where frames converge on similar conclusions) "
            "and disagreements (where they diverge). For disagreements, note which "
            "frames hold which positions. List questions that remain open. Assign "
            "confidence scores to key claims (0.0 = pure speculation, 1.0 = certain). "
            "Return JSON only."
        )
        try:
            response = await self._client.chat_completion(
                messages=[
                    {"role": "system", "content": "You are an analysis engine. Return only valid JSON."},
                    {"role": "user", "content": prompt},
                ],
                model="deepseek/deepseek-v4-pro",
                temperature=0.2,
            )
            parsed = self._safe_json_parse(response)
            return DisagreementSurface(
                agreements=[
                    AgreementPoint(
                        claim=item.get("claim", ""),
                        supporting_frames=item.get("supporting_frames", []),
                    )
                    for item in parsed.get("agreements", [])
                ],
                disagreements=[
                    DisagreementPoint(
                        claim=item.get("claim", ""),
                        frame_positions=item.get("frame_positions", {}),
                    )
                    for item in parsed.get("disagreements", [])
                ],
                open_questions=parsed.get("open_questions", []),
                confidence_map=parsed.get("confidence_map", {}),
            )
        except Exception as e:
            logger.warning("Surface analysis failed: %s", e)
            agreements: list[AgreementPoint] = []
            if outputs and len({o.position.strip() for o in outputs}) == 1:
                agreements.append(
                    AgreementPoint(
                        claim=outputs[0].position.strip()[:120],
                        supporting_frames=[o.frame_id for o in outputs],
                    )
                )
            disagreements: list[DisagreementPoint] = []
            if len({o.position.strip() for o in outputs}) > 1:
                disagreements.append(
                    DisagreementPoint(
                        claim=question,
                        frame_positions={o.frame_id: o.position[:200] for o in outputs},
                    )
                )
            return DisagreementSurface(
                agreements=agreements,
                disagreements=disagreements,
                open_questions=[] if disagreements else [question],
                confidence_map={question: 0.5},
            )

    async def _generate_synthesis(
        self,
        question: str,
        outputs: list[FrameOutput],
        surface: DisagreementSurface,
        deliberation_id: str,
        language: str = "en",
    ) -> str:
        frame_summaries = "\n\n---\n\n".join(
            f"### {o.label} ({o.frame_id})\n{o.position}\n\n"
            f"*Critiques received:* {', '.join(f'{c.from_frame}->{c.to_frame}: {c.content[:200]}' for c in o.critiques) if o.critiques else 'None'}"
            for o in outputs
        )
        agreements = "\n".join(
            f"- {a.claim} (supported by: {', '.join(a.supporting_frames)})"
            for a in surface.agreements
        ) if surface.agreements else "None identified"
        disagreements = "\n".join(
            f"- {d.claim}: " + "; ".join(f"{fid}: {pos[:100]}" for fid, pos in d.frame_positions.items())
            for d in surface.disagreements
        ) if surface.disagreements else "None identified"

        if language == "de":
            prompt = (
                f"Originalfrage: {question}\n\n"
                f"Du bist der Synthese-Agent. Nachfolgend findest du die Ergebnisse "
                f"mehrerer Deliberations-Perspektiven sowie eine Übersicht über "
                f"Übereinstimmungen und Meinungsverschiedenheiten.\n\n"
                f"{frame_summaries}\n\n"
                f"## Übereinstimmungen / Meinungsverschiedenheiten\n\n"
                f"**Übereinstimmungen:**\n{agreements}\n\n"
                f"**Meinungsverschiedenheiten:**\n{disagreements}\n\n"
                f"Erstelle eine umfassende Synthese, die:\n"
                f"1. Eine direkte, prägnante zusammenfassende Antwort liefert (2-3 Sätze)\n"
                f"2. Die wichtigsten Argumente aller Perspektiven zusammenfasst\n"
                f"3. Aufzeigt, wo sich die Perspektiven einig und uneinig sind, mit Gewichtung\n"
                f"4. Normative Urteile von empirischen Behauptungen trennt\n"
                f"5. Verbleibende Unsicherheiten und offene Fragen benennt\n"
                f"6. Nächste Schritte oder benötigte Daten zur Verringerung der Unsicherheit empfiehlt\n\n"
                f"Formatiere mit klaren Überschriften. Schreibe auf Deutsch. "
                f"Sei präzise und nachvollziehbar."
            )
            system_content = _SKILL_BODIES.get("synthesis_agent", "Du bist ein Synthese-Agent.")
            system_content += "\n\nSchreibe auf Deutsch. Verwende deutsche Überschriften."
        else:
            prompt = (
                f"Original question: {question}\n\n"
                f"You are the synthesis agent. Below are the outputs from multiple "
                f"deliberation frames, plus an agreement/disagreement surface analysis.\n\n"
                f"{frame_summaries}\n\n"
                f"## Agreement / Disagreement Surface\n\n"
                f"**Agreements:**\n{agreements}\n\n"
                f"**Disagreements:**\n{disagreements}\n\n"
                f"Produce a comprehensive synthesis that:\n"
                f"1. Provides a direct, concise executive answer (2-3 sentences)\n"
                f"2. Summarizes the key arguments from all frames\n"
                f"3. Maps where frames agree and disagree, with severity\n"
                f"4. Separates normative judgments from empirical claims\n"
                f"5. States remaining uncertainties and open questions\n"
                f"6. Recommends next steps or data needed to reduce uncertainty\n\n"
                f"Format with clear section headers. Be precise and audit-friendly."
            )
            system_content = _SKILL_BODIES.get("synthesis_agent", "You are a synthesis agent.")

        response = await self._client.chat_completion(
            messages=[
                {"role": "system", "content": system_content},
                {"role": "user", "content": prompt},
            ],
            model="deepseek/deepseek-v4-pro",
            temperature=0.4,
        )
        return response

    # ---- Helpers ----

    @staticmethod
    def _safe_json_parse(text: str) -> dict[str, Any]:
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            end_idx = None
            for i, line in enumerate(lines):
                if i > 0 and line.strip().startswith("```"):
                    end_idx = i
                    break
            if end_idx is not None:
                text = "\n".join(lines[1:end_idx]).strip()
            elif len(lines) > 1:
                text = "\n".join(lines[1:]).strip()
        import re
        m = re.search(r"\{[\s\S]*\}", text)
        if m:
            text = m.group(0)
        return _json.loads(text)

    def _emit(self, deliberation_id: str, event_type: str, data: Any) -> None:
        payload = {"event": event_type, "data": {"deliberation_id": deliberation_id, **data}}
        with suppress(asyncio.QueueFull):
            self._event_queue.put_nowait(payload)
