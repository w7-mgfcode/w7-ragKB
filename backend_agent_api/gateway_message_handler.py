"""Gateway message handler for processing inbound messages through sessions.

This module implements the message processing pipeline that:
- Receives InboundMessage from Control Plane
- Routes to appropriate Session via SessionManager
- Executes the Pydantic AI agent with session context
- Sends OutboundMessage back through Control Plane

This replaces the direct Slack bot message handling with a unified
multi-channel approach using the Gateway architecture.
"""

import logging
import os
from typing import Optional

import httpx

from agent import AgentDeps, agent
from agent_tool_filter import run_agent_with_tool_filter
from chat_commands import ChatCommandHandler
from db import get_pool
from gateway_protocol import InboundMessage, MessageSerializer
from gateway_server import get_control_plane
from session_manager import get_session_manager
from tools import retrieve_grounded_context_tool
from vertex_embeddings import VertexEmbeddingClient

logger = logging.getLogger(__name__)

# Lazy-initialised command handler (needs SessionManager at runtime)
_command_handler: Optional[ChatCommandHandler] = None


def _get_command_handler() -> ChatCommandHandler:
    """Return the module-level ChatCommandHandler, creating it on first use."""
    global _command_handler
    if _command_handler is None:
        _command_handler = ChatCommandHandler(get_session_manager())
    return _command_handler


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


async def build_agent_deps(slack_user_id: str) -> AgentDeps:
    """Construct AgentDeps for agent invocation.
    
    Args:
        slack_user_id: Slack user ID for memory retrieval
        
    Returns:
        AgentDeps instance
    """
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


