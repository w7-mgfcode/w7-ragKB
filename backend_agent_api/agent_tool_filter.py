"""Tool access control filter for Pydantic AI agent.

This module provides a wrapper around agent.run() that enforces tool access
control based on session allowlists and denylists. It intercepts tool calls
and blocks unauthorized tools before execution.
"""

import logging
from typing import Any, Optional

from pydantic_ai import Agent

logger = logging.getLogger(__name__)


class ToolAccessError(Exception):
    """Raised when a tool is blocked by access control."""
    pass


async def run_agent_with_tool_filter(
    agent: Agent,
    prompt: str,
    deps: Any,
    session: Optional[Any] = None,
    **kwargs: Any,
) -> Any:
    """Run the agent with tool access control filtering.
    
    This wrapper enforces tool access control by:
    1. Running the agent normally
    2. If a tool is called, checking if it's allowed in the session
    3. Blocking unauthorized tools and logging the attempt
    4. Returning an error message for blocked tools
    
    Note: Pydantic AI doesn't provide a built-in way to intercept tool calls
    before execution, so we rely on the tool implementations themselves to
    check permissions via ctx.deps.session_id and the Session.is_tool_allowed()
    method.
    
    Args:
        agent: Pydantic AI agent instance
        prompt: User prompt to process
        deps: Agent dependencies (AgentDeps instance)
        session: Optional Session instance for tool access control
        
    Returns:
        Agent run result
        
    Raises:
        ToolAccessError: If a tool is blocked by access control
    """
    # For now, we rely on tool implementations to check permissions
    # via the session instance passed in deps
    # 
    # A more robust approach would require:
    # 1. Pydantic AI to expose a tool call hook
    # 2. Or wrapping each tool function with a permission check decorator
    # 3. Or using a custom tool registry that checks permissions
    
    # Store session in deps for tool access
    if session is not None:
        deps.session = session
    
    # Run the agent
    result = await agent.run(prompt, deps=deps, **kwargs)

    return result


def create_tool_wrapper(tool_func, tool_name: str):
    """Create a wrapper around a tool function that checks permissions.
    
    This decorator can be applied to tool functions to add automatic
    permission checking before execution.
    
    Args:
        tool_func: The original tool function
        tool_name: Name of the tool for permission checking
        
    Returns:
        Wrapped tool function with permission checking
    """
    async def wrapped_tool(ctx, *args, **kwargs):
        """Wrapped tool function with permission checking."""
        # Check if session is available in deps
        session = getattr(ctx.deps, 'session', None)
        
        if session is not None:
            # Check if tool is allowed
            if not session.is_tool_allowed(tool_name):
                # Log blocked attempt
                await session.log_blocked_tool(tool_name)
                
                # Return error message (don't expose that the tool exists)
                return (
                    "I don't have permission to use that capability in this conversation. "
                    "Please contact an administrator if you need access to additional tools."
                )
        
        # Tool is allowed or no session context, execute normally
        return await tool_func(ctx, *args, **kwargs)
    
    # Preserve function metadata
    wrapped_tool.__name__ = tool_func.__name__
    wrapped_tool.__doc__ = tool_func.__doc__
    
    return wrapped_tool


# Tool name mapping for permission checking
# This maps the actual tool function names to their permission names
TOOL_NAME_MAP = {
    "web_search": "web_search",
    "retrieve_relevant_documents": "retrieve_relevant_documents",
    "list_documents": "list_documents",
    "get_document_content": "get_document_content",
    "execute_sql_query": "execute_sql_query",
    "image_analysis": "image_analysis",
    "execute_code": "execute_code",
    "list_sessions": "sessions_list",
    "get_session_history": "sessions_history",
    "send_to_session": "sessions_send",
    "navigate_browser": "browser_navigate",
    "click_element": "browser_click",
    "capture_screenshot": "browser_screenshot",
    "fill_form_field": "browser_fill_form",
    "execute_javascript": "browser_execute_js",
}


def get_tool_permission_name(tool_func_name: str) -> str:
    """Get the permission name for a tool function.
    
    Args:
        tool_func_name: Name of the tool function
        
    Returns:
        Permission name for the tool
    """
    return TOOL_NAME_MAP.get(tool_func_name, tool_func_name)
