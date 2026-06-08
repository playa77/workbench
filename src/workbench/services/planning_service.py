"""Planning Service — AI-powered strategic planning with 9 plan types.

Adapted from PlanExe's worker_plan_internal/ pipeline. Implements key plan
types as structured LLM pipelines using OpenRouterClient. Each plan type has
a dedicated system prompt adapted from PlanExe's prompt templates.

Plan types:
- project_plan: SMART goals, risks, stakeholders, compliance
- swot: Strengths, Weaknesses, Opportunities, Threats
- executive_summary: One-page executive overview
- wbs: Work Breakdown Structure (3 levels)
- schedule: Gantt/timeline estimation
- rca: Root Cause Analysis
- pitch: Pitch deck / proposal
- governance: Governance framework
- team: Team composition
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
# Plan Type Definitions
# ---------------------------------------------------------------------------

PLAN_TYPES: dict[str, dict[str, str]] = {
    "project_plan": {
        "name": "Project Plan",
        "description": (
            "Comprehensive project plan with SMART goals, risk assessment, "
            "stakeholder analysis, compliance, and resource requirements"
        ),
        "icon": "target",
    },
    "swot": {
        "name": "SWOT Analysis",
        "description": (
            "Strengths, Weaknesses, Opportunities, and Threats with "
            "strategic objectives and recommendations"
        ),
        "icon": "grid",
    },
    "executive_summary": {
        "name": "Executive Summary",
        "description": (
            "One-page executive overview with key findings, timeline, "
            "budget estimate, and action orientation"
        ),
        "icon": "file-text",
    },
    "wbs": {
        "name": "Work Breakdown Structure",
        "description": (
            "Hierarchical task breakdown with 3 levels of detail, "
            "dependencies, and duration estimates"
        ),
        "icon": "list",
    },
    "schedule": {
        "name": "Schedule / Timeline",
        "description": (
            "Gantt-style timeline with phases, milestones, durations, "
            "and critical path identification"
        ),
        "icon": "clock",
    },
    "rca": {
        "name": "Root Cause Analysis",
        "description": (
            "5-Why analysis and causal chain tracing to identify root "
            "causes with evidence and remediation actions"
        ),
        "icon": "search",
    },
    "pitch": {
        "name": "Pitch / Proposal",
        "description": (
            "Persuasive pitch with problem statement, solution, market "
            "analysis, competitive advantage, and ask"
        ),
        "icon": "megaphone",
    },
    "governance": {
        "name": "Governance Framework",
        "description": (
            "Governance structure with roles, bodies, decision escalation "
            "matrix, and monitoring mechanisms"
        ),
        "icon": "shield",
    },
    "team": {
        "name": "Team Composition",
        "description": (
            "Team structure with roles, responsibilities, required skills, "
            "and hiring/onboarding recommendations"
        ),
        "icon": "users",
    },
}


def get_plan_types() -> dict[str, dict[str, str]]:
    return dict(PLAN_TYPES)


# ---------------------------------------------------------------------------
# Prompts (adapted from PlanExe)
# ---------------------------------------------------------------------------

SYSTEM_PROMPTS: dict[str, str] = {
    "project_plan": """\
You are an expert project planner. Create a comprehensive and actionable plan
based on the user's description. Output structured sections, not a conversation.

Your plan MUST include these sections with markdown headers:

## Goal Statement
A clear goal adhering to SMART criteria — Specific, Measurable, Achievable,
Relevant, Time-bound. Be concrete about what success looks like.

## Dependencies and Resources
All dependencies, prerequisites, and resources needed. Be specific
about quantities, types, and acquisition strategies.

## Risk Assessment
Identify key risks (3-5). For each: probability (Low/Medium/High), impact,
and specific mitigation strategy. Consider financial, operational, technical,
regulatory, and environmental risks.

## Stakeholder Analysis
Primary and secondary stakeholders. For each: their interest, influence level,
and engagement strategy. Be specific — name actual roles/categories.

## Regulatory & Compliance
Permits, licenses, standards, and regulatory bodies involved. List
concrete compliance actions needed.

## Timeline Overview
Phased timeline with milestones. Estimate durations for key phases.
Identify critical path dependencies.

## Success Metrics
How will success be measured? Specific KPIs or qualitative indicators.
""",

    "swot": """\