async def process_inbound_message(message: InboundMessage) -> None:
    """Process an inbound message through the session and agent.
    
    This is the main message processing pipeline:
    1. Get or create session via SessionManager
    2. Check activation mode (for group chats)
    3. Store user message in session
    4. Run agent with session context
    5. Store agent response in session
    6. Send response back through Control Plane
    
    Args:
        message: InboundMessage from channel adapter
    """
    try:
        # Get session manager
        session_manager = get_session_manager()
        if not session_manager:
            logger.error("SessionManager not initialized")
            return
        
        # Determine session type based on chat context
        session_type = "main"  # Default to main session
        metadata = message.metadata or {}
        
        # For Slack: check channel_type
        if metadata.get("channel_type") in ["group", "channel"]:
            session_type = "group"
        
        # For Telegram: check chat_type
        if metadata.get("chat_type") in ["group", "supergroup"]:
            session_type = "group"
        
        # Get or create session
        session = await session_manager.get_or_create_session(
            channel_id=message.channel_id,
            user_id=message.user_id,
            chat_id=message.chat_id,
            thread_id=message.thread_id,
            session_type=session_type,
            activation_mode="mention" if session_type == "group" else "always",
        )
        
        logger.info(
            f"Processing message {message.message_id} in session {session.session_id}"
        )
        
        # Check activation for group sessions
        if session_type == "group":
            bot_mention = metadata.get("bot_mention", False)
            should_respond = await session.check_activation(message.text, bot_mention)
            
            if not should_respond:
                logger.debug(
                    f"Skipping message {message.message_id} - activation check failed"
                )
                return
        
        # Store user message
        await session.add_message("user", message.text, metadata)

        # Intercept slash commands before invoking the AI agent
        channel_type = metadata.get("source_platform", "slack")
        command_handler = _get_command_handler()
        command_response = await command_handler.handle_message(
            message.text, session, channel_type
        )
        if command_response is not None:
            await session.add_message("assistant", command_response)
            await send_outbound_message(
                channel_id=message.channel_id,
                chat_id=message.chat_id,
                thread_id=message.thread_id,
                text=command_response,
                reply_to=message.message_id,
            )
            return

        # Build agent dependencies
        deps = await build_agent_deps(message.user_id)
        
        # Run agent
        result = None
        try:
            is_web_channel = metadata.get("source_platform") == "web"

            if is_web_channel:
                # Web chat: soft RAG gate — inject KB context as run-level
                # instructions so the user query stays clean in history.
                prefetched = await retrieve_grounded_context_tool(
                    pool=deps.db_pool,
                    embedding_client=deps.embedding_client,
                    user_query=message.text,
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
                result = await run_agent_with_tool_filter(
                    agent,
                    message.text,
                    deps,
                    session=session,
                    **({"instructions": rag_instructions} if rag_instructions else {}),
                )
                response_text = result.output if hasattr(result, "output") else str(result)
            else:
                # Messaging platforms (Slack, Telegram, etc.): full tool access
                result = await run_agent_with_tool_filter(
                    agent, message.text, deps, session=session,
                )
                response_text = result.output if hasattr(result, "output") else str(result)
        except Exception:
            logger.exception(
                f"Agent error for session {session.session_id}",
            )
            response_text = "I'm having trouble processing your request. Please try again shortly."
        
        # Store agent response with Pydantic AI message data
        message_data = None
        if result is not None:
            try:
                from pydantic_ai.messages import ModelMessagesTypeAdapter
                
                message_data = ModelMessagesTypeAdapter.dump_json(
                    result.all_messages()
                ).decode()
            except Exception:
                logger.debug("Could not serialize Pydantic AI messages", exc_info=True)
        
        await session.add_message("assistant", response_text, {"message_data": message_data})
        
        # Send response back through Control Plane
        await send_outbound_message(
            channel_id=message.channel_id,
            chat_id=message.chat_id,
            thread_id=message.thread_id,
            text=response_text,
            reply_to=message.message_id,
        )
        
        logger.info(
            f"Processed message {message.message_id} successfully"
        )
    
    except Exception as e:
        logger.error(
            f"Failed to process inbound message {message.message_id}: {e}",
            exc_info=True,
        )
        try:
            await send_outbound_message(
                channel_id=message.channel_id,
                chat_id=message.chat_id,
                thread_id=message.thread_id,
                text="Sorry, I encountered an error. Please try again.",
                reply_to=message.message_id,
            )
        except Exception:
            logger.error(
                "Failed to send error response for %s",
                message.message_id,
                exc_info=True,
            )


async def send_outbound_message(
    channel_id: str,
    chat_id: str,
    text: str,
    thread_id: Optional[str] = None,
    reply_to: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> None:
    """Send an outbound message through the Control Plane.
    
    Args:
        channel_id: Target channel adapter
        chat_id: Target chat/group/DM
        text: Response text
        thread_id: Optional thread identifier
        reply_to: Optional message ID to reply to
        metadata: Optional platform-specific metadata
    """
    control_plane = get_control_plane()
    if not control_plane:
        logger.error("Control Plane not initialized")
        return
    
    # Generate message ID
    import time
    message_id = f"{channel_id}:{chat_id}:{int(time.time() * 1000)}"
    
    # Create outbound message
    outbound_msg = MessageSerializer.create_outbound_message(
        message_id=message_id,
        channel_id=channel_id,
        chat_id=chat_id,
        text=text,
        thread_id=thread_id,
        reply_to=reply_to,
        metadata=metadata,
    )
    
    # Deliver through Control Plane
    success = await control_plane.deliver_outbound_message(outbound_msg)
    
    if not success:
        logger.error(f"Failed to deliver outbound message {message_id}")


async def start_message_handler() -> None:
    """Start the message handler that processes inbound messages.
    
    This subscribes to inbound messages from the Control Plane and
    processes them through sessions and the agent.
    """
    logger.info("Starting Gateway message handler")
    
    control_plane = get_control_plane()
    if not control_plane:
        logger.error("Control Plane not initialized, cannot start message handler")
        return
    
    # Register message handler with Control Plane
    # This will be called for each inbound message
    # For now, we'll poll the Control Plane for messages
    # In a future enhancement, this could use a pub/sub pattern
    
    logger.info("Gateway message handler started")


async def stop_message_handler() -> None:
    """Stop the message handler."""
    logger.info("Gateway message handler stopped")
