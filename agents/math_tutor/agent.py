"""Math Tutor Agent — step-by-step math problem solving with adaptive competency.

Provides:
- Rich problem input (freeform text with embedded LaTeX equations)
- SSE streaming chat with the LLM tutor
- Adaptive competency tracking (adjusts to student's level)
- Per-concept checkpoint MC questions (optional)
- Comprehensive MC interview covering the entire problem (optional)
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from agents.base import AgentBase
from workbench.core.agents import get_user_agent_settings as _get_agent_settings
from workbench.core.auth import get_current_user, get_user_llm_client
from workbench.core.db import get_session
from workbench.core.models import User
from workbench.shared.llm.router import OpenRouterClient

logger = logging.getLogger(__name__)

SESSION_TTL_SECONDS = 7200

COMPETENCY_LEVELS = [
    "smart_high_school",
    "college_freshman",
    "college_senior",
    "grad_student",
]

COMPETENCY_LABELS = {
    "smart_high_school": "Smart High School Senior",
    "college_freshman": "College Freshman",
    "college_senior": "College Senior",
    "grad_student": "Grad Student",
}

ASSESSMENT_MODES = ["off", "ask_first", "auto"]


@dataclass
class TutorSession:
    session_id: str
    user_id: str
    problem: str
    equation_json: dict[str, Any] | None = None
    equation_latex: str | None = None
    chat_history: list[dict[str, str]] = field(default_factory=list)
    competency_level: str = "smart_high_school"
    assessment_mode: str = "ask_first"
    concepts_covered: list[str] = field(default_factory=list)
    current_concept: str = ""


class MathTutorAgent(AgentBase):
    name = "math-tutor"
    display_name = "Math Tutor"
    description = (
        "Step-by-step math tutor with adaptive competency — discuss "
        "complex problems with embedded equations, get per-concept checkpoints, "
        "and comprehensive MC interviews"
    )
    version = "0.1.0"
    icon = "scale"

    _sessions: ClassVar[dict[str, TutorSession]] = {}
    _session_timestamps: ClassVar[dict[str, float]] = {}

    def _build_router(self) -> APIRouter:
        router = APIRouter()
        router.add_api_route("/start", self.start_session, methods=["POST"])
        router.add_api_route("/chat", self.chat, methods=["POST"])
        router.add_api_route("/deep-dive", self.deep_dive, methods=["POST"])
        router.add_api_route("/equation", self.update_equation, methods=["POST"])
        router.add_api_route("/assess", self.generate_assessment, methods=["POST"])
        router.add_api_route("/assess/answer", self.check_assessment_answer, methods=["POST"])
        router.add_api_route("/session", self.get_session, methods=["GET"])
        router.add_api_route("/session", self.delete_session, methods=["DELETE"])
        return router

    def get_settings_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "initial_competency": {
                    "type": "string",
                    "title": "Initial Competency",
                    "description": "Starting competency level the tutor assumes",
                    "enum": COMPETENCY_LEVELS,
                    "default": "smart_high_school",
                },
                "assessment_mode": {
                    "type": "string",
                    "title": "Assessment Mode",
                    "description": (
                        "off = no MC questions, "
                        "ask_first = ask before quizzing, "
                        "auto = automatic"
                    ),
                    "enum": ASSESSMENT_MODES,
                    "default": "ask_first",
                },
            },
            "additionalProperties": False,
        }

    def get_default_settings(self) -> dict[str, Any]:
        return {
            "initial_competency": "smart_high_school",
            "assessment_mode": "ask_first",
        }

    def get_static_dir(self) -> Path:
        return Path(__file__).parent / "static"

    def get_frontend_tab(self) -> dict:
        return {
            "id": self.name,
            "displayName": self.display_name,
            "icon": self.icon,
            "component": f"agent-{self.name}",
            "js": f"/static/plugins/{self.name}/js/tab.js",
            "css": f"/static/plugins/{self.name}/css/styles.css",
        }

    def _get_user_settings(self, user_id: str, session: AsyncSession) -> dict[str, Any]:
        return {}  # Filled in by the endpoint handler

    async def _require_enabled(self, user: User, session: AsyncSession) -> None:
        user_settings = await _get_agent_settings(str(user.id), session)
        agent_config = user_settings.get(self.name, {})
        if not agent_config.get("enabled", False):
            raise HTTPException(
                status_code=403,
                detail=f"Agent '{self.display_name}' is not enabled. "
                "Enable it in Settings to use this feature.",
            )

    async def on_enable(self, user_id: str, session: AsyncSession) -> None:
        pass

    async def on_disable(self, user_id: str, session: AsyncSession) -> None:
        for sid, ss in list(self._sessions.items()):
            if ss.user_id == user_id:
                self._sessions.pop(sid, None)
                self._session_timestamps.pop(sid, None)
        logger.info(
            "Cleaned up math-tutor sessions for disabled user %s", user_id,
        )

    # ---- Start session ----

    async def start_session(
        self,
        body: StartSessionRequest,
        request: Request,
        user: User = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ):
        await self._require_enabled(user, session)
        client = await get_user_llm_client(user, session, request.app.state.config)

        user_settings = await self._load_user_settings(str(user.id), session)
        competency = user_settings.get("initial_competency", "smart_high_school")
        assessment_mode = user_settings.get("assessment_mode", "ask_first")

        session_id = str(uuid.uuid4())
        tutor_session = TutorSession(
            session_id=session_id,
            user_id=str(user.id),
            problem=body.problem,
            equation_json=body.equation_json,
            equation_latex=body.equation_latex,
            competency_level=competency,
            assessment_mode=assessment_mode,
        )
        self._sessions[session_id] = tutor_session
        self._session_timestamps[session_id] = time.monotonic()

        async def generate_sse():
            try:
                intro = await self._stream_chat_response(
                    client, tutor_session,
                    self._build_system_prompt(tutor_session),
                    "I'm ready to begin. Please introduce yourself, summarize my problem, "
                    "and start walking me through the first step.",
                )
                async for chunk in intro:
                    yield chunk
                yield f"event: session_id\ndata: {json.dumps({'session_id': session_id})}\n\n"
                yield "event: done\ndata: {}\n\n"
            except asyncio.CancelledError:
                yield 'event: error\ndata: {"message": "Client disconnected"}\n\n'
            except Exception:
                logger.exception("Math tutor start error")
                yield 'event: error\ndata: {"message": "An internal error occurred"}\n\n'
            finally:
                await client.close()

        return StreamingResponse(
            generate_sse(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # ---- Chat ----

    async def chat(
        self,
        body: ChatRequest,
        request: Request,
        user: User = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ):
        await self._require_enabled(user, session)
        client = await get_user_llm_client(user, session, request.app.state.config)

        tutor_session = self._sessions.get(body.session_id)
        if not tutor_session or tutor_session.user_id != str(user.id):
            raise HTTPException(status_code=404, detail="Session not found")
        self._session_timestamps[body.session_id] = time.monotonic()

        tutor_session.chat_history.append({"role": "user", "content": body.message})

        async def generate_sse():
            try:
                response = await self._stream_chat_response(
                    client, tutor_session,
                    self._build_system_prompt(tutor_session),
                    body.message,
                )
                full_response = ""
                async for chunk in response:
                    yield chunk
                    if chunk.startswith("data: "):
                        try:
                            data = json.loads(chunk[6:])
                            full_response += data.get("content", "")
                        except (json.JSONDecodeError, KeyError):
                            pass

                tutor_session.chat_history.append({"role": "assistant", "content": full_response})

                if tutor_session.assessment_mode == "auto":
                    concept = self._detect_concept_transition(full_response)
                    if concept:
                        tutor_session.concepts_covered.append(concept)
                        tutor_session.current_concept = concept
                        mcq = await self._generate_mcq(client, tutor_session, concept)
                        yield mcq
                elif tutor_session.assessment_mode == "ask_first":
                    concept = self._detect_concept_transition(full_response)
                    if concept and concept not in tutor_session.concepts_covered:
                        msg = (
                            f'I noticed we covered "{concept}". '
                            "Would you like a quick multiple-choice "
                            "checkpoint before we continue?"
                        )
                        yield (
                            f"event: checkpoint_prompt\n"
                            f"data: {json.dumps({'concept': concept, 'message': msg})}\n\n"
                        )

                yield "event: done\ndata: {}\n\n"
            except asyncio.CancelledError:
                yield 'event: error\ndata: {"message": "Client disconnected"}\n\n'
            except Exception:
                logger.exception("Math tutor chat error")
                yield 'event: error\ndata: {"message": "An internal error occurred"}\n\n'
            finally:
                await client.close()

        return StreamingResponse(
            generate_sse(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # ---- Deep dive ----

    async def deep_dive(
        self,
        body: DeepDiveRequest,
        request: Request,
        user: User = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ):
        await self._require_enabled(user, session)
        client = await get_user_llm_client(user, session, request.app.state.config)

        tutor_session = self._sessions.get(body.session_id)
        if not tutor_session or tutor_session.user_id != str(user.id):
            raise HTTPException(status_code=404, detail="Session not found")
        self._session_timestamps[body.session_id] = time.monotonic()

        dive_prompt = (
            f"The student wants to deep-dive into: {body.topic}\n"
            f"Context: {body.context}\n"
            "Explain this in thorough detail, connecting it to the broader problem. "
            "Break it down from first principles. The student may ask follow-ups."
        )
        tutor_session.chat_history.append({"role": "user", "content": dive_prompt})

        async def generate_sse():
            try:
                response = await self._stream_chat_response(
                    client, tutor_session,
                    self._build_system_prompt(tutor_session),
                    dive_prompt,
                )
                full_response = ""
                async for chunk in response:
                    yield chunk
                    if chunk.startswith("data: "):
                        try:
                            data = json.loads(chunk[6:])
                            full_response += data.get("content", "")
                        except (json.JSONDecodeError, KeyError):
                            pass
                tutor_session.chat_history.append({"role": "assistant", "content": full_response})
                yield "event: done\ndata: {}\n\n"
            except asyncio.CancelledError:
                yield 'event: error\ndata: {"message": "Client disconnected"}\n\n'
            except Exception:
                logger.exception("Math tutor deep dive error")
                yield 'event: error\ndata: {"message": "An internal error occurred"}\n\n'
            finally:
                await client.close()

        return StreamingResponse(
            generate_sse(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # ---- Update equation (mid-session) ----

    async def update_equation(
        self,
        body: EquationUpdateRequest,
        request: Request,
        user: User = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ):
        await self._require_enabled(user, session)
        client = await get_user_llm_client(user, session, request.app.state.config)

        tutor_session = self._sessions.get(body.session_id)
        if not tutor_session or tutor_session.user_id != str(user.id):
            raise HTTPException(status_code=404, detail="Session not found")
        self._session_timestamps[body.session_id] = time.monotonic()

        if body.equation_json is not None:
            tutor_session.equation_json = body.equation_json
        if body.equation_latex is not None:
            tutor_session.equation_latex = body.equation_latex

        message = (
            "I'd like to introduce a new equation to our discussion:\n\n"
            f"$${body.equation_latex or ''}$$\n\n"
            f"{body.context or ''}"
        )
        tutor_session.chat_history.append({"role": "user", "content": message})

        async def generate_sse():
            try:
                response = await self._stream_chat_response(
                    client, tutor_session,
                    self._build_system_prompt(tutor_session),
                    message,
                )
                full_response = ""
                async for chunk in response:
                    yield chunk
                    if chunk.startswith("data: "):
                        try:
                            data = json.loads(chunk[6:])
                            full_response += data.get("content", "")
                        except (json.JSONDecodeError, KeyError):
                            pass
                tutor_session.chat_history.append(
                    {"role": "assistant", "content": full_response}
                )
                yield "event: done\ndata: {}\n\n"
            except asyncio.CancelledError:
                yield 'event: error\ndata: {"message": "Client disconnected"}\n\n'
            except Exception:
                logger.exception("Math tutor equation update error")
                yield 'event: error\ndata: {"message": "An internal error occurred"}\n\n'
            finally:
                await client.close()

        return StreamingResponse(
            generate_sse(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # ---- Assessment ----

    async def generate_assessment(
        self,
        body: AssessmentRequest,
        request: Request,
        user: User = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ):
        await self._require_enabled(user, session)
        client = await get_user_llm_client(user, session, request.app.state.config)

        tutor_session = self._sessions.get(body.session_id)
        if not tutor_session or tutor_session.user_id != str(user.id):
            raise HTTPException(status_code=404, detail="Session not found")
        self._session_timestamps[body.session_id] = time.monotonic()

        try:
            mcq = await self._generate_mcq(client, tutor_session, body.scope or "current concept")
            return mcq
        finally:
            await client.close()

    async def check_assessment_answer(
        self,
        body: CheckAnswerRequest,
        request: Request,
        user: User = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ):
        await self._require_enabled(user, session)
        client = await get_user_llm_client(user, session, request.app.state.config)

        tutor_session = self._sessions.get(body.session_id)
        if not tutor_session or tutor_session.user_id != str(user.id):
            raise HTTPException(status_code=404, detail="Session not found")
        self._session_timestamps[body.session_id] = time.monotonic()

        try:
            prompt = (
                f"The student was given this multiple choice question:\n\n"
                f"Question: {body.question}\n"
                f"Options: {json.dumps(body.options)}\n\n"
                f"The student chose: {body.answer}\n\n"
                f"Your task:\n"
                f"1. State whether the answer is correct or not.\n"
                f"2. Explain why the answer is "
                f"{'' if body.answer else 'wrong'}.\n"
                f"3. Briefly reassess the student's competency level "
                f"(currently: {tutor_session.competency_level}). "
                f"It is okay for the competency level to stay the same. "
                f"Reduce it if the student needs more foundational help.\n"
                f"4. End your response with a single line in the format: "
                f"COMPETENCY: <new_level>\n"
                f"Valid levels: {', '.join(COMPETENCY_LEVELS)}"
            )

        response = await client.chat_completion(
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": prompt},
            ],
            temperature=0.5,
        )

            new_level = tutor_session.competency_level
            for line in response.splitlines():
                if line.strip().startswith("COMPETENCY:"):
                    candidate = line.strip().split(":", 1)[1].strip()
                    if candidate in COMPETENCY_LEVELS:
                        new_level = candidate
                        break

            old_level = tutor_session.competency_level
            tutor_session.competency_level = new_level
            if old_level != new_level:
                tutor_session.chat_history.append({
                    "role": "system",
                    "content": f"[Competency adjusted: {old_level} → {new_level}]",
                })

            return {"feedback": response, "competency_level": new_level}
        finally:
            await client.close()

    # ---- Session management ----

    async def get_session(
        self,
        user: User = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ):
        await self._require_enabled(user, session)
        for sid, ss in self._sessions.items():
            if ss.user_id == str(user.id):
                self._session_timestamps[sid] = time.monotonic()
                return {
                    "session_id": ss.session_id,
                    "problem": ss.problem,
                    "equation_json": ss.equation_json,
                    "equation_latex": ss.equation_latex,
                    "competency_level": ss.competency_level,
                    "assessment_mode": ss.assessment_mode,
                    "concepts_covered": ss.concepts_covered,
                    "current_concept": ss.current_concept,
                    "chat_history": ss.chat_history,
                }
        return {"session_id": None}

    async def delete_session(
        self,
        user: User = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ):
        await self._require_enabled(user, session)
        for sid, ss in list(self._sessions.items()):
            if ss.user_id == str(user.id):
                self._sessions.pop(sid, None)
                self._session_timestamps.pop(sid, None)
        return {"status": "deleted"}

    # ---- Helpers ----

    async def _load_user_settings(self, user_id: str, session: AsyncSession) -> dict[str, Any]:
        from workbench.core.agents import get_user_agent_settings
        user_settings = await get_user_agent_settings(user_id, session)
        agent_config = user_settings.get(self.name, {})
        return agent_config.get("settings", self.get_default_settings())

    def _build_system_prompt(self, tutor_session: TutorSession) -> str:
        level_label = COMPETENCY_LABELS.get(
            tutor_session.competency_level, tutor_session.competency_level
        )
        prompt_parts = [
            (
                f"You are a friendly, patient math tutor. "
                f"The student's current assessed level is: {level_label}."
            ),
            (
                f"Adjust your explanations to match and gradually improve this level. "
                f"Use language and analogies appropriate for a "
                f"{level_label.replace('Smart ', '').replace('Student', 'student')}."
            ),
            "",
            "GUIDELINES:",
            (
                "- Walk through the problem step by step. "
                "Never skip steps unless the student asks you to."
            ),
            (
                "- After explaining each concept, "
                "briefly check if the student has questions."
            ),
            (
                "- When the student asks about a specific term, "
                "equation component, or step, do a deep dive."
            ),
            (
                "- Use LaTeX notation (within $$) for mathematical "
                "expressions so they can be rendered."
            ),
            (
                "- Encourage the student to attempt steps on their own "
                "before revealing the answer."
            ),
            (
                "- Be encouraging but honest. "
                "If the student makes a mistake, gently correct them."
            ),
            "",
            f"The student's problem:\n{tutor_session.problem}",
        ]
        if tutor_session.equation_latex:
            prompt_parts.append(
                f"\nKey equation (LaTeX):\n{tutor_session.equation_latex}"
            )
        if tutor_session.equation_json:
            prompt_parts.append(
                f"\nEquation structure (JSON):\n"
                f"{json.dumps(tutor_session.equation_json, indent=2)}"
            )
        return "\n".join(prompt_parts)

    async def _stream_chat_response(
        self,
        client: OpenRouterClient,
        tutor_session: TutorSession,
        system_prompt: str,
        user_message: str,
    ):
        messages = [{"role": "system", "content": system_prompt}]
        for entry in tutor_session.chat_history[-20:]:
            messages.append(entry)
        if messages[-1]["role"] != "user" or messages[-1]["content"] != user_message:
            messages.append({"role": "user", "content": user_message})

        _SENTINEL = "__STREAM_DONE__"
        queue: asyncio.Queue[str] = asyncio.Queue()

        async def stream_to_queue() -> None:
            try:
                async for chunk in client.chat_completion_stream(
                    messages=messages,
                    temperature=0.7,
                ):
                    await queue.put(
                        f"event: chunk\ndata: {json.dumps({'content': chunk})}\n\n"
                    )
                await queue.put(_SENTINEL)
            except Exception as e:
                await queue.put(str(e))
                await queue.put(_SENTINEL)

        task = asyncio.create_task(stream_to_queue())

        try:
            while True:
                item = await queue.get()
                if item == _SENTINEL:
                    break
                yield item
        finally:
            if not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task

    def _detect_concept_transition(self, response: str) -> str | None:
        markers = [
            "now that we understand", "the next concept", "moving on to",
            "this brings us to", "now let's look at", "the key insight here",
            "an important principle", "this relates to",
        ]
        for marker in markers:
            idx = response.lower().find(marker)
            if idx >= 0:
                snippet = response[idx:idx + 120].strip()
                return snippet.split(".")[0] if "." in snippet else snippet
        return None

    async def _generate_mcq(
        self,
        client: OpenRouterClient,
        tutor_session: TutorSession,
        scope: str,
    ) -> dict[str, Any]:
        level_label = COMPETENCY_LABELS.get(
            tutor_session.competency_level, tutor_session.competency_level
        )
        prompt = (
            f"Generate ONE multiple-choice question to assess the student's "
            f"understanding of: {scope}\n\n"
            f"Problem context:\n{tutor_session.problem}\n\n"
            f"Student level: {level_label}\n\n"
            f"Requirements:\n"
            f"- 4 options (A, B, C, D)\n"
            f"- Exactly one correct answer\n"
            f"- Distractors should target common misconceptions\n"
            f"- Difficulty should be appropriate for the student's level\n"
            f"- Include a brief explanation of the correct answer\n\n"
            f"Respond in JSON format:\n"
            f'{{"question": "..."'
            f', "options": {{"A": "..", "B": "..", "C": "..", "D": ".."}}'
            f', "correct": "A", "explanation": "..."}}'
        )

        response = await client.chat_completion(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a math assessment generator. "
                        "Respond ONLY with valid JSON."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.5,
        )

        try:
            json_start = response.index("{")
            json_end = response.rindex("}") + 1
            mcq = json.loads(response[json_start:json_end])
            tutor_session.chat_history.append({
                "role": "system",
                "content": f"[MCQ generated for: {scope}]",
            })
            return mcq
        except (ValueError, json.JSONDecodeError):
            return {"error": "Failed to parse assessment", "raw": response}

    # ---- Cleanup ----

    @classmethod
    def _cleanup_sessions(cls) -> None:
        now = time.monotonic()
        to_remove = [
            sid for sid, ts in list(cls._session_timestamps.items())
            if now - ts > SESSION_TTL_SECONDS
        ]
        for sid in to_remove:
            cls._sessions.pop(sid, None)
            cls._session_timestamps.pop(sid, None)
            logger.info("Cleaned up expired math-tutor session: %s", sid)


# ---- Request/Response Models ----

class StartSessionRequest(BaseModel):
    problem: str = Field(..., max_length=20000)
    equation_json: dict[str, Any] | None = None
    equation_latex: str | None = None


class ChatRequest(BaseModel):
    session_id: str
    message: str = Field(..., max_length=10000)


class DeepDiveRequest(BaseModel):
    session_id: str
    topic: str = Field(..., max_length=2000)
    context: str = ""


class AssessmentRequest(BaseModel):
    session_id: str
    scope: str | None = None


class CheckAnswerRequest(BaseModel):
    session_id: str
    question: str
    options: dict[str, str]
    answer: str


class EquationUpdateRequest(BaseModel):
    session_id: str
    equation_json: dict[str, Any] | None = None
    equation_latex: str | None = None
    context: str = ""