You are a strategic analyst conducting a thorough SWOT analysis.
Output structured markdown.

## Strengths
Internal advantages, capabilities, resources. 4-6 well-developed points.
What are we good at? What unique resources do we have?

## Weaknesses
Internal limitations, gaps, vulnerabilities. 4-6 points. Be honest — a
SWOT without weaknesses has no strategic value. What could be improved?
Where are we under-resourced?

## Opportunities
External factors that could be leveraged for advantage. 4-6 points.
Market trends, technological changes, regulatory shifts, partnership potential.

## Threats
External risks, competitive pressures, constraints. 4-6 points.
What obstacles do we face? What are competitors doing? What regulations
or market changes threaten us?

## Strategic Objectives
Based on the analysis above: 3-5 strategic objectives that leverage
strengths, address weaknesses, capture opportunities, and mitigate threats.

## Recommendations
3-5 concrete, prioritized recommendations with rationale.

## Assumptions
Key assumptions underlying this analysis. What would change the assessment
if proven wrong?

After completing the standard SWOT, add:

## Missing Information
What data would strengthen this analysis? What's unknown?

## Questions for Stakeholders
5-7 specific questions to ask to validate or deepen this analysis.
""",

    "executive_summary": """\
You are a seasoned executive producing concise, high-impact summaries.
Write a one-page executive summary of the plan/initiative described.

Your summary must include these sections with markdown headers:

## Focus and Context
Why this plan exists. Hook the reader with the key insight or opportunity.
2-3 sentences.

## Purpose and Goals
Main objectives and success criteria. 2-3 bullets.

## Key Deliverables and Outcomes
Primary deliverables, milestones, expected results. Bulleted list.

## Timeline and Budget
Brief estimate of timeframe and high-level budget/resources needed.

## Risks and Mitigations
1-2 major risks and how they'll be addressed. Concise.

## Action Orientation
Immediate next steps. Who does what by when?

## Overall Takeaway
One sentence summarizing the value proposition or expected ROI.

Keep the entire output to roughly one page worth of content. Be crisp.
Use the active voice. Write for a senior decision-maker with limited time.
""",

    "wbs": """\
You are a project planning engineer creating a Work Breakdown Structure.
Break down the described goal/project into hierarchical work packages.

Output structured markdown:

## Level 1 — Major Work Streams
3-5 top-level work streams that decompose the overall goal.

## Level 2 — Work Packages
For each Level 1 stream, list 3-5 specific work packages.
Format: "L1.WPNumber: Description of work package"

## Level 3 — Tasks
For each Level 2 work package, list 2-4 concrete tasks.
Format: "Task: Description (est. duration, [dependency])"

## Dependency Map
Key dependencies between work packages. What must finish before what starts?
Format: "Task A -> Task B: reason for dependency"

## Duration Estimates
For each Level 1 stream: total estimated duration and effort (person-days).

## Critical Path
Identify the sequence of tasks that determines the minimum project duration.
Explain why this path is critical.

Be specific with task names. Use concrete deliverables, not vague activities.
""",

    "schedule": """\
You are a project scheduler creating a phased timeline.

Output structured markdown:

## Project Phases
List the major phases in chronological order. For each phase:
- Phase name
- Start condition (what triggers this phase)
- Duration estimate
- Key activities (3-5 bullets)
- Deliverables
- End condition / gate criteria

## Milestone Plan
5-8 key milestones with target dates/cadence. Format:
"M#: Milestone Name — Month X — Owner — Success criteria"

## Critical Path
The sequence of activities that must complete on time for the project
to finish on schedule. Identify the critical path explicitly.

## Resource Loading
Peak resource requirements per phase. What skills/roles are most
constrained? When is the busiest period?

## Risk Timeline
When are key risks most likely to materialize during the timeline?
What are the most schedule-sensitive risks?

Be realistic about durations. Include buffer for uncertainty.
Use weeks or months, not exact dates unless provided.
""",

    "rca": """\
You are a root cause analyst applying the 5-Why methodology.

Output structured markdown:

## Problem Statement
Define the problem precisely: what happened, when, where, magnitude.
Include any relevant metrics or impact data.

## Timeline of Events
5-8 key events leading to or surrounding the problem. Chronological order.

## 5-Why Analysis
For each suspected contributing factor, perform 5-Why analysis:

