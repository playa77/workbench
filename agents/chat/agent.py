"""Chat Agent — LLM chat with the workbench infrastructure."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from agents.base import AgentBase
from workbench.core.auth import get_current_user, get_user_openrouter_key
from workbench.core.db import get_session
from workbench.core.models import User
from workbench.core.router import OpenRouterClient


class ChatAgent(AgentBase):
    name = "chat"
    display_name = "Chat"
    description = "LLM chat with your OpenRouter API key"
    version = "0.1.0"
    icon = "message-circle"

    def _build_router(self) -> APIRouter:
        router = APIRouter()
        router.add_api_route("/send", self.chat_send, methods=["POST"])
        return router

    async def chat_send(
        self,
        body: "ChatRequest",
        user: User = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ):
        or_key = await get_user_openrouter_key(user, session)
        if not or_key:
            raise HTTPException(status_code=400, detail="Set your OpenRouter key in Settings")
        client = OpenRouterClient(api_key=or_key)
        try:
            response = await client.chat_completion(
                messages=[{"role": "user", "content": body.message}],
                model=body.model or "deepseek/deepseek-v4-pro",
                temperature=body.temperature,
                max_tokens=body.max_tokens or 4096,
            )
            return {"response": response}
        finally:
            await client.close()

    def get_frontend_tab(self) -> dict:
        return {
            "id": self.name,
            "displayName": self.display_name,
            "icon": self.icon,
            "component": f"agent-{self.name}",
            "js": f"/static/js/components/{self.name}-tab.js",
        }


class ChatRequest(BaseModel):
    message: str
    model: str | None = None
    temperature: float = 0.7
    max_tokens: int | None = None
