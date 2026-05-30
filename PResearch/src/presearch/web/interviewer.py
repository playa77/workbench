"""Interviewer — refines research questions through a structured interview process."""

from __future__ import annotations

from presearch.providers.base import ChatSession, ProviderInterface
from presearch.prompts import INTERVIEW_TEMPLATE


_READY_MARKERS = [
    "ready to proceed",
    "readiness assessment",
    "would you like me to proceed",
]


def is_ready(text: str) -> bool:
    """Check if the LLM indicates readiness to proceed to delivery."""
    lower = text.lower()
    return any(marker in lower for marker in _READY_MARKERS)


def extract_refined_query(text: str) -> str:
    """Extract the refined query from the delivery phase response."""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("refined query:"):
            return stripped[len("refined query:"):].strip()
        if stripped.lower().startswith("**refined query"):
            cleaned = stripped.replace("**", "").strip()
            idx = cleaned.find(":")
            if idx != -1:
                return cleaned[idx + 1:].strip()
    # Fallback: first non-empty, non-heading line
    lines = [l.strip() for l in text.splitlines() if l.strip() and not l.strip().startswith("#")]
    return lines[0] if lines else ""


async def create_interview_chat(provider: ProviderInterface, initial_idea: str) -> ChatSession:
    """Create a chat session configured with the interview prompt."""
    prompt = INTERVIEW_TEMPLATE.replace("{{input}}", initial_idea)
    return await provider.create_chat(
        system_instruction=prompt,
        tools=None,
    )


async def start_interview(chat: ChatSession, initial_idea: str) -> str:
    """Send the initial research idea to start the interview."""
    response = await chat.send(
        f"I want to research the following topic. Please interview me to refine "
        f"this into a precise research question:\n\n{initial_idea}"
    )
    return response.text or ""


async def send_answer(chat: ChatSession, answer: str) -> str:
    """Send the user's answer to the LLM's interview questions."""
    response = await chat.send(answer)
    return response.text or ""


async def finalize(chat: ChatSession) -> str:
    """Ask the LLM to proceed to the delivery phase."""
    response = await chat.send("Yes, please proceed to the delivery phase.")
    return response.text or ""