### Chain 1: [initial symptom]
- Why? -> [answer]
- Why? -> [answer]
- Why? -> [answer]
- Why? -> [answer]
- Why? -> [answer (root cause)]

Do 2-3 causal chains to ensure you haven't stopped at a single cause.

## Root Causes Identified
Consolidated list of root causes. Distinguish between:
- Direct causes (immediate triggers)
- Systemic causes (process/structural issues)
- Contributing factors (environment/context)

## Evidence
For each root cause: what evidence supports it? What evidence would
contradict it? Confidence level (Low/Medium/High).

## Remediation Actions
For each root cause: specific corrective action, owner, timeline, and
success criteria. Include both immediate fixes and systemic improvements.

## Prevention
How to prevent recurrence. Process changes, monitoring, training,
governance changes.
""",

    "pitch": """\
You are a pitch strategist creating a persuasive proposal.
Write in a compelling, confident tone suitable for investors or executives.

Output structured markdown:

## Executive Hook
One powerful sentence that captures the essence and value. Make it
memorable. This is your elevator pitch.

## Problem Statement
What problem are you solving? Who experiences this problem? How painful
or costly is it? Quantify where possible. Make the reader feel the pain.

## Solution
Your proposed solution. How does it work? What makes it unique?
Why will it succeed where others have not? Be specific about the mechanism.

## Market Analysis
- Market size (TAM, SAM, SOM if applicable)
- Target audience / customer segment
- Market trends supporting this direction
- Competitive landscape: who else is in this space and how you differ

## Competitive Advantage
Your moat. What protects this? Technology, network effects, brand,
expertise, patents, exclusive partnerships? Why can't this be easily copied?

## Business Model / Approach
How will this create value? Revenue model, cost structure, key metrics.

## Team & Capabilities
What capabilities are needed to execute? What's the current state?

## The Ask
What is needed? Resources, budget, approval, partnership. Be specific
about what you're asking for and what the return will be.

## Risks & Mitigations
2-3 key risks and how you'll address them. Be honest — investors respect
realistic risk assessment more than denial.

## Call to Action
What should the reader do next? Make it easy to say yes.
""",

    "governance": """\
You are an organizational design consultant creating a governance framework.

Output structured markdown:

## Governance Philosophy
2-3 sentences on the governance approach — steering philosophy, key principles.

## Governance Bodies
For each body:
- Name and purpose
- Membership (roles, not names)
- Meeting cadence
- Decision authority (what can they decide vs escalate?)
- Key responsibilities

Typical bodies: Steering Committee, Technical Advisory Board, Change Control
Board, Risk Committee. Adapt to the project scale.

## Decision Escalation Matrix
A structured escalation path:

| Decision Type | Decision Maker | Approval Required | Threshold |
| --- | --- | --- | --- |
| Operational (day-to-day) | Team Lead | None | Routine |
| Tactical (resource allocation) | Steering Committee | Simple majority | < budget threshold |
| Strategic (scope change) | Executive Sponsor | Unanimous | Any budget impact |
| Crisis | Emergency Response Lead | Post-hoc notification | Time-sensitive |

Adapt categories and thresholds to the context.

## Roles & Responsibilities
RACI matrix for key decisions/activities:
- R = Responsible (does the work)
- A = Accountable (approves/signs off)
- C = Consulted (provides input)
- I = Informed (kept updated)

## Monitoring & Reporting
- What KPIs will be tracked?
- Reporting cadence and format
- Escalation triggers (what metrics crossing what threshold triggers escalation?)

## Compliance & Audit
- Regulatory compliance touchpoints
- Audit schedule and scope
- Document retention and versioning

## Meeting Cadence
Regular governance meetings: purpose, attendees, frequency, duration.
""",

    "team": """\
You are an organizational planner designing a team structure.

Output structured markdown:

## Team Structure
Organizational chart (describe in text). Reporting lines. Team size.
Flat, hierarchical, or matrix? Why this structure?

## Roles and Responsibilities
For each role:
- Role title
- Key responsibilities (3-5 bullets)
- Required skills and experience
- Reporting to whom
- Full-time / part-time / contract

## Skill Requirements Matrix
| Skill | Role 1 | Role 2 | Role 3 | Critical Gap? |
| --- | --- | --- | --- | --- |
Map required skills to roles. Identify gaps.

## Team Composition Rationale
Why this specific composition? What trade-offs were made? What
alternatives were considered?

