"""Slack Socket Mode bot for the w7-ragKB AI Agent.

DEPRECATED: This module is deprecated in favor of adapters/slack.py which
integrates with the multi-channel Gateway architecture. This module is
kept for backward compatibility and monitoring purposes only.

The new architecture uses:
- adapters/slack.py: SlackAdapter for Slack integration
- gateway_server.py: Control Plane for message routing
- session_manager.py: Unified session management across channels
- gateway_message_handler.py: Message processing pipeline

Connects to Slack via outbound WebSocket (no inbound HTTP required).
Handles message events, wires them to the Pydantic AI agent, and
manages conversation sessions derived from channel + thread.
"""

import asyncio
import logging
import os
import warnings

from slack_bolt.async_app import AsyncApp
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
from slack_sdk.errors import SlackApiError

from agent import AgentDeps, agent
from db import get_pool
from db_conversations import (
    create_conversation,
    ensure_slack_user,
    fetch_conversation_history,
    generate_session_id,
    store_message,
)
from vertex_embeddings import VertexEmbeddingClient

logger = logging.getLogger(__name__)

# Deprecation warning
warnings.warn(
    "slack_bot module is deprecated. Use adapters/slack.py (SlackAdapter) instead. "
    "This module is kept for backward compatibility and monitoring only.",
    DeprecationWarning,
    stacklevel=2,
)

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_APP_TOKEN = os.getenv("SLACK_APP_TOKEN")

app = AsyncApp(token=SLACK_BOT_TOKEN)


async def _build_agent_deps(slack_user_id: str) -> AgentDeps:
    """Construct AgentDeps for a single message invocation."""
    import httpx

    pool = await get_pool()
    embedding_client = VertexEmbeddingClient()

    return AgentDeps(
        db_pool=pool,
        embedding_client=embedding_client,
        http_client=httpx.AsyncClient(),
        brave_api_key=os.getenv("BRAVE_API_KEY"),
        searxng_base_url=os.getenv("SEARXNG_BASE_URL"),
        memories="",
        slack_user_id=slack_user_id,
    )


async def _ensure_conversation_exists(
    session_id: str,
    slack_user_id: str,
    channel_id: str,
) -> None:
    """Create the conversation row if it doesn't already exist."""
    pool = await get_pool()
    existing = await pool.fetchval(
        "SELECT 1 FROM conversations WHERE session_id = $1",
        session_id,
    )
    if not existing:
        await create_conversation(pool, slack_user_id, session_id, channel_id)


async def run_agent_for_message(
    user_id: str,
    text: str,
    channel_id: str,
    thread_ts: str,
) -> str:
    """Process a Slack message through the Pydantic AI agent.

    Tracks the user, ensures a conversation session exists, stores
    the inbound message, runs the agent, stores the response, and
    returns the agent's reply text.
    """
    pool = await get_pool()
    session_id = generate_session_id(channel_id, thread_ts)

    await ensure_slack_user(pool, user_id)
    await _ensure_conversation_exists(session_id, user_id, channel_id)
    await store_message(pool, session_id, "human", text)

    deps = await _build_agent_deps(user_id)

    # Fetch prior messages for context
    history = await fetch_conversation_history(pool, session_id)

    result = None
    try:
        result = await agent.run(text, deps=deps)
        response_text = result.output if hasattr(result, "output") else str(result.data)
    except Exception:
        logger.exception(
            "Agent error for user=%s channel=%s session=%s",
            user_id,
            channel_id,
            session_id,
        )
        response_text = "I'm having trouble processing your request. Please try again shortly."

    # Persist the AI response, including Pydantic AI message data when available
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

    return response_text


@app.event("message")
async def handle_message(event, say):
    """Handle incoming Slack message events.

    Extracts user ID, text, channel, and thread_ts from the event,
    runs the agent, and posts the response back to the same thread.
    """
    # Ignore bot messages and message_changed subtypes
    if event.get("subtype") in ("bot_message", "message_changed", "message_deleted"):
        return
    if event.get("bot_id"):
        return

    user_id = event.get("user")
    if not user_id:
        return

    text = event.get("text", "")
    if not text.strip():
        return

    channel = event["channel"]
    thread_ts = event.get("thread_ts", event["ts"])

    logger.info(
        "Received message from user=%s channel=%s thread=%s",
        user_id,
        channel,
        thread_ts,
    )

    try:
        response = await run_agent_for_message(user_id, text, channel, thread_ts)
        await say(text=response, thread_ts=thread_ts)
    except SlackApiError:
        logger.exception(
            "Failed to post response for user=%s channel=%s",
            user_id,
            channel,
        )
        # Retry once on Slack API failure
        try:
            await say(
                text="Sorry, I encountered an error. Please try again.",
                thread_ts=thread_ts,
            )
        except SlackApiError:
            logger.error("Retry also failed for channel=%s", channel)


async def start_socket_mode():
    """Start 2 parallel Socket Mode connections for high availability.

    If one WebSocket drops, the other continues processing messages
    while the SDK reconnects the failed one automatically.
    """
    handler1 = AsyncSocketModeHandler(app, SLACK_APP_TOKEN)
    handler2 = AsyncSocketModeHandler(app, SLACK_APP_TOKEN)

    logger.info("Starting 2 Socket Mode handlers for HA")
    try:
        await asyncio.gather(
            handler1.start_async(),
            handler2.start_async(),
        )
    finally:
        # Ensure aiohttp sessions owned by socket handlers are closed
        # when the process receives SIGTERM or tasks are cancelled.
        for handler in (handler1, handler2):
            close_async = getattr(handler, "close_async", None)
            if callable(close_async):
                try:
                    await close_async()
                except Exception:
                    logger.debug("Failed to close Socket Mode handler cleanly", exc_info=True)
