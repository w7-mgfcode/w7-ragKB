"""Web chat endpoint for the frontend.

Accepts authenticated chat requests, persists messages, runs the agent,
and returns a JSON response compatible with the frontend client.
"""

import json
import logging
import os
import re
import uuid
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from agent import AgentDeps, agent
from auth_middleware import get_current_user
from db import get_pool
from db_conversations import ensure_slack_user, fetch_conversation_history, store_message, update_conversation_title
from tools import retrieve_grounded_context_tool
from vertex_embeddings import VertexEmbeddingClient

logger = logging.getLogger(__name__)

router = APIRouter()
WEB_SESSION_ID_RE = re.compile(r"^[a-f0-9]{16}$")
NO_RAG_HIT_RESPONSE = (
    "Nem találtam releváns információt a jelenlegi tudásbázisban (RAG).\n\n"
    "Lehetséges következő lépések:\n"
    "1. Pontosítsd a kérdést kulcsszavakkal (pl. szolgáltatásnév, fájlnév, környezet).\n"
    "2. Kérd a dokumentumlista lekérését (`list your knowledge base`).\n"
    "3. Tölts fel/importálj kapcsolódó dokumentumot a RAG pipeline-ba, majd kérdezz újra."
)
NO_CONTEXT_OPTIONS_SUFFIX = (
    "\n\nLehetséges következő lépések:\n"
    "1. Pontosítsd a kérdést kulcsszavakkal (pl. szolgáltatásnév, fájlnév, környezet).\n"
    "2. Kérd a dokumentumlista lekérését (`list your knowledge base`).\n"
    "3. Tölts fel/importálj kapcsolódó dokumentumot a RAG pipeline-ba, majd kérdezz újra."
)


def _looks_like_no_context_answer(text: str) -> bool:
    t = (text or "").lower()
    indicators = (
        "cannot answer",
        "cannot be answered",
        "do not contain information",
        "insufficient context",
        "not in the provided context",
        "nincs információ",
        "nem található",
        "nem tudok válaszolni",
    )
    return any(ind in t for ind in indicators)


class AgentRequest(BaseModel):
    query: str
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    files: Optional[List[Dict[str, Any]]] = None


class AgentResponse(BaseModel):
    title: str
    session_id: str
    output: str


async def _ensure_web_conversation(session_id: str, user_id: str, email: str | None) -> None:
    """Create a web conversation row if it does not exist."""
    pool = await get_pool()
    row = await pool.fetchrow(
        "SELECT session_id, web_user_id FROM conversations WHERE session_id = $1",
        session_id,
    )
    if row:
        if str(row["web_user_id"]) != str(user_id):
            raise HTTPException(status_code=403, detail="Forbidden")
        return

    # Existing schema still requires slack_user_id + slack_channel_id.
    synthetic_slack_id = f"web:{user_id}"
    await ensure_slack_user(pool, synthetic_slack_id, email)

    await pool.execute(
        """
        INSERT INTO conversations (session_id, slack_user_id, slack_channel_id, web_user_id)
        VALUES ($1, $2, 'web', $3)
        """,
        session_id,
        synthetic_slack_id,
        user_id,
    )


async def _build_message_history(pool, session_id: str) -> list:
    """Reconstruct Pydantic AI message history from the last stored AI response.

    The ``message_data`` column of the most recent AI message contains the full
    serialised Pydantic AI conversation up to that point.  Deserialising it gives
    us the exact history the model saw, which we pass back via ``message_history``
    so the agent retains conversational context across requests.
    """
    rows = await fetch_conversation_history(pool, session_id)
    for row in reversed(rows):
        msg = row.get("message", {})
        md = row.get("message_data")
        if isinstance(msg, dict) and msg.get("type") == "ai" and md:
            try:
                from pydantic_ai.messages import ModelMessagesTypeAdapter

                return list(ModelMessagesTypeAdapter.validate_json(md))
            except Exception:
                logger.debug("Could not deserialize message_data for history", exc_info=True)
    return []


@router.post("/agent", response_model=AgentResponse)
async def run_web_chat(
    body: AgentRequest,
    current_user: dict = Depends(get_current_user),
) -> AgentResponse:
    """Run agent for an authenticated web user and persist messages."""
    query = (body.query or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="query is required")

    pool = await get_pool()
    user_id = str(current_user["sub"])
    email = current_user.get("email")

    requested_session_id = (body.session_id or "").strip()
    if requested_session_id and WEB_SESSION_ID_RE.match(requested_session_id):
        session_id = requested_session_id
    else:
        if requested_session_id:
            logger.warning(
                "Ignoring non-web session_id format from client: %s",
                requested_session_id,
            )
        session_id = uuid.uuid4().hex[:16]
    try:
        await _ensure_web_conversation(session_id, user_id, email)
    except HTTPException as exc:
        # If client sends a session from another user/admin view, recover by creating
        # a fresh conversation instead of failing the entire chat request with 403.
        if exc.status_code == 403 and body.session_id:
            logger.warning(
                "Rejected foreign session_id=%s for user_id=%s; creating new session",
                body.session_id,
                user_id,
            )
            session_id = uuid.uuid4().hex[:16]
            await _ensure_web_conversation(session_id, user_id, email)
        else:
            raise

    # Fetch conversation history BEFORE storing the new message so
    # the history only contains prior turns.
    message_history = await _build_message_history(pool, session_id)

    await store_message(pool, session_id, "human", query, files=body.files)

    result = None
    response_text = ""
    embedding_client = VertexEmbeddingClient()
    try:
        async with httpx.AsyncClient() as http_client:
            deps = AgentDeps(
                db_pool=pool,
                embedding_client=embedding_client,
                http_client=http_client,
                brave_api_key=os.getenv("BRAVE_API_KEY"),
                searxng_base_url=os.getenv("SEARXNG_BASE_URL"),
                memories="",
                slack_user_id=f"web:{user_id}",
            )

            # Soft RAG gate: pre-fetch knowledge base context and inject
            # it as run-level instructions so the user's actual query stays
            # clean in message_history (important for conversation continuity).
            prefetched = await retrieve_grounded_context_tool(
                pool=pool,
                embedding_client=embedding_client,
                user_query=query,
            )

            rag_instructions = None
            if prefetched and prefetched != "No relevant documents found.":
                rag_instructions = (
                    "Here is potentially relevant context from the knowledge base. "
                    "Use it when it helps answer the question, but you may also use "
                    "your tools (web search, list documents, etc.) if the context is "
                    "insufficient or the question is unrelated to the documents.\n\n"
                    f"Knowledge base context:\n{prefetched[:8000]}"
                )

            result = await agent.run(
                query,
                deps=deps,
                message_history=message_history,
                **({"instructions": rag_instructions} if rag_instructions else {}),
            )

            response_text = result.output if hasattr(result, "output") else str(result.data)
    except Exception:
        logger.exception("Web chat agent error for user_id=%s session_id=%s", user_id, session_id)
        response_text = "I'm having trouble processing your request. Please try again shortly."

    message_data = None
    if result is not None:
        try:
            from pydantic_ai.messages import ModelMessagesTypeAdapter

            message_data = ModelMessagesTypeAdapter.dump_json(
                result.all_messages()
            ).decode()
        except Exception:
            logger.debug("Could not serialise Pydantic AI messages", exc_info=True)

    await store_message(pool, session_id, "ai", response_text, message_data=message_data)

    # Set a first title for new conversations.
    await update_conversation_title(pool, session_id, query[:120])

    return AgentResponse(
        title=query[:120] or "New conversation",
        session_id=session_id,
        output=response_text,
    )