## Onboarding Plan
How will new team members be brought up to speed? First 30/60/90 days.
Documentation, training, mentorship.

## Communication Plan
- Team communication channels and norms
- Meeting cadence (standups, reviews, retros)
- Documentation expectations
- Decision-making process within the team

## Growth Path
How does the team evolve as the project progresses? Phase 1 vs Phase 2
staffing. When to hire additional roles.

## Risks
Team-related risks: single points of failure, skill gaps, availability,
burnout. Mitigation for each.
""",
}

# ---------------------------------------------------------------------------
# Localisation — Section Heading Translations
# ---------------------------------------------------------------------------

_DE_SECTION_HEADINGS: dict[str, str] = {
    "Goal Statement": "Zielsetzung",
    "Dependencies and Resources": "Abhängigkeiten & Ressourcen",
    "Risk Assessment": "Risikobewertung",
    "Stakeholder Analysis": "Stakeholder-Analyse",
    "Regulatory & Compliance": "Regulatorische & Compliance-Aspekte",
    "Timeline Overview": "Zeitplan-Übersicht",
    "Success Metrics": "Erfolgskennzahlen",
    "Strengths": "Stärken",
    "Weaknesses": "Schwächen",
    "Opportunities": "Chancen",
    "Threats": "Risiken",
    "Strategic Objectives": "Strategische Ziele",
    "Recommendations": "Empfehlungen",
    "Assumptions": "Annahmen",
    "Missing Information": "Fehlende Informationen",
    "Questions for Stakeholders": "Fragen an Stakeholder",
    "Focus and Context": "Fokus & Kontext",
    "Purpose and Goals": "Zweck & Ziele",
    "Key Deliverables and Outcomes": "Wichtigste Ergebnisse",
    "Timeline and Budget": "Zeitplan & Budget",
    "Risks and Mitigations": "Risiken & Gegenmaßnahmen",
    "Action Orientation": "Handlungsempfehlungen",
    "Overall Takeaway": "Kernbotschaft",
    "Level 1 — Major Work Streams": "Ebene 1 — Hauptarbeitsstränge",
    "Level 2 — Work Packages": "Ebene 2 — Arbeitspakete",
    "Level 3 — Tasks": "Ebene 3 — Aufgaben",
    "Dependency Map": "Abhängigkeitsdiagramm",
    "Duration Estimates": "Dauerschätzungen",
    "Critical Path": "Kritischer Pfad",
    "Project Phases": "Projektphasen",
    "Milestone Plan": "Meilensteinplan",
    "Resource Loading": "Ressourcenauslastung",
    "Risk Timeline": "Risiko-Zeitplan",
    "Problem Statement": "Problemstellung",
    "Timeline of Events": "Ereignisablauf",
    "5-Why Analysis": "5-Warum-Analyse",
    "Root Causes Identified": "Identifizierte Ursachen",
    "Evidence": "Belege",
    "Remediation Actions": "Korrekturmaßnahmen",
    "Prevention": "Prävention",
    "Executive Hook": "Aufhänger",
    "Solution": "Lösung",
    "Market Analysis": "Marktanalyse",
    "Competitive Advantage": "Wettbewerbsvorteil",
    "Business Model / Approach": "Geschäftsmodell / Ansatz",
    "Team & Capabilities": "Team & Fähigkeiten",
    "The Ask": "Die Anfrage",
    "Call to Action": "Handlungsaufforderung",
    "Governance Philosophy": "Governance-Philosophie",
    "Governance Bodies": "Governance-Gremien",
    "Decision Escalation Matrix": "Entscheidungs-Eskalationsmatrix",
    "Roles & Responsibilities": "Rollen & Verantwortlichkeiten",
    "Monitoring & Reporting": "Monitoring & Berichterstattung",
    "Compliance & Audit": "Compliance & Audit",
    "Meeting Cadence": "Besprechungsrhythmus",
    "Team Structure": "Teamstruktur",
    "Skill Requirements Matrix": "Kompetenzanforderungsmatrix",
    "Team Composition Rationale": "Begründung der Teamzusammensetzung",
    "Onboarding Plan": "Einarbeitungsplan",
    "Communication Plan": "Kommunikationsplan",
    "Growth Path": "Entwicklungspfad",
    "Risks": "Risiken",
}


def _get_section_heading(english_heading: str, language: str) -> str:
    """Translate a section heading to the target language.

    Falls back to the English heading if no translation is available.
    """
    if language in ("de", "german", "de-DE"):
        return _DE_SECTION_HEADINGS.get(english_heading, english_heading)
    return english_heading


def _build_language_instruction(language: str) -> str:
    """Build a language instruction block to prepend to a system prompt.

    For non-English languages, this instructs the LLM to write in that
    language and provides section heading translations.
    """
    if language in ("de", "german", "de-DE"):
        lang_name = "German"
        mappings = "\n".join(
            f"  {eng} -> {_DE_SECTION_HEADINGS[eng]}"
            for eng in sorted(_DE_SECTION_HEADINGS)
        )
        return (
            f"WRITING LANGUAGE: {lang_name}. Write ALL output in {lang_name}.\n"
            f"ALL section headings, labels, and analysis MUST be in {lang_name}.\n"
            f"\n"
            f"Use these translated section headings when writing in {lang_name}:\n"
            f"{mappings}\n"
            f"\n"
            f"---\n\n"
        )
    return ""


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------


class PlanningState(BaseModel):
    run_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    goal: str = ""
    plan_type: str = "project_plan"
    status: str = "PENDING"
    result: str = ""
    model: str = "deepseek/deepseek-v4-pro"
    temperature: float = 0.5
    started_at: str = ""
    completed_at: str = ""
    elapsed_seconds: float = 0.0
    error: str = ""


class DeliberationResult(BaseModel):
    plan_type: str = ""
    content: str = ""
    model: str = ""
    elapsed_seconds: float = 0.0


class PlanningService:
    """Runs a planning pipeline for a given plan type against an LLM.

    Emits SSE events for progress tracking.
    """

    def __init__(self, client: OpenRouterClient) -> None:
        self._client = client
        self._event_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=500)
        self._stop_flag = asyncio.Event()
        self.state = PlanningState()

    def stop(self) -> None:
        self._stop_flag.set()
        self.state.status = "STOPPED"

    async def run(
        self,
        goal: str,
        plan_type: str = "project_plan",
        *,
        language: str = "en",
        model: str = "deepseek/deepseek-v4-pro",
        temperature: float = 0.5,
    ) -> DeliberationResult:
        t0 = time.monotonic()
        run_id = self.state.run_id

        plan_info = PLAN_TYPES.get(plan_type, PLAN_TYPES["project_plan"])
        base_prompt = SYSTEM_PROMPTS.get(
            plan_type, SYSTEM_PROMPTS["project_plan"]
        )
        system_prompt = _build_language_instruction(language) + base_prompt

        self.state = PlanningState(
            run_id=run_id,
            goal=goal,
            plan_type=plan_type,
            status="RUNNING",
            model=model,
            temperature=temperature,
        )

        self._emit(run_id, "started", {
            "plan_type": plan_type,
            "plan_name": plan_info["name"],
            "goal": goal[:200],
        })

        try:
            self._emit(run_id, "phase", {
                "phase": "planning",
                "message": f"Generating {plan_info['name']}...",
            })

            user_prompt = (
                f"Generate a {plan_info['name']} for the following:\n\n{goal}"
            )

            content = await self._client.chat_completion(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                model=model,
                temperature=temperature,
            )

            self.state.result = content
            self.state.status = "COMPLETED"
            elapsed = round(time.monotonic() - t0, 1)
            self.state.elapsed_seconds = elapsed

            self._emit(run_id, "completed", {
                "content_length": len(content),
                "elapsed_seconds": elapsed,
            })

            return DeliberationResult(
                plan_type=plan_type,
                content=content,
                model=model,
                elapsed_seconds=elapsed,
            )

        except Exception as e:
            logger.exception("Planning run %s failed", run_id)
            self.state.status = "ERROR"
            self.state.error = str(e)
            self._emit(run_id, "error", {"message": str(e)})
            raise
        finally:
            self.state.completed_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            self._emit(run_id, "done", {})

    async def event_stream(self) -> AsyncGenerator[str, None]:
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

    def _emit(self, run_id: str, event_type: str, data: Any) -> None:
        payload = {"event": event_type, "data": {"run_id": run_id, **data}}
        with suppress(asyncio.QueueFull):
            self._event_queue.put_nowait(payload)
