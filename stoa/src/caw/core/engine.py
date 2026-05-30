"""Core orchestration engine implementation for chat execution."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from caw.errors import ProviderError, ValidationError_
from caw.models import Artifact, Message, MessageRole, PermissionLevel, SessionMode, SessionState
from caw.protocols.types import ProviderMessage, ProviderResponse, ToolDefinition

if TYPE_CHECKING:
    from caw.core.config import CAWConfig
    from caw.core.permissions import PermissionGate
    from caw.core.router import Router
    from caw.core.session import SessionManager
    from caw.protocols.registry import ProviderRegistry
    from caw.skills.registry import SkillRegistry
    from caw.storage.repository import MessageRepository
    from caw.traces.collector import TraceCollector

from caw.traces.schemas import (
    provider_error,
    provider_request,
    provider_response,
    routing_decision,
    skill_resolved,
)


@dataclass
class ExecutionRequest:
    session_id: str
    content: str
    mode: SessionMode = SessionMode.CHAT
    provider: str | None = None
    model: str | None = None
    tools: list[ToolDefinition] | None = None
    attachments: list[object] | None = None


@dataclass
class ExecutionResult:
    session_id: str
    message_id: str
    content: str
    model: str
    provider: str
    tokens_in: int
    tokens_out: int
    latency_ms: int
    trace_id: str
    artifacts: list[Artifact] = field(default_factory=list)


class Engine:
    """Central orchestration engine for single-request chat execution."""

    def __init__(
        self,
        config: CAWConfig,
        session_manager: SessionManager,
        router: Router,
        permission_gate: PermissionGate,
        skill_registry: SkillRegistry,
        trace_collector: TraceCollector,
        provider_registry: ProviderRegistry,
        message_repo: MessageRepository,
    ) -> None:
        self._config = config
        self._session_manager = session_manager
        self._router = router
        self._permission_gate = permission_gate
        self._skill_registry = skill_registry
        self._trace_collector = trace_collector
        self._provider_registry = provider_registry
        self._message_repo = message_repo

    async def execute(self, request: ExecutionRequest) -> ExecutionResult:
        """Execute a chat request through session, skills, routing, and provider layers."""
        if request.mode is not SessionMode.CHAT:
            raise ValidationError_(
                message="Only chat mode is currently implemented",
                code="mode_not_implemented",
                details={"mode": request.mode.value},
            )

        trace_id = str(uuid.uuid4())
        session = await self._session_manager.get(request.session_id)

        if session.state is SessionState.CREATED:
            session = await self._session_manager.transition(session.id, SessionState.ACTIVE)

        approval = await self._permission_gate.check(
            level=PermissionLevel.SUGGEST,
            action="chat completion",
            resources=[f"session:{session.id}"],
            trace_id=trace_id,
            session_id=session.id,
        )
        if approval is not None:
            raise ValidationError_(
                message="Chat execution unexpectedly requires approval",
                code="chat_approval_required",
                details={"approval_id": approval.id},
            )

        resolver = self._skill_registry.create_resolver()
        resolved = resolver.resolve(
            explicit_ids=list(session.active_skills),
            mode_default_ids=self._skill_registry.get_mode_defaults(session.mode),
        )

        await self._trace_collector.emit(
            skill_resolved(
                trace_id=trace_id,
                session_id=session.id,
                resolved_skill_ids=[skill.skill_id for skill in resolved.skills],
                precedence_chain=list(resolved.conflicts_resolved),
            )
        )

        preferred_provider = next(
            (skill.provider_preference for skill in resolved.skills if skill.provider_preference),
            None,
        )
        selection = await self._router.route(
            explicit_provider=request.provider,
            explicit_model=request.model,
            skill_preference=preferred_provider,
        )

        await self._trace_collector.emit(
            routing_decision(
                trace_id=trace_id,
                session_id=session.id,
                strategy=self._config.routing.strategy,
                candidates=self._provider_registry.list_providers(),
                selected=selection.provider_key,
                rationale=selection.rationale,
            )
        )

        history = await self._message_repo.list_by_session(session.id)
        provider_messages: list[ProviderMessage] = []
        if resolved.composed_context:
            provider_messages.append(
                ProviderMessage(role="system", content=resolved.composed_context)
            )

        for message in history:
            provider_messages.append(
                ProviderMessage(role=message.role.value, content=message.content)
            )
        provider_messages.append(
            ProviderMessage(role=MessageRole.USER.value, content=request.content)
        )

        await self._trace_collector.emit(
            provider_request(
                trace_id=trace_id,
                session_id=session.id,
                provider=selection.provider_key,
                model=selection.model,
                message_count=len(provider_messages),
                token_estimate=0,
            )
        )

        provider = self._provider_registry.get(selection.provider_key)
        try:
            completion = await provider.complete(
                messages=provider_messages,
                model=selection.model,
                tools=request.tools,
                max_tokens=self._config.providers[selection.provider_key].max_tokens,
                stream=False,
            )
        except ProviderError as exc:
            await self._trace_collector.emit(
                provider_error(
                    trace_id=trace_id,
                    session_id=session.id,
                    provider=selection.provider_key,
                    model=selection.model,
                    error_type=exc.code,
                    message=exc.message,
                )
            )
            raise

        if not isinstance(completion, ProviderResponse):
            raise ProviderError(
                message="Streaming responses are not supported in Engine.execute",
                code="provider_streaming_unexpected",
            )

        if not isinstance(completion.content, str):
            assistant_text = "\n".join(
                part.text or "" for part in completion.content if getattr(part, "text", None)
            ).strip()
        else:
            assistant_text = completion.content

        next_seq = await self._message_repo.count_by_session(session.id)
        user_message = await self._message_repo.create(
            Message(
                session_id=session.id,
                sequence_num=next_seq + 1,
                role=MessageRole.USER,
                content=request.content,
            )
        )
        assistant_message = await self._message_repo.create(
            Message(
                session_id=session.id,
                sequence_num=next_seq + 2,
                role=MessageRole.ASSISTANT,
                content=assistant_text,
                model=completion.model,
                provider=selection.provider_key,
                token_count_in=completion.input_tokens,
                token_count_out=completion.output_tokens,
            )
        )

        await self._trace_collector.emit(
            provider_response(
                trace_id=trace_id,
                session_id=session.id,
                provider=selection.provider_key,
                model=completion.model,
                tokens_in=completion.input_tokens,
                tokens_out=completion.output_tokens,
                latency_ms=completion.latency_ms,
            )
        )

        # Keep a reference to the user message ID in case downstream workflows
        # need to correlate request/response pairs for analytics.
        _ = user_message.id

        return ExecutionResult(
            session_id=session.id,
            message_id=assistant_message.id,
            content=assistant_text,
            model=completion.model,
            provider=selection.provider_key,
            tokens_in=completion.input_tokens,
            tokens_out=completion.output_tokens,
            latency_ms=completion.latency_ms,
            trace_id=trace_id,
        )
