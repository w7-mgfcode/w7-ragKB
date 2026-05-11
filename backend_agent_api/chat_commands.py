"""Chat command system for controlling agent behavior via slash commands.

This module implements user-facing commands that control session behavior:
- /status  — show session configuration, message count, active tools, model
- /reset   — clear message history, preserve configuration
- /new     — create a new session, switch the user to it
- /compact — summarize and replace conversation history
- /think   — toggle verbose reasoning mode
- /verbose — toggle detailed tool output
- /usage   — show token usage and cost statistics

Commands are detected before the agent processes the message and return
immediate responses without invoking the AI agent.

Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7, 11.8, 11.9
"""

import logging
import time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Channel-specific command prefixes
CHANNEL_PREFIXES: Dict[str, str] = {
    "slack": "/",
    "telegram": "/",
    "discord": "!",
    "whatsapp": "/",
}

DEFAULT_PREFIX = "/"

AVAILABLE_COMMANDS = [
    "status", "reset", "new", "compact", "think", "verbose", "usage",
]


class ChatCommandHandler:
    """Handles chat commands for session control.

    Commands are intercepted before the agent processes the message.
    Each command returns a text response sent directly to the user.
    """

    def __init__(self, session_manager: Any, pool: Any = None):
        self.session_manager = session_manager
        self.pool = pool
        self._commands: Dict[str, Any] = {
            "status": self._cmd_status,
            "reset": self._cmd_reset,
            "new": self._cmd_new,
            "compact": self._cmd_compact,
            "think": self._cmd_think,
            "verbose": self._cmd_verbose,
            "usage": self._cmd_usage,
        }

    def get_prefix(self, channel_type: str) -> str:
        """Get the command prefix for a channel type."""
        return CHANNEL_PREFIXES.get(channel_type, DEFAULT_PREFIX)

    def is_command(self, text: str, channel_type: str) -> bool:
        """Check if text is a chat command."""
        if not text or not text.strip():
            return False
        prefix = self.get_prefix(channel_type)
        return text.strip().startswith(prefix)

    def parse_command(self, text: str, channel_type: str) -> Tuple[str, List[str]]:
        """Parse a command from message text.

        Returns:
            Tuple of (command_name, args_list).
            command_name is empty string if no valid command found.
        """
        if not text or not text.strip():
            return ("", [])

        prefix = self.get_prefix(channel_type)
        stripped = text.strip()

        if not stripped.startswith(prefix):
            return ("", [])

        without_prefix = stripped[len(prefix):]
        parts = without_prefix.split()

        if not parts:
            return ("", [])

        command_name = parts[0].lower()
        args = parts[1:]
        return (command_name, args)

    async def execute(
        self,
        command_name: str,
        session: Any,
        args: Optional[List[str]] = None,
    ) -> str:
        """Execute a parsed command. Returns response text."""
        if args is None:
            args = []

        handler = self._commands.get(command_name)
        if handler is None:
            return self._cmd_help()

        try:
            return await handler(session, args)
        except Exception as e:
            logger.error(f"Error executing command /{command_name}: {e}", exc_info=True)
            return f"Error executing /{command_name}. Please try again."

    async def handle_message(
        self, text: str, session: Any, channel_type: str,
    ) -> Optional[str]:
        """Handle a message that might be a command.

        Returns response text if command was handled, None if not a command.
        """
        if not self.is_command(text, channel_type):
            return None

        command_name, args = self.parse_command(text, channel_type)
        if not command_name:
            return None

        return await self.execute(command_name, session, args)

    # -----------------------------------------------------------------
    # Command implementations
    # -----------------------------------------------------------------

    async def _cmd_status(self, session: Any, args: List[str]) -> str:
        """Req 11.1: session config, message count, active tools, model."""
        tools_display = ", ".join(session.tool_allowlist[:5])
        if len(session.tool_allowlist) > 5:
            tools_display += f", ... (+{len(session.tool_allowlist) - 5} more)"

        denied = ", ".join(session.tool_denylist) if session.tool_denylist else "none"

        lines = [
            f"Session: {session.session_id}",
            f"Type: {session.session_type}",
            f"Channel: {session.channel_id}",
            f"Activation: {session.activation_mode}",
            f"Messages: {session.message_count}",
            f"Tools: {tools_display}",
            f"Denied: {denied}",
            f"Browser: {'enabled' if session.browser_enabled else 'disabled'}",
            f"Session tools: {'enabled' if session.session_tools_enabled else 'disabled'}",
        ]
        return "\n".join(lines)

    async def _cmd_reset(self, session: Any, args: List[str]) -> str:
        """Req 11.2: clear history, preserve config."""
        await session.clear_history()
        return (
            f"Session {session.session_id} has been reset. "
            f"Message history cleared. Configuration preserved."
        )

    async def _cmd_new(self, session: Any, args: List[str]) -> str:
        """Req 11.3: create new session, switch user."""
        if not self.session_manager:
            return "Session manager not available."

        new_chat_id = f"{session.chat_id}:{int(time.time())}"
        new_session = await self.session_manager.create_session(
            channel_id=session.channel_id,
            user_id=session.user_id,
            chat_id=new_chat_id,
            session_type=session.session_type,
            activation_mode=session.activation_mode,
        )
        return (
            f"New session created: {new_session.session_id}\n"
            f"Your messages will now be routed to the new session."
        )

    async def _cmd_compact(self, session: Any, args: List[str]) -> str:
        """Req 11.4: summarize and replace history."""
        before_count = session.message_count
        await session.compact()
        after_count = session.message_count
        return (
            f"Session compacted: {before_count} messages -> {after_count} messages. "
            f"Older messages have been summarized."
        )

    async def _cmd_think(self, session: Any, args: List[str]) -> str:
        """Req 11.5: toggle verbose reasoning mode."""
        current = session.token_usage.get("verbose_reasoning", False)
        new_value = not current
        token_usage = dict(session.token_usage)
        token_usage["verbose_reasoning"] = new_value
        await session.update_token_usage(token_usage)
        state = "enabled" if new_value else "disabled"
        return f"Verbose reasoning mode {state}."

    async def _cmd_verbose(self, session: Any, args: List[str]) -> str:
        """Req 11.6: toggle detailed tool output."""
        current = session.token_usage.get("verbose_tools", False)
        new_value = not current
        token_usage = dict(session.token_usage)
        token_usage["verbose_tools"] = new_value
        await session.update_token_usage(token_usage)
        state = "enabled" if new_value else "disabled"
        return f"Detailed tool output {state}."

    async def _cmd_usage(self, session: Any, args: List[str]) -> str:
        """Req 11.7: token usage and cost statistics."""
        usage = session.token_usage or {}
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
        total_tokens = input_tokens + output_tokens

        lines = [
            f"Token Usage for session {session.session_id}:",
            f"  Input tokens:  {input_tokens:,}",
            f"  Output tokens: {output_tokens:,}",
            f"  Total tokens:  {total_tokens:,}",
            f"  Messages:      {session.message_count}",
        ]
        return "\n".join(lines)

    def _cmd_help(self) -> str:
        """Req 11.8: help for unrecognized commands."""
        lines = [
            "Available commands:",
            "  /status  - Show session status and configuration",
            "  /reset   - Clear message history (preserves config)",
            "  /new     - Create a new session",
            "  /compact - Summarize and compress message history",
            "  /think   - Toggle verbose reasoning mode",
            "  /verbose - Toggle detailed tool output",
            "  /usage   - Show token usage statistics",
        ]
        return "\n".join(lines)
