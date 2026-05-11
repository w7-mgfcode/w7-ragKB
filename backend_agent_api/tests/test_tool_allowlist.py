"""Unit tests for tool allowlist functionality.

Tests cover:
- Wildcard pattern matching ("read_*", "web_*", "*")
- Denylist precedence over allowlist
- Dynamic allowlist updates
- Audit logging for blocked tools
- Integration with Session class
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tool_allowlist import ToolAllowlist


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


@pytest.fixture
def tool_allowlist(mock_pool):
    """Create a ToolAllowlist instance with mock pool."""
    return ToolAllowlist(mock_pool)


class TestToolAllowlistInitialization:
    """Test tool allowlist initialization based on session context."""
    
    def test_initialize_main_session(self, tool_allowlist):
        """Main sessions should allow all tools by default."""
        allowlist, denylist = tool_allowlist.initialize_allowlist(
            channel_id="slack-main",
            user_id="user123",
            session_type="main",
        )
        
        assert allowlist == ["*"]
        assert denylist == []
    
    def test_initialize_group_session(self, tool_allowlist):
        """Group sessions should have limited tools by default."""
        allowlist, denylist = tool_allowlist.initialize_allowlist(
            channel_id="telegram-bot1",
            user_id="user456",
            session_type="group",
        )
        
        # Group sessions have restricted tools
        assert "*" not in allowlist
        assert "web_search" in allowlist
        assert "retrieve_relevant_documents" in allowlist
        assert denylist == []
    
    def test_initialize_webhook_session(self, tool_allowlist):
        """Webhook sessions should have read-only tools by default."""
        allowlist, denylist = tool_allowlist.initialize_allowlist(
            channel_id="discord-main",
            user_id="user789",
            session_type="webhook",
        )
        
        # Webhook sessions have minimal tools
        assert "*" not in allowlist
        assert "web_search" in allowlist
        assert "retrieve_relevant_documents" in allowlist
        assert "list_documents" in allowlist
        assert denylist == []
    
    def test_initialize_unknown_session_type(self, tool_allowlist):
        """Unknown session types should default to all tools allowed."""
        allowlist, denylist = tool_allowlist.initialize_allowlist(
            channel_id="slack-main",
            user_id="user123",
            session_type="unknown_type",
        )
        
        assert allowlist == ["*"]
        assert denylist == []


class TestWildcardPatternMatching:
    """Test wildcard pattern matching for tool names."""
    
    def test_wildcard_all_tools(self, tool_allowlist):
        """Wildcard '*' should match all tools."""
        allowlist = ["*"]
        denylist = []
        
        assert tool_allowlist.is_tool_allowed("web_search", allowlist, denylist)
        assert tool_allowlist.is_tool_allowed("execute_code", allowlist, denylist)
        assert tool_allowlist.is_tool_allowed("browser_navigate", allowlist, denylist)
        assert tool_allowlist.is_tool_allowed("any_tool_name", allowlist, denylist)
    
    def test_wildcard_prefix_matching(self, tool_allowlist):
        """Pattern 'read_*' should match all tools starting with 'read_'."""
        allowlist = ["read_*"]
        denylist = []
        
        assert tool_allowlist.is_tool_allowed("read_file", allowlist, denylist)
        assert tool_allowlist.is_tool_allowed("read_document", allowlist, denylist)
        assert not tool_allowlist.is_tool_allowed("write_file", allowlist, denylist)
        assert not tool_allowlist.is_tool_allowed("web_search", allowlist, denylist)
    
    def test_wildcard_multiple_patterns(self, tool_allowlist):
        """Multiple patterns should all be checked."""
        allowlist = ["web_*", "browser_*", "list_*"]
        denylist = []
        
        assert tool_allowlist.is_tool_allowed("web_search", allowlist, denylist)
        assert tool_allowlist.is_tool_allowed("browser_navigate", allowlist, denylist)
        assert tool_allowlist.is_tool_allowed("list_documents", allowlist, denylist)
        assert not tool_allowlist.is_tool_allowed("execute_code", allowlist, denylist)
    
    def test_exact_tool_name_matching(self, tool_allowlist):
        """Exact tool names should match without wildcards."""
        allowlist = ["web_search", "list_documents", "execute_sql_query"]
        denylist = []
        
        assert tool_allowlist.is_tool_allowed("web_search", allowlist, denylist)
        assert tool_allowlist.is_tool_allowed("list_documents", allowlist, denylist)
        assert tool_allowlist.is_tool_allowed("execute_sql_query", allowlist, denylist)
        assert not tool_allowlist.is_tool_allowed("execute_code", allowlist, denylist)
    
    def test_empty_allowlist_blocks_all(self, tool_allowlist):
        """Empty allowlist should block all tools."""
        allowlist = []
        denylist = []
        
        assert not tool_allowlist.is_tool_allowed("web_search", allowlist, denylist)
        assert not tool_allowlist.is_tool_allowed("any_tool", allowlist, denylist)


class TestDenylistPrecedence:
    """Test that denylist takes precedence over allowlist."""
    
    def test_denylist_blocks_wildcard_allowlist(self, tool_allowlist):
        """Denylist should block tools even with wildcard allowlist."""
        allowlist = ["*"]
        denylist = ["execute_*"]
        
        assert tool_allowlist.is_tool_allowed("web_search", allowlist, denylist)
        assert tool_allowlist.is_tool_allowed("list_documents", allowlist, denylist)
        assert not tool_allowlist.is_tool_allowed("execute_code", allowlist, denylist)
        assert not tool_allowlist.is_tool_allowed("execute_sql_query", allowlist, denylist)
    
    def test_denylist_blocks_specific_tools(self, tool_allowlist):
        """Denylist should block specific tools in allowlist."""
        allowlist = ["web_search", "execute_code", "list_documents"]
        denylist = ["execute_code"]
        
        assert tool_allowlist.is_tool_allowed("web_search", allowlist, denylist)
        assert tool_allowlist.is_tool_allowed("list_documents", allowlist, denylist)
        assert not tool_allowlist.is_tool_allowed("execute_code", allowlist, denylist)
    
    def test_denylist_with_wildcards(self, tool_allowlist):
        """Denylist wildcards should block matching tools."""
        allowlist = ["*"]
        denylist = ["browser_*", "execute_*"]
        
        assert tool_allowlist.is_tool_allowed("web_search", allowlist, denylist)
        assert not tool_allowlist.is_tool_allowed("browser_navigate", allowlist, denylist)
        assert not tool_allowlist.is_tool_allowed("browser_click", allowlist, denylist)
        assert not tool_allowlist.is_tool_allowed("execute_code", allowlist, denylist)
    
    def test_empty_denylist_allows_all_in_allowlist(self, tool_allowlist):
        """Empty denylist should not block any tools."""
        allowlist = ["*"]
        denylist = []
        
        assert tool_allowlist.is_tool_allowed("execute_code", allowlist, denylist)
        assert tool_allowlist.is_tool_allowed("browser_navigate", allowlist, denylist)


class TestAuditLogging:
    """Test audit logging for blocked tool attempts."""
    
    @pytest.mark.asyncio
    async def test_log_blocked_tool_creates_audit_entry(self, tool_allowlist, mock_pool):
        """Blocked tool attempts should be logged to database."""
        await tool_allowlist.log_blocked_tool(
            session_id="session123",
            tool_name="execute_code",
            user_id="user456",
            channel_id="slack-main",
        )
        
        # Verify database insert was called
        conn = await mock_pool.acquire().__aenter__()
        conn.execute.assert_called_once()
        
        # Check the SQL query
        call_args = conn.execute.call_args
        sql = call_args[0][0]
        assert "INSERT INTO tool_access_log" in sql
        assert "session_id" in sql
        assert "tool_name" in sql
        assert "access_granted" in sql
        
        # Check the parameters
        params = call_args[0][1:]
        assert params[0] == "session123"  # session_id
        assert params[1] == "execute_code"  # tool_name
        assert params[2] == "user456"  # user_id
        assert params[3] == "slack-main"  # channel_id
        assert params[4] is False  # access_granted
    
    @pytest.mark.asyncio
    async def test_log_blocked_tool_handles_db_errors(self, tool_allowlist, mock_pool):
        """Audit logging failures should not raise exceptions."""
        # Make database insert fail
        conn = await mock_pool.acquire().__aenter__()
        conn.execute.side_effect = Exception("Database error")
        
        # Should not raise exception
        await tool_allowlist.log_blocked_tool(
            session_id="session123",
            tool_name="execute_code",
        )
    
    @pytest.mark.asyncio
    async def test_log_blocked_tool_with_minimal_info(self, tool_allowlist, mock_pool):
        """Audit logging should work with minimal information."""
        await tool_allowlist.log_blocked_tool(
            session_id="session123",
            tool_name="execute_code",
        )
        
        # Verify database insert was called
        conn = await mock_pool.acquire().__aenter__()
        conn.execute.assert_called_once()
        
        # Check parameters include None for optional fields
        call_args = conn.execute.call_args
        params = call_args[0][1:]
        assert params[0] == "session123"
        assert params[1] == "execute_code"
        assert params[2] is None  # user_id
        assert params[3] is None  # channel_id


class TestDynamicAllowlistUpdates:
    """Test dynamic updates to tool allowlists for active sessions."""
    
    @pytest.mark.asyncio
    async def test_update_allowlist_only(self, tool_allowlist, mock_pool):
        """Updating allowlist should update database."""
        await tool_allowlist.update_allowlist(
            session_id="session123",
            allowlist=["web_*", "list_*"],
        )
        
        # Verify database update was called
        conn = await mock_pool.acquire().__aenter__()
        conn.execute.assert_called_once()
        
        # Check the SQL query
        call_args = conn.execute.call_args
        sql = call_args[0][0]
        assert "UPDATE sessions" in sql
        assert "tool_allowlist = $1" in sql
        assert "session_id = $2" in sql
        
        # Check parameters
        params = call_args[0][1:]
        assert params[0] == ["web_*", "list_*"]
        assert params[1] == "session123"
    
    @pytest.mark.asyncio
    async def test_update_allowlist_and_denylist(self, tool_allowlist, mock_pool):
        """Updating both allowlist and denylist should update database."""
        await tool_allowlist.update_allowlist(
            session_id="session123",
            allowlist=["*"],
            denylist=["execute_*"],
        )
        
        # Verify database update was called
        conn = await mock_pool.acquire().__aenter__()
        conn.execute.assert_called_once()
        
        # Check the SQL query includes both fields
        call_args = conn.execute.call_args
        sql = call_args[0][0]
        assert "UPDATE sessions" in sql
        assert "tool_allowlist = $1" in sql
        assert "tool_denylist = $2" in sql
        
        # Check parameters
        params = call_args[0][1:]
        assert params[0] == ["*"]
        assert params[1] == ["execute_*"]
        assert params[2] == "session123"
    
    @pytest.mark.asyncio
    async def test_update_allowlist_handles_db_errors(self, tool_allowlist, mock_pool):
        """Update failures should raise exceptions."""
        # Make database update fail
        conn = await mock_pool.acquire().__aenter__()
        conn.execute.side_effect = Exception("Database error")
        
        # Should raise exception
        with pytest.raises(Exception) as exc_info:
            await tool_allowlist.update_allowlist(
                session_id="session123",
                allowlist=["web_*"],
            )
        
        assert "Database error" in str(exc_info.value)


class TestSessionIntegration:
    """Test integration with Session class."""
    
    def test_session_is_tool_allowed_with_wildcards(self):
        """Session.is_tool_allowed should support wildcard patterns."""
        from session import Session
        
        # Create a mock session with wildcard allowlist
        session = Session(
            pool=MagicMock(),
            session_id="session123",
            channel_id="slack-main",
            user_id="user123",
            chat_id="dm",
            session_type="main",
            tool_allowlist=["web_*", "list_*"],
            tool_denylist=[],
        )
        
        assert session.is_tool_allowed("web_search")
        assert session.is_tool_allowed("web_fetch")
        assert session.is_tool_allowed("list_documents")
        assert not session.is_tool_allowed("execute_code")
    
    def test_session_is_tool_allowed_with_denylist(self):
        """Session.is_tool_allowed should respect denylist precedence."""
        from session import Session
        
        # Create a mock session with denylist
        session = Session(
            pool=MagicMock(),
            session_id="session123",
            channel_id="slack-main",
            user_id="user123",
            chat_id="dm",
            session_type="main",
            tool_allowlist=["*"],
            tool_denylist=["execute_*", "browser_*"],
        )
        
        assert session.is_tool_allowed("web_search")
        assert session.is_tool_allowed("list_documents")
        assert not session.is_tool_allowed("execute_code")
        assert not session.is_tool_allowed("execute_sql_query")
        assert not session.is_tool_allowed("browser_navigate")
    
    @pytest.mark.asyncio
    async def test_session_log_blocked_tool(self):
        """Session.log_blocked_tool should create audit log entry."""
        from session import Session
        
        # Create a mock pool
        mock_pool = MagicMock()
        mock_pool.execute = AsyncMock()
        
        # Create session
        session = Session(
            pool=mock_pool,
            session_id="session123",
            channel_id="slack-main",
            user_id="user123",
            chat_id="dm",
            session_type="main",
        )
        
        # Log blocked tool
        await session.log_blocked_tool("execute_code")
        
        # Verify database insert was called
        mock_pool.execute.assert_called_once()
        call_args = mock_pool.execute.call_args
        sql = call_args[0][0]
        assert "INSERT INTO tool_access_log" in sql


class TestToolNameMapping:
    """Test tool name mapping for permission checking."""
    
    def test_tool_name_map_completeness(self):
        """Tool name map should include all agent tools."""
        from agent_tool_filter import TOOL_NAME_MAP
        
        # Check that common tools are mapped
        assert "web_search" in TOOL_NAME_MAP
        assert "execute_code" in TOOL_NAME_MAP
        assert "list_sessions" in TOOL_NAME_MAP
        assert "navigate_browser" in TOOL_NAME_MAP
    
    def test_get_tool_permission_name(self):
        """get_tool_permission_name should return correct permission names."""
        from agent_tool_filter import get_tool_permission_name
        
        assert get_tool_permission_name("web_search") == "web_search"
        assert get_tool_permission_name("list_sessions") == "sessions_list"
        assert get_tool_permission_name("navigate_browser") == "browser_navigate"
        
        # Unknown tools should return the original name
        assert get_tool_permission_name("unknown_tool") == "unknown_tool"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
