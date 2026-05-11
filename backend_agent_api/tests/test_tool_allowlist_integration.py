"""Integration tests for tool allowlist with Session and SessionManager.

Tests the complete flow:
1. SessionManager creates session with tool allowlist
2. Session checks tool permissions
3. Blocked tools are logged to audit trail
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from session import Session
from tool_allowlist import ToolAllowlist, init_tool_allowlist


@pytest.fixture
def mock_pool():
    """Create a mock database connection pool."""
    pool = MagicMock()
    pool.acquire = AsyncMock()
    pool.execute = AsyncMock()
    
    # Mock connection context manager
    conn = MagicMock()
    conn.execute = AsyncMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock()
    
    return pool


class TestSessionToolAllowlistIntegration:
    """Test integration between Session and tool allowlist."""
    
    def test_session_with_wildcard_allowlist(self, mock_pool):
        """Session with wildcard allowlist should allow all tools."""
        session = Session(
            pool=mock_pool,
            session_id="session123",
            channel_id="slack-main",
            user_id="user123",
            chat_id="dm",
            session_type="main",
            tool_allowlist=["*"],
            tool_denylist=[],
        )
        
        # All tools should be allowed
        assert session.is_tool_allowed("web_search")
        assert session.is_tool_allowed("execute_code")
        assert session.is_tool_allowed("browser_navigate")
        assert session.is_tool_allowed("any_tool")
    
    def test_session_with_restricted_allowlist(self, mock_pool):
        """Session with restricted allowlist should block unauthorized tools."""
        session = Session(
            pool=mock_pool,
            session_id="session123",
            channel_id="telegram-bot1",
            user_id="user456",
            chat_id="group789",
            session_type="group",
            tool_allowlist=["web_*", "list_*", "retrieve_*"],
            tool_denylist=[],
        )
        
        # Allowed tools
        assert session.is_tool_allowed("web_search")
        assert session.is_tool_allowed("list_documents")
        assert session.is_tool_allowed("retrieve_relevant_documents")
        
        # Blocked tools
        assert not session.is_tool_allowed("execute_code")
        assert not session.is_tool_allowed("browser_navigate")
        assert not session.is_tool_allowed("execute_sql_query")
    
    def test_session_with_denylist_precedence(self, mock_pool):
        """Session denylist should override allowlist."""
        session = Session(
            pool=mock_pool,
            session_id="session123",
            channel_id="discord-main",
            user_id="user789",
            chat_id="channel456",
            session_type="group",
            tool_allowlist=["*"],
            tool_denylist=["execute_*", "browser_*"],
        )
        
        # Allowed tools
        assert session.is_tool_allowed("web_search")
        assert session.is_tool_allowed("list_documents")
        
        # Blocked by denylist
        assert not session.is_tool_allowed("execute_code")
        assert not session.is_tool_allowed("execute_sql_query")
        assert not session.is_tool_allowed("browser_navigate")
        assert not session.is_tool_allowed("browser_click")
    
    @pytest.mark.asyncio
    async def test_session_logs_blocked_tools(self, mock_pool):
        """Session should log blocked tool attempts to audit trail."""
        session = Session(
            pool=mock_pool,
            session_id="session123",
            channel_id="slack-main",
            user_id="user123",
            chat_id="dm",
            session_type="main",
            tool_allowlist=["web_*"],
            tool_denylist=[],
        )
        
        # Check that tool is blocked
        assert not session.is_tool_allowed("execute_code")
        
        # Log the blocked attempt
        await session.log_blocked_tool("execute_code")
        
        # Verify database insert was called
        mock_pool.execute.assert_called_once()
        call_args = mock_pool.execute.call_args
        sql = call_args[0][0]
        
        assert "INSERT INTO tool_access_log" in sql
        assert call_args[0][1] == "session123"  # session_id
        assert call_args[0][2] == "execute_code"  # tool_name
        assert call_args[0][5] is False  # access_granted


class TestToolAllowlistInitialization:
    """Test tool allowlist initialization for different session types."""
    
    def test_initialize_main_session_allowlist(self, mock_pool):
        """Main sessions should get full tool access by default."""
        tool_allowlist = ToolAllowlist(mock_pool)
        
        allowlist, denylist = tool_allowlist.initialize_allowlist(
            channel_id="slack-main",
            user_id="user123",
            session_type="main",
        )
        
        assert allowlist == ["*"]
        assert denylist == []
    
    def test_initialize_group_session_allowlist(self, mock_pool):
        """Group sessions should get restricted tool access by default."""
        tool_allowlist = ToolAllowlist(mock_pool)
        
        allowlist, denylist = tool_allowlist.initialize_allowlist(
            channel_id="telegram-bot1",
            user_id="user456",
            session_type="group",
        )
        
        # Group sessions have limited tools
        assert "*" not in allowlist
        assert "web_search" in allowlist
        assert "retrieve_relevant_documents" in allowlist
        assert denylist == []
    
    def test_initialize_webhook_session_allowlist(self, mock_pool):
        """Webhook sessions should get minimal tool access by default."""
        tool_allowlist = ToolAllowlist(mock_pool)
        
        allowlist, denylist = tool_allowlist.initialize_allowlist(
            channel_id="discord-main",
            user_id="webhook_user",
            session_type="webhook",
        )
        
        # Webhook sessions have minimal tools
        assert "*" not in allowlist
        assert "web_search" in allowlist
        assert "retrieve_relevant_documents" in allowlist
        assert "list_documents" in allowlist
        assert denylist == []


class TestToolAllowlistDynamicUpdates:
    """Test dynamic updates to tool allowlists."""
    
    @pytest.mark.asyncio
    async def test_update_session_allowlist(self, mock_pool):
        """Updating session allowlist should persist to database."""
        session = Session(
            pool=mock_pool,
            session_id="session123",
            channel_id="slack-main",
            user_id="user123",
            chat_id="dm",
            session_type="main",
            tool_allowlist=["*"],
            tool_denylist=[],
        )
        
        # Update allowlist
        new_allowlist = ["web_*", "list_*"]
        new_denylist = ["execute_*"]
        
        await session.update_tool_allowlist(new_allowlist, new_denylist)
        
        # Verify local state updated
        assert session.tool_allowlist == new_allowlist
        assert session.tool_denylist == new_denylist
        
        # Verify database update was called
        # (db_sessions.update_session_tool_allowlist is called internally)
    
    def test_updated_allowlist_affects_permissions(self, mock_pool):
        """Updated allowlist should immediately affect tool permissions."""
        session = Session(
            pool=mock_pool,
            session_id="session123",
            channel_id="slack-main",
            user_id="user123",
            chat_id="dm",
            session_type="main",
            tool_allowlist=["*"],
            tool_denylist=[],
        )
        
        # Initially all tools allowed
        assert session.is_tool_allowed("execute_code")
        
        # Update allowlist to restrict tools
        session.tool_allowlist = ["web_*"]
        session.tool_denylist = []
        
        # Now execute_code should be blocked
        assert not session.is_tool_allowed("execute_code")
        assert session.is_tool_allowed("web_search")


class TestToolAllowlistAuditLog:
    """Test audit logging for tool access attempts."""
    
    @pytest.mark.asyncio
    async def test_audit_log_includes_all_fields(self, mock_pool):
        """Audit log should include session_id, tool_name, user_id, channel_id, access_granted."""
        tool_allowlist = ToolAllowlist(mock_pool)
        
        await tool_allowlist.log_blocked_tool(
            session_id="session123",
            tool_name="execute_code",
            user_id="user456",
            channel_id="slack-main",
        )
        
        # Verify database insert
        conn = await mock_pool.acquire().__aenter__()
        conn.execute.assert_called_once()
        
        call_args = conn.execute.call_args
        sql = call_args[0][0]
        params = call_args[0][1:]
        
        assert "INSERT INTO tool_access_log" in sql
        assert params[0] == "session123"
        assert params[1] == "execute_code"
        assert params[2] == "user456"
        assert params[3] == "slack-main"
        assert params[4] is False  # access_granted
    
    @pytest.mark.asyncio
    async def test_audit_log_handles_missing_optional_fields(self, mock_pool):
        """Audit log should work with minimal required fields."""
        tool_allowlist = ToolAllowlist(mock_pool)
        
        await tool_allowlist.log_blocked_tool(
            session_id="session123",
            tool_name="execute_code",
        )
        
        # Verify database insert with None for optional fields
        conn = await mock_pool.acquire().__aenter__()
        conn.execute.assert_called_once()
        
        call_args = conn.execute.call_args
        params = call_args[0][1:]
        
        assert params[0] == "session123"
        assert params[1] == "execute_code"
        assert params[2] is None  # user_id
        assert params[3] is None  # channel_id


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
