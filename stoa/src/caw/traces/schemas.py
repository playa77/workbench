"""Trace event factory functions.

Each helper creates a :class:`caw.models.TraceEvent` with the correct
``event_type`` and payload structure. Callers should prefer these helpers over
manual event construction to keep event schemas consistent across the system.
"""

from __future__ import annotations

from caw.models import TraceEvent


def _event(
    trace_id: str,
    session_id: str,
    event_type: str,
    data: dict[str, object],
    parent_event_id: str | None = None,
) -> TraceEvent:
    return TraceEvent(
        trace_id=trace_id,
        session_id=session_id,
        event_type=event_type,
        data=data,
        parent_event_id=parent_event_id,
    )


def session_created(trace_id: str, session_id: str, mode: str, skills: list[str]) -> TraceEvent:
    return _event(trace_id, session_id, "session:created", {"mode": mode, "skills": skills})


def session_state_changed(
    trace_id: str,
    session_id: str,
    old_state: str,
    new_state: str,
) -> TraceEvent:
    return _event(
        trace_id,
        session_id,
        "session:state_changed",
        {"old_state": old_state, "new_state": new_state},
    )


def session_branched(
    trace_id: str,
    session_id: str,
    parent_id: str,
    branch_point: int,
) -> TraceEvent:
    return _event(
        trace_id,
        session_id,
        "session:branched",
        {"parent_id": parent_id, "branch_point": branch_point},
    )


def skill_resolved(
    trace_id: str,
    session_id: str,
    resolved_skill_ids: list[str],
    precedence_chain: list[str],
) -> TraceEvent:
    return _event(
        trace_id,
        session_id,
        "skill:resolved",
        {"resolved_skill_ids": resolved_skill_ids, "precedence_chain": precedence_chain},
    )


def skill_conflict(
    trace_id: str,
    session_id: str,
    conflicting_skill_ids: list[str],
    resolution: str,
) -> TraceEvent:
    return _event(
        trace_id,
        session_id,
        "skill:conflict",
        {"conflicting_skill_ids": conflicting_skill_ids, "resolution": resolution},
    )


def routing_decision(
    trace_id: str,
    session_id: str,
    strategy: str,
    candidates: list[str],
    selected: str,
    rationale: str,
) -> TraceEvent:
    return _event(
        trace_id,
        session_id,
        "routing:decision",
        {
            "strategy": strategy,
            "candidates": candidates,
            "selected": selected,
            "rationale": rationale,
        },
    )


def provider_request(
    trace_id: str,
    session_id: str,
    provider: str,
    model: str,
    message_count: int,
    token_estimate: int,
) -> TraceEvent:
    return _event(
        trace_id,
        session_id,
        "provider:request",
        {
            "provider": provider,
            "model": model,
            "message_count": message_count,
            "token_estimate": token_estimate,
        },
    )


def provider_response(
    trace_id: str,
    session_id: str,
    provider: str,
    model: str,
    tokens_in: int,
    tokens_out: int,
    latency_ms: int,
) -> TraceEvent:
    return _event(
        trace_id,
        session_id,
        "provider:response",
        {
            "provider": provider,
            "model": model,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "latency_ms": latency_ms,
        },
    )


def provider_error(
    trace_id: str,
    session_id: str,
    provider: str,
    model: str,
    error_type: str,
    message: str,
) -> TraceEvent:
    return _event(
        trace_id,
        session_id,
        "provider:error",
        {
            "provider": provider,
            "model": model,
            "error_type": error_type,
            "message": message,
        },
    )


def provider_fallback(
    trace_id: str,
    session_id: str,
    from_provider: str,
    to_provider: str,
    reason: str,
) -> TraceEvent:
    return _event(
        trace_id,
        session_id,
        "provider:fallback",
        {"from_provider": from_provider, "to_provider": to_provider, "reason": reason},
    )


def tool_invocation(
    trace_id: str,
    session_id: str,
    tool_name: str,
    arguments: dict[str, object],
    server_id: str,
) -> TraceEvent:
    return _event(
        trace_id,
        session_id,
        "tool:invocation",
        {"tool_name": tool_name, "arguments": arguments, "server_id": server_id},
    )


def tool_result(
    trace_id: str,
    session_id: str,
    tool_name: str,
    success: bool,
    duration_ms: int,
) -> TraceEvent:
    return _event(
        trace_id,
        session_id,
        "tool:result",
        {"tool_name": tool_name, "success": success, "duration_ms": duration_ms},
    )


def retrieval_query(
    trace_id: str,
    session_id: str,
    query: str,
    strategy: str,
    top_k: int,
) -> TraceEvent:
    return _event(
        trace_id,
        session_id,
        "retrieval:query",
        {"query": query, "strategy": strategy, "top_k": top_k},
    )


def retrieval_results(
    trace_id: str,
    session_id: str,
    result_count: int,
    scores: list[float],
    source_ids: list[str],
) -> TraceEvent:
    return _event(
        trace_id,
        session_id,
        "retrieval:results",
        {"result_count": result_count, "scores": scores, "source_ids": source_ids},
    )


