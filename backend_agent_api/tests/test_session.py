"""Unit tests for Session class.

Tests cover:
- Session initialization and configuration
- Message storage and retrieval
- History compaction
- Activation mode checking
- Tool allowlist/denylist enforcement
- Configuration updates
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from session import Session, SessionConfig


@pytest.fixture
def mock_pool():
    """Create a mock database connection pool."""
    pool = MagicMock()
    return pool


@pytest.fixture
def sample_session(mock_pool):
    """Create a sample session for testing."""
    return Session(
        pool=mock_pool,
        session_id="slack-main:user123:dm",
        channel_id="slack-main",
        user_id="user123",
        chat_id="dm",
        session_type="main",
        activation_mode="mention",
        tool_allowlist=["read_*", "web_*"],
        tool_denylist=["web_execute"],
        max_message_history=100,
        auto_compact_threshold=80,
        browser_enabled=False,
        session_tools_enabled=True,
        message_count=0,
    )


class TestSessionInitialization:
    """Tests for Session initialization."""
    
    def test_session_creation(self, mock_pool):
        """Test basic session creation."""
        session = Session(
            pool=mock_pool,
            session_id="test-session",
            channel_id="slack-main",
            user_id="user123",
            chat_id="dm",
            session_type="main",
        )
        
        assert session.session_id == "test-session"
        assert session.channel_id == "slack-main"
        assert session.user_id == "user123"
        assert session.chat_id == "dm"
        assert session.session_type == "main"
        assert session.activation_mode == "mention"
        assert session.tool_allowlist == ["*"]
        assert session.tool_denylist == []
        assert session.message_count == 0
    
    def test_session_config_property(self, sample_session):
        """Test session config property returns valid SessionConfig."""
        config = sample_session.config
        
        assert isinstance(config, SessionConfig)
        assert config.session_id == sample_session.session_id
        assert config.channel_id == sample_session.channel_id
        assert config.activation_mode == sample_session.activation_mode
        assert config.tool_allowlist == sample_session.tool_allowlist
    
    def test_session_repr(self, sample_session):
        """Test session string representation."""
        repr_str = repr(sample_session)
        
        assert "Session(" in repr_str
        assert "slack-main:user123:dm" in repr_str
        assert "slack-main" in repr_str
        assert "user123" in repr_str


class TestMessageManagement:
    """Tests for message storage and retrieval."""
    
    @pytest.mark.asyncio
    async def test_add_message(self, sample_session):
        """Test adding a message to session history."""
        # Mock the database function
        with patch("session.add_session_message", new_callable=AsyncMock) as mock_add:
            mock_add.return_value = {
                "message_id": 1,
                "session_id": sample_session.session_id,
                "role": "user",
                "content": "Hello",
                "metadata": {},
            }
            
            message = await sample_session.add_message("user", "Hello")
            
            assert message["role"] == "user"
            assert message["content"] == "Hello"
            assert sample_session.message_count == 1
            
            # Verify database function was called
            mock_add.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_history(self, sample_session):
        """Test retrieving message history."""
        # Mock the database function
        with patch("session.get_session_messages", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = [
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there!"},
            ]
            
            history = await sample_session.get_history(limit=10)
            
            assert len(history) == 2
            assert history[0]["role"] == "user"
            assert history[1]["role"] == "assistant"
            
            # Verify database function was called
            mock_get.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_clear_history(self, sample_session):
        """Test clearing message history."""
        sample_session.message_count = 50
        
        with patch("session.clear_session_messages", new_callable=AsyncMock) as mock_clear:
            await sample_session.clear_history()
            
            assert sample_session.message_count == 0
            mock_clear.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_history_caching(self, sample_session):
        """Test that message history is cached."""
        with patch("session.get_session_messages", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = [{"role": "user", "content": "Test"}]
            
            # First call should fetch from database
            history1 = await sample_session.get_history()
            assert mock_get.call_count == 1
            
            # Second call should use cache
            history2 = await sample_session.get_history()
            assert mock_get.call_count == 1  # Not called again
            
            assert history1 == history2


class TestHistoryCompaction:
    """Tests for message history compaction."""
    
    @pytest.mark.asyncio
    async def test_compaction_below_threshold(self, sample_session):
        """Test that compaction is skipped when below threshold."""
        sample_session.message_count = 50
        sample_session.auto_compact_threshold = 80
        
        with patch("session.get_session_messages", new_callable=AsyncMock) as mock_get:
            await sample_session.compact()
            
            # Should not fetch messages if below threshold
            mock_get.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_compaction_above_threshold(self, sample_session):
        """Test that compaction occurs when above threshold."""
        sample_session.message_count = 100
        sample_session.auto_compact_threshold = 80
        
        # Create 100 mock messages
        messages = [
            {"role": "user" if i % 2 == 0 else "assistant", "content": f"Message {i}"}
            for i in range(100)
        ]
        
        with patch("session.get_session_messages", new_callable=AsyncMock) as mock_get, \
             patch("session.clear_session_messages", new_callable=AsyncMock) as mock_clear, \
             patch("session.add_session_message", new_callable=AsyncMock) as mock_add:
            
            mock_get.return_value = messages
            mock_add.return_value = {"message_id": 1}
            
            await sample_session.compact()
            
            # Should clear messages and rebuild
            mock_clear.assert_called_once()
            
            # Should add summary + kept messages
            # (1 summary + 20% of 100 = 21 total)
            assert mock_add.call_count == 21
    
    @pytest.mark.asyncio
    async def test_auto_compaction_on_add_message(self, sample_session):
        """Test that compaction is triggered automatically when threshold is reached."""
        sample_session.message_count = 79
        sample_session.auto_compact_threshold = 80
        
        with patch("session.add_session_message", new_callable=AsyncMock) as mock_add, \
             patch.object(sample_session, "compact", new_callable=AsyncMock) as mock_compact:
            
            mock_add.return_value = {"message_id": 1}
            
            await sample_session.add_message("user", "This triggers compaction")
            
            # Should trigger compaction
            mock_compact.assert_called_once()


class TestActivationMode:
    """Tests for activation mode checking."""
    
    @pytest.mark.asyncio
    async def test_activation_mode_always(self, sample_session):
        """Test activation mode 'always' responds to all messages."""
        sample_session.activation_mode = "always"
        
        assert await sample_session.check_activation("Hello", bot_mention=False) is True
        assert await sample_session.check_activation("Hello", bot_mention=True) is True
    
    @pytest.mark.asyncio
    async def test_activation_mode_mention(self, sample_session):
        """Test activation mode 'mention' only responds to mentions."""
        sample_session.activation_mode = "mention"
        
        assert await sample_session.check_activation("Hello", bot_mention=False) is False
        assert await sample_session.check_activation("@bot Hello", bot_mention=True) is True
    
    @pytest.mark.asyncio
    async def test_activation_mode_manual(self, sample_session):
        """Test activation mode 'manual' only responds to commands."""
        sample_session.activation_mode = "manual"
        
        assert await sample_session.check_activation("Hello", bot_mention=False) is False
        assert await sample_session.check_activation("@bot Hello", bot_mention=True) is False
        assert await sample_session.check_activation("/status", bot_mention=False) is True


class TestToolAllowlist:
    """Tests for tool allowlist and denylist enforcement."""
    
    def test_tool_allowed_wildcard(self, mock_pool):
        """Test that wildcard allows all tools."""
        session = Session(
            pool=mock_pool,
            session_id="test",
            channel_id="slack",
            user_id="user",
            chat_id="dm",
            session_type="main",
            tool_allowlist=["*"],
        )
        
        assert session.is_tool_allowed("read_file") is True
        assert session.is_tool_allowed("web_search") is True
        assert session.is_tool_allowed("any_tool") is True
    
    def test_tool_allowed_pattern_matching(self, sample_session):
        """Test that pattern matching works for allowlist."""
        # sample_session has allowlist: ["read_*", "web_*"]
        
        assert sample_session.is_tool_allowed("read_file") is True
        assert sample_session.is_tool_allowed("read_directory") is True
        assert sample_session.is_tool_allowed("web_search") is True
        assert sample_session.is_tool_allowed("web_fetch") is True
        assert sample_session.is_tool_allowed("execute_code") is False
    
    def test_tool_denylist_precedence(self, sample_session):
        """Test that denylist takes precedence over allowlist."""
        # sample_session has allowlist: ["read_*", "web_*"]
        # and denylist: ["web_execute"]
        
        assert sample_session.is_tool_allowed("web_search") is True
        assert sample_session.is_tool_allowed("web_execute") is False
    
    def test_tool_denylist_pattern_matching(self, mock_pool):
        """Test that pattern matching works for denylist."""
        session = Session(
            pool=mock_pool,
            session_id="test",
            channel_id="slack",
            user_id="user",
            chat_id="dm",
            session_type="main",
            tool_allowlist=["*"],
            tool_denylist=["execute_*", "delete_*"],
        )
        
        assert session.is_tool_allowed("read_file") is True
        assert session.is_tool_allowed("execute_code") is False
        assert session.is_tool_allowed("execute_shell") is False
        assert session.is_tool_allowed("delete_file") is False


class TestConfigurationUpdates:
    """Tests for session configuration updates."""
    
    @pytest.mark.asyncio
    async def test_update_activation_mode(self, sample_session):
        """Test updating activation mode."""
        with patch("session.update_session_activation_mode", new_callable=AsyncMock) as mock_update:
            await sample_session.update_activation_mode("always")
            
            assert sample_session.activation_mode == "always"
            mock_update.assert_called_once_with(
                sample_session.pool,
                sample_session.session_id,
                "always",
            )
    
    @pytest.mark.asyncio
    async def test_update_tool_allowlist(self, sample_session):
        """Test updating tool allowlist."""
        new_allowlist = ["read_*", "web_search"]
        new_denylist = ["read_sensitive"]
        
        with patch("session.update_session_tool_allowlist", new_callable=AsyncMock) as mock_update:
            await sample_session.update_tool_allowlist(new_allowlist, new_denylist)
            
            assert sample_session.tool_allowlist == new_allowlist
            assert sample_session.tool_denylist == new_denylist
            mock_update.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_update_token_usage(self, sample_session):
        """Test updating token usage statistics."""
        token_usage = {"input_tokens": 100, "output_tokens": 50}
        
        with patch("session.update_session_token_usage", new_callable=AsyncMock) as mock_update:
            await sample_session.update_token_usage(token_usage)
            
            assert sample_session.token_usage == token_usage
            mock_update.assert_called_once()


class TestSessionSerialization:
    """Tests for session serialization."""
    
    def test_to_dict(self, sample_session):
        """Test converting session to dictionary."""
        session_dict = sample_session.to_dict()
        
        assert session_dict["session_id"] == sample_session.session_id
        assert session_dict["channel_id"] == sample_session.channel_id
        assert session_dict["user_id"] == sample_session.user_id
        assert session_dict["session_type"] == sample_session.session_type
        assert session_dict["activation_mode"] == sample_session.activation_mode
        assert session_dict["tool_allowlist"] == sample_session.tool_allowlist
        assert session_dict["message_count"] == sample_session.message_count
