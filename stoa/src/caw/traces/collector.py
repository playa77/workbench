"""Trace event collection and batched persistence.

The trace collector decouples event emission from storage writes by buffering
trace events in memory. This keeps producers lightweight while still ensuring
that events are persisted regularly and on shutdown.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime

    from caw.models import TraceEvent
    from caw.storage.repository import TraceEventRepository

logger = logging.getLogger(__name__)


class TraceCollector:
    """Collects and persists trace events.

    Thread-safe and async-safe. Events are buffered and flushed every
    ``flush_interval`` seconds or every ``flush_threshold`` events,
    whichever happens first.

    The collector must be started to run the periodic flush loop and stopped
    to ensure any remaining buffered events are persisted.
    """

    def __init__(
        self,
        repository: TraceEventRepository,
        flush_threshold: int = 100,
        flush_interval: float = 5.0,
    ) -> None:
        self._repository = repository
        self._flush_threshold = flush_threshold
        self._flush_interval = flush_interval
        self._buffer: list[TraceEvent] = []
        self._buffer_lock = asyncio.Lock()
        self._flush_lock = asyncio.Lock()
        self._stop_event = asyncio.Event()
        self._flush_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Start the periodic flush background task."""
        if self._flush_task is not None and not self._flush_task.done():
            return
        self._stop_event.clear()
        self._flush_task = asyncio.create_task(self._run_periodic_flush())

    async def stop(self) -> None:
        """Flush remaining events and stop the background task."""
        self._stop_event.set()
        if self._flush_task is not None:
            await self._flush_task
            self._flush_task = None
        await self.flush()

    async def emit(self, event: TraceEvent) -> None:
        """Buffer a trace event for persistence.

        If the buffer reaches ``flush_threshold``, this method triggers an
        immediate flush so the buffer does not grow unbounded.
        """
        should_flush = False
        async with self._buffer_lock:
            self._buffer.append(event)
            should_flush = len(self._buffer) >= self._flush_threshold
        if should_flush:
            await self.flush()

    async def flush(self) -> None:
        """Write all buffered events to the database."""
        async with self._flush_lock:
            async with self._buffer_lock:
                if not self._buffer:
                    return
                events = self._buffer[:]
                self._buffer.clear()

            await self._repository.create_batch(events)

    async def get_trace(self, trace_id: str) -> list[TraceEvent]:
        """Retrieve all events for a trace ID, ordered by timestamp."""
        return await self._repository.get_by_trace_id(trace_id)

    async def get_session_events(
        self,
        session_id: str,
        event_types: list[str] | None = None,
        since: datetime | None = None,
    ) -> list[TraceEvent]:
        """Retrieve events for a session with optional filtering."""
        return await self._repository.get_by_session(
            session_id, event_types=event_types, since=since
        )

    async def _run_periodic_flush(self) -> None:
        """Run periodic flushes until shutdown is requested."""
        while True:
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self._flush_interval)
                return
            except TimeoutError:
                try:
                    await self.flush()
                except Exception:
                    logger.exception("Periodic trace flush failed")