def synthesis_started(
    trace_id: str,
    session_id: str,
    query: str,
    source_count: int,
    format: str,
) -> TraceEvent:
    return _event(
        trace_id,
        session_id,
        "synthesis:started",
        {"query": query, "source_count": source_count, "format": format},
    )


def synthesis_completed(
    trace_id: str,
    session_id: str,
    claim_count: int,
    citation_count: int,
    uncertainty_count: int,
) -> TraceEvent:
    return _event(
        trace_id,
        session_id,
        "synthesis:completed",
        {
            "claim_count": claim_count,
            "citation_count": citation_count,
            "uncertainty_count": uncertainty_count,
        },
    )


def deliberation_started(
    trace_id: str,
    session_id: str,
    question: str,
    frame_count: int,
    rounds: int,
) -> TraceEvent:
    return _event(
        trace_id,
        session_id,
        "deliberation:started",
        {"question": question, "frame_count": frame_count, "rounds": rounds},
    )


def deliberation_frame_output(
    trace_id: str,
    session_id: str,
    frame_id: str,
    position_summary: str,
) -> TraceEvent:
    return _event(
        trace_id,
        session_id,
        "deliberation:frame_output",
        {"frame_id": frame_id, "position_summary": position_summary},
    )


def deliberation_critique(
    trace_id: str,
    session_id: str,
    from_frame: str,
    to_frame: str,
    critique_summary: str,
) -> TraceEvent:
    return _event(
        trace_id,
        session_id,
        "deliberation:critique",
        {"from_frame": from_frame, "to_frame": to_frame, "critique_summary": critique_summary},
    )


def deliberation_completed(
    trace_id: str,
    session_id: str,
    agreement_count: int,
    disagreement_count: int,
) -> TraceEvent:
    return _event(
        trace_id,
        session_id,
        "deliberation:completed",
        {"agreement_count": agreement_count, "disagreement_count": disagreement_count},
    )


def workspace_read(trace_id: str, session_id: str, path: str, size: int) -> TraceEvent:
    return _event(trace_id, session_id, "workspace:read", {"path": path, "size": size})


def workspace_write(
    trace_id: str,
    session_id: str,
    path: str,
    size: int,
    hash: str,
) -> TraceEvent:
    return _event(
        trace_id, session_id, "workspace:write", {"path": path, "size": size, "hash": hash}
    )


def workspace_execute(
    trace_id: str,
    session_id: str,
    command: str,
    exit_code: int,
    duration_ms: int,
) -> TraceEvent:
    return _event(
        trace_id,
        session_id,
        "workspace:execute",
        {"command": command, "exit_code": exit_code, "duration_ms": duration_ms},
    )


def workspace_delete(trace_id: str, session_id: str, path: str) -> TraceEvent:
    return _event(trace_id, session_id, "workspace:delete", {"path": path})


def gate_approval_required(
    trace_id: str,
    session_id: str,
    action: str,
    permission_level: str,
    resources: list[str],
) -> TraceEvent:
    return _event(
        trace_id,
        session_id,
        "gate:approval_required",
        {"action": action, "permission_level": permission_level, "resources": resources},
    )


def gate_approved(
    trace_id: str,
    session_id: str,
    request_id: str,
    modifier: str | None = None,
) -> TraceEvent:
    data: dict[str, object] = {"request_id": request_id, "modifier": modifier}
    return _event(trace_id, session_id, "gate:approved", data)


def gate_denied(trace_id: str, session_id: str, request_id: str) -> TraceEvent:
    return _event(trace_id, session_id, "gate:denied", {"request_id": request_id})


def checkpoint_saved(
    trace_id: str,
    session_id: str,
    checkpoint_id: str,
    message_index: int,
) -> TraceEvent:
    return _event(
        trace_id,
        session_id,
        "checkpoint:saved",
        {"checkpoint_id": checkpoint_id, "message_index": message_index},
    )


def checkpoint_restored(trace_id: str, session_id: str, checkpoint_id: str) -> TraceEvent:
    return _event(
        trace_id,
        session_id,
        "checkpoint:restored",
        {"checkpoint_id": checkpoint_id},
    )


def eval_run_started(
    trace_id: str,
    session_id: str,
    task_id: str,
    provider: str,
    model: str,
    skill_pack: str,
) -> TraceEvent:
    return _event(
        trace_id,
        session_id,
        "eval:run_started",
        {"task_id": task_id, "provider": provider, "model": model, "skill_pack": skill_pack},
    )


def eval_run_completed(
    trace_id: str,
    session_id: str,
    scores: dict[str, float],
    duration_ms: int,
) -> TraceEvent:
    return _event(
        trace_id,
        session_id,
        "eval:run_completed",
        {"scores": scores, "duration_ms": duration_ms},
    )


def error_unhandled(
    trace_id: str,
    session_id: str,
    exception_type: str,
    message: str,
    traceback: str,
) -> TraceEvent:
    return _event(
        trace_id,
        session_id,
        "error:unhandled",
        {"exception_type": exception_type, "message": message, "traceback": traceback},
    )
