"""WebSocket endpoint for real-time research streaming."""

from __future__ import annotations

import json
import logging

from starlette.websockets import WebSocket, WebSocketDisconnect

from presearch.config import PResearchConfig
from presearch.providers import get_provider
from presearch.web.interviewer import (
    create_interview_chat,
    extract_refined_query,
    finalize,
    is_ready,
    send_answer,
    start_interview,
)
from presearch.web.session import SessionManager
from presearch.web.webui import WebUI

log = logging.getLogger(__name__)


async def ws_endpoint(websocket: WebSocket) -> None:
    """Handle a WebSocket connection for one research session."""
    await websocket.accept()
    mgr: SessionManager = websocket.app.state.session_manager
    db = websocket.app.state.db
    session = None
    interview_state: dict | None = None

    async def _cleanup_interview() -> None:
        nonlocal interview_state
        interview_state = None

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "data": {"message": "Invalid JSON"}})
                continue

            msg_type = msg.get("type", "")

            if msg_type == "refine":
                idea = msg.get("idea", "").strip()
                if not idea:
                    await websocket.send_json({
                        "type": "error", "data": {"message": "Please enter a research idea to refine"},
                    })
                    continue

                overrides = msg.get("config", {})
                safe_overrides = {}
                for k, v in overrides.items():
                    if v != "" and v is not None and k in PResearchConfig.model_fields:
                        safe_overrides[k] = v
                try:
                    config = PResearchConfig(**safe_overrides)
                except Exception as e:
                    await websocket.send_json({
                        "type": "error", "data": {"message": f"Invalid config: {e}"},
                    })
                    continue

                try:
                    provider = get_provider(config)
                    webui = WebUI(websocket, "interview")
                    chat = await create_interview_chat(provider, idea)
                    resp_text = await start_interview(chat, idea)
                    interview_state = {"chat": chat, "webui": webui, "phase": "interviewing", "original_idea": idea}
                    if is_ready(resp_text):
                        interview_state["phase"] = "awaiting_confirm"
                        await webui.interview_ready(resp_text)
                    else:
                        await webui.interview_question(resp_text)
                except Exception as e:
                    log.exception("Interview error: %s", e)
                    await websocket.send_json({
                        "type": "error", "data": {"message": f"Interview failed: {e}"},
                    })
                    _cleanup_interview()

            elif msg_type == "refine_answer":
                if not interview_state:
                    await websocket.send_json({
                        "type": "error", "data": {"message": "No active interview session"},
                    })
                    continue
                answer = msg.get("answer", "").strip()
                if not answer:
                    continue

                try:
                    chat = interview_state["chat"]
                    webui = interview_state["webui"]
                    resp_text = await send_answer(chat, answer)
                    if is_ready(resp_text):
                        interview_state["phase"] = "awaiting_confirm"
                        await webui.interview_ready(resp_text)
                    else:
                        await webui.interview_question(resp_text)
                except Exception as e:
                    log.exception("Interview error: %s", e)
                    await websocket.send_json({
                        "type": "error", "data": {"message": f"Interview failed: {e}"},
                    })
                    _cleanup_interview()

            elif msg_type == "refine_confirm":
                if not interview_state or interview_state.get("phase") != "awaiting_confirm":
                    await websocket.send_json({
                        "type": "error", "data": {"message": "Not awaiting confirmation"},
                    })
                    continue

                try:
                    chat = interview_state["chat"]
                    webui = interview_state["webui"]
                    confirm = msg.get("confirm", False)
                    if confirm:
                        resp_text = await finalize(chat)
                        refined = extract_refined_query(resp_text)
                        if not refined:
                            refined = interview_state.get("original_idea", "")
                        await webui.interview_complete(
                            refined, resp_text.replace(refined, "").strip() if refined else resp_text
                        )
                    else:
                        resp_text = await chat.send(
                            "Please ask more questions before we proceed to the delivery phase."
                        )
                        interview_state["phase"] = "interviewing"
                        await webui.interview_question(resp_text)
                except Exception as e:
                    log.exception("Interview error: %s", e)
                    await websocket.send_json({
                        "type": "error", "data": {"message": f"Interview failed: {e}"},
                    })
                finally:
                    _cleanup_interview()

            elif msg_type == "refine_cancel":
                _cleanup_interview()
                await websocket.send_json({"type": "interview_cancelled", "data": {}})

            elif msg_type == "start":
                # Guard: cancel previous session on this WS before starting a new one
                if session:
                    mgr.remove(session.session_id)
                    session = None

                query = msg.get("query", "").strip()
                if not query:
                    await websocket.send_json({
                        "type": "error", "data": {"message": "Query is required"},
                    })
                    continue

                overrides = msg.get("config", {})
                safe_overrides = {}
                for k, v in overrides.items():
                    if v != "" and v is not None and k in PResearchConfig.model_fields:
                        safe_overrides[k] = v
                try:
                    config = PResearchConfig(**safe_overrides)
                except Exception as e:
                    await websocket.send_json({
                        "type": "error", "data": {"message": f"Invalid config: {e}"},
                    })
                    continue

                session = mgr.create_session(websocket, config)
                await websocket.send_json({
                    "type": "session_created",
                    "data": {"session_id": session.session_id},
                })
                await session.start(query, db)

            elif msg_type in ("interrupt", "stop"):
                if not session:
                    await websocket.send_json({
                        "type": "error",
                        "data": {"message": "No active research session"},
                    })
                    continue
                message = msg.get("message", "stop") if msg_type == "interrupt" else "stop"
                await session.interrupt(message)

    except WebSocketDisconnect:
        pass
    except Exception as e:
        log.exception("WebSocket error: %s", e)
    finally:
        if session:
            mgr.remove(session.session_id)
