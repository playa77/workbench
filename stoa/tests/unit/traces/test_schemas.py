from __future__ import annotations

from collections.abc import Callable

from caw.models import TraceEvent
from caw.traces import schemas

FactoryCase = tuple[Callable[[], TraceEvent], str, dict[str, object]]


TRACE_ID = "trace-1"
SESSION_ID = "session-1"


def _cases() -> list[FactoryCase]:
    return [
        (
            lambda: schemas.session_created(TRACE_ID, SESSION_ID, "chat", ["a.skill"]),
            "session:created",
            {"mode": "chat", "skills": ["a.skill"]},
        ),
        (
            lambda: schemas.session_state_changed(TRACE_ID, SESSION_ID, "created", "active"),
            "session:state_changed",
            {"old_state": "created", "new_state": "active"},
        ),
        (
            lambda: schemas.session_branched(TRACE_ID, SESSION_ID, "s0", 7),
            "session:branched",
            {"parent_id": "s0", "branch_point": 7},
        ),
        (
            lambda: schemas.skill_resolved(TRACE_ID, SESSION_ID, ["a", "b"], ["explicit", "pack"]),
            "skill:resolved",
            {"resolved_skill_ids": ["a", "b"], "precedence_chain": ["explicit", "pack"]},
        ),
        (
            lambda: schemas.skill_conflict(TRACE_ID, SESSION_ID, ["a", "b"], "kept a"),
            "skill:conflict",
            {"conflicting_skill_ids": ["a", "b"], "resolution": "kept a"},
        ),
        (
            lambda: schemas.routing_decision(
                TRACE_ID, SESSION_ID, "latency", ["p1", "p2"], "p1", "fast"
            ),
            "routing:decision",
            {
                "strategy": "latency",
                "candidates": ["p1", "p2"],
                "selected": "p1",
                "rationale": "fast",
            },
        ),
        (
            lambda: schemas.provider_request(TRACE_ID, SESSION_ID, "openai", "gpt", 2, 100),
            "provider:request",
            {"provider": "openai", "model": "gpt", "message_count": 2, "token_estimate": 100},
        ),
        (
            lambda: schemas.provider_response(TRACE_ID, SESSION_ID, "openai", "gpt", 20, 30, 250),
            "provider:response",
            {
                "provider": "openai",
                "model": "gpt",
                "tokens_in": 20,
                "tokens_out": 30,
                "latency_ms": 250,
            },
        ),
        (
            lambda: schemas.provider_error(
                TRACE_ID, SESSION_ID, "openai", "gpt", "timeout", "oops"
            ),
            "provider:error",
            {"provider": "openai", "model": "gpt", "error_type": "timeout", "message": "oops"},
        ),
        (
            lambda: schemas.provider_fallback(TRACE_ID, SESSION_ID, "a", "b", "quota"),
            "provider:fallback",
            {"from_provider": "a", "to_provider": "b", "reason": "quota"},
        ),
        (
            lambda: schemas.tool_invocation(TRACE_ID, SESSION_ID, "search", {"q": "x"}, "srv"),
            "tool:invocation",
            {"tool_name": "search", "arguments": {"q": "x"}, "server_id": "srv"},
        ),
        (
            lambda: schemas.tool_result(TRACE_ID, SESSION_ID, "search", True, 88),
            "tool:result",
            {"tool_name": "search", "success": True, "duration_ms": 88},
        ),
        (
            lambda: schemas.retrieval_query(TRACE_ID, SESSION_ID, "what", "hybrid", 5),
            "retrieval:query",
            {"query": "what", "strategy": "hybrid", "top_k": 5},
        ),
        (
            lambda: schemas.retrieval_results(TRACE_ID, SESSION_ID, 2, [0.9, 0.8], ["s1", "s2"]),
            "retrieval:results",
            {"result_count": 2, "scores": [0.9, 0.8], "source_ids": ["s1", "s2"]},
        ),
        (
            lambda: schemas.synthesis_started(TRACE_ID, SESSION_ID, "what", 3, "report"),
            "synthesis:started",
            {"query": "what", "source_count": 3, "format": "report"},
        ),
        (
            lambda: schemas.synthesis_completed(TRACE_ID, SESSION_ID, 4, 5, 1),
            "synthesis:completed",
            {"claim_count": 4, "citation_count": 5, "uncertainty_count": 1},
        ),
        (
            lambda: schemas.deliberation_started(TRACE_ID, SESSION_ID, "q", 2, 3),
            "deliberation:started",
            {"question": "q", "frame_count": 2, "rounds": 3},
        ),
        (
            lambda: schemas.deliberation_frame_output(TRACE_ID, SESSION_ID, "f1", "summary"),
            "deliberation:frame_output",
            {"frame_id": "f1", "position_summary": "summary"},
        ),
        (
            lambda: schemas.deliberation_critique(TRACE_ID, SESSION_ID, "f1", "f2", "crit"),
            "deliberation:critique",
            {"from_frame": "f1", "to_frame": "f2", "critique_summary": "crit"},
        ),
        (
            lambda: schemas.deliberation_completed(TRACE_ID, SESSION_ID, 1, 2),
            "deliberation:completed",
            {"agreement_count": 1, "disagreement_count": 2},
        ),
        (
            lambda: schemas.workspace_read(TRACE_ID, SESSION_ID, "/tmp/a", 100),
            "workspace:read",
            {"path": "/tmp/a", "size": 100},
        ),
        (
            lambda: schemas.workspace_write(TRACE_ID, SESSION_ID, "/tmp/a", 200, "abc"),
            "workspace:write",
            {"path": "/tmp/a", "size": 200, "hash": "abc"},
        ),
        (
            lambda: schemas.workspace_execute(TRACE_ID, SESSION_ID, "echo hi", 0, 12),
            "workspace:execute",
            {"command": "echo hi", "exit_code": 0, "duration_ms": 12},
        ),
        (
            lambda: schemas.workspace_delete(TRACE_ID, SESSION_ID, "/tmp/a"),
            "workspace:delete",
            {"path": "/tmp/a"},
        ),
        (
            lambda: schemas.gate_approval_required(
                TRACE_ID, SESSION_ID, "write", "write", ["/tmp/a"]
            ),
            "gate:approval_required",
            {"action": "write", "permission_level": "write", "resources": ["/tmp/a"]},
        ),
        (
            lambda: schemas.gate_approved(TRACE_ID, SESSION_ID, "req-1", "safe-mode"),
            "gate:approved",
            {"request_id": "req-1", "modifier": "safe-mode"},
        ),
        (
            lambda: schemas.gate_denied(TRACE_ID, SESSION_ID, "req-1"),
            "gate:denied",
            {"request_id": "req-1"},
        ),
        (
            lambda: schemas.checkpoint_saved(TRACE_ID, SESSION_ID, "cp-1", 42),
            "checkpoint:saved",
            {"checkpoint_id": "cp-1", "message_index": 42},
        ),
        (
            lambda: schemas.checkpoint_restored(TRACE_ID, SESSION_ID, "cp-1"),
            "checkpoint:restored",
            {"checkpoint_id": "cp-1"},
        ),
        (
            lambda: schemas.eval_run_started(
                TRACE_ID, SESSION_ID, "task", "openai", "gpt", "default"
            ),
            "eval:run_started",
            {"task_id": "task", "provider": "openai", "model": "gpt", "skill_pack": "default"},
        ),
        (
            lambda: schemas.eval_run_completed(TRACE_ID, SESSION_ID, {"f1": 0.9}, 999),
            "eval:run_completed",
            {"scores": {"f1": 0.9}, "duration_ms": 999},
        ),
        (
            lambda: schemas.error_unhandled(TRACE_ID, SESSION_ID, "ValueError", "bad", "tb"),
            "error:unhandled",
            {"exception_type": "ValueError", "message": "bad", "traceback": "tb"},
        ),
    ]


def test_factory_functions_cover_event_types() -> None:
    for factory, expected_type, expected_data in _cases():
        event = factory()
        assert event.trace_id == TRACE_ID
        assert event.session_id == SESSION_ID
        assert event.event_type == expected_type
        assert event.data == expected_data
        assert event.timestamp is not None
