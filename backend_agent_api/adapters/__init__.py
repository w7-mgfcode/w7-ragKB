"""Channel adapters for multi-platform messaging support.

This package contains channel adapters that translate between platform-specific
APIs and the unified Gateway protocol.

Available adapters:
    - TelegramAdapter: Telegram Bot API integration
    - SlackAdapter: Slack Socket Mode integration
    - DiscordAdapter: Discord Gateway integration
    - WhatsAppAdapter: WhatsApp Business API integration (planned)
"""

from .discord import DiscordAdapter
from .slack import SlackAdapter
from .telegram import TelegramAdapter

__all__ = ["SlackAdapter", "TelegramAdapter", "DiscordAdapter"]
