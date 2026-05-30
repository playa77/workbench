"""Replay and analysis tools for trace events."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from datetime import datetime

    from caw.models import TraceEvent
    from caw.traces.collector import TraceCollector


@dataclass
class RunSummary:
    trace_id: str
    session_id: str
    mode: str
    started_at: datetime
    completed_at: datetime | None
    duration_ms: int | None
    event_count: int
    provider_calls: int
    tool_calls: int
    errors: int
    key_events: list[TraceEvent]


@dataclass
class RunDiff:
    trace_id_a: str
    trace_id_b: str
    events_only_in_a: list[TraceEvent]
    events_only_in_b: list[TraceEvent]
    common_event_types: list[str]
    timing_comparison: dict[str, tuple[int, int]]


class ReplayEngine:
    """Reconstructs and compares traced runs."""

    _KEY_EVENT_TYPES: ClassVar[set[str]] = {
        "session:created",
        "routing:decision",
        "provider:request",
        "provider:response",
        "provider:error",
        "tool:invocation",
        "tool:result",
        "gate:approval_required",
        "gate:approved",
        "gate:denied",
        "error:unhandled",
    }

    def __init__(self, collector: TraceCollector) -> None:
        self._collector = collector

    async def timeline(
        self,
        trace_id: str,
        event_types: list[str] | None = None,
    ) -> list[TraceEvent]:
        """Return a chronological event list for a trace ID."""
        events = await self._collector.get_trace(trace_id)
        if event_types is not None:
            allowed = set(event_types)
            events = [event for event in events if event.event_type in allowed]
        return sorted(events, key=lambda event: event.timestamp)

    async def summary(self, trace_id: str) -> RunSummary:
        """Build a high-level summary for one run trace."""
        events = await self.timeline(trace_id)
        if not events:
            raise ValueError(f"Trace '{trace_id}' has no events and cannot be summarized")

        started_at = events[0].timestamp
        completed_at = events[-1].timestamp
        duration_ms = int((completed_at - started_at).total_seconds() * 1000)
        session_created_event = next(
            (event for event in events if event.event_type == "session:created"),
            None,
        )
        mode = "unknown"
        if session_created_event is not None:
            mode_value = session_created_event.data.get("mode")
            if isinstance(mode_value, str):
                mode = mode_value

        return RunSummary(
            trace_id=trace_id,
            session_id=events[0].session_id,
            mode=mode,
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=duration_ms,
            event_count=len(events),
            provider_calls=sum(1 for event in events if event.event_type == "provider:request"),
            tool_calls=sum(1 for event in events if event.event_type == "tool:invocation"),
            errors=sum(
                1 for event in events if event.event_type in {"provider:error", "error:unhandled"}
            ),
            key_events=[event for event in events if event.event_type in self._KEY_EVENT_TYPES],
        )

    async def diff(self, trace_id_a: str, trace_id_b: str) -> RunDiff:
        """Compare two traces and return unique/common events and timing data."""
        events_a = await self.timeline(trace_id_a)
        events_b = await self.timeline(trace_id_b)

        counter_a = Counter(self._event_fingerprint(event) for event in events_a)
        counter_b = Counter(self._event_fingerprint(event) for event in events_b)

        only_in_a = self._subtract_events(events_a, counter_b)
        only_in_b = self._subtract_events(events_b, counter_a)

        common_event_types = sorted(
            {event.event_type for event in events_a}.intersection(
                event.event_type for event in events_b
            )
        )

        timing_comparison: dict[str, tuple[int, int]] = {}
        for event_type in common_event_types:
            ms_a = self._duration_for_type(events_a, event_type)
            ms_b = self._duration_for_type(events_b, event_type)
            timing_comparison[event_type] = (ms_a, ms_b)

        return RunDiff(
            trace_id_a=trace_id_a,
            trace_id_b=trace_id_b,
            events_only_in_a=only_in_a,
            events_only_in_b=only_in_b,
            common_event_types=common_event_types,
            timing_comparison=timing_comparison,
        )

    def _event_fingerprint(self, event: TraceEvent) -> str:
        payload = {
            "event_type": event.event_type,
            "data": event.data,
            "parent_event_id": event.parent_event_id,
        }
        return json.dumps(payload, sort_keys=True, default=str)

    def _subtract_events(
        self, source: list[TraceEvent], other_counts: Counter[str]
    ) -> list[TraceEvent]:
        remaining = other_counts.copy()
        unique: list[TraceEvent] = []
        for event in source:
            fingerprint = self._event_fingerprint(event)
            if remaining[fingerprint] > 0:
                remaining[fingerprint] -= 1
            else:
                unique.append(event)
        return unique

    def _duration_for_type(self, events: list[TraceEvent], event_type: str) -> int:
        filtered = [event for event in events if event.event_type == event_type]
        if len(filtered) < 2:
            return 0
        return int((filtered[-1].timestamp - filtered[0].timestamp).total_seconds() * 1000)
