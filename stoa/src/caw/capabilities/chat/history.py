"""Conversation history construction helpers for chat capability."""

from __future__ import annotations

from typing import TYPE_CHECKING

from caw.protocols.types import ProviderMessage

if TYPE_CHECKING:
    from caw.storage.repository import MessageRepository


class ConversationHistory:
    """Manages conversation history for context building."""

    def __init__(self, message_repo: MessageRepository) -> None:
        self._message_repo = message_repo

    async def build_context(
        self, session_id: str, max_messages: int | None = None
    ) -> list[ProviderMessage]:
        """Build provider message list from stored session history.

        Args:
            session_id: Session identifier whose history should be loaded.
            max_messages: Optional limit for the number of most-recent messages.

        Returns:
            Provider messages in chronological order, suitable for provider calls.
        """
        if max_messages is None:
            history = await self._message_repo.list_by_session(session_id)
        else:
            history = await self._message_repo.get_last_n(session_id, max_messages)

        return [
            ProviderMessage(role=message.role.value, content=message.content) for message in history
        ]
