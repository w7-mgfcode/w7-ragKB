"""Unit tests for session tools.

Tests the session tools implementation including:
- sessions_list: List accessible sessions
- sessions_history: Retrieve message history
- sessions_send: Send inter-session messages
- Permission checks and access control
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from typing import Any, Dict, List

from tools.session_tools import (
    sessions_list,
    sessions_history,
    sessions_send,
    can_access_session,
    PermissionError,
    SessionNotFoundError,
)


class MockSession:
    """Mock Session object for testing."""
    
    def __init__(
        self,
        session_id: str,
        channel_id: str,
        user_id: str,
        chat_id: str,
        session_type: str = "main",
        message_count: int = 0,
        session_tools_enabled: bool = True,
        created_at: float = 1234567890.0,
        last_activity_at: float = 1234567890.0,
    ):
        self.session_id = session_id
        self.channel_id = channel_id
        self.user_id = user_id
        self.chat_id = chat_id
        self.session_type = session_type
        self.message_count = message_count
        self.session_tools_enabled = session_tools_enabled
        self.created_at = created_at
        self.last_activity_at = last_activity_at
    
    async def get_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Mock get_history method."""
        return [
            {
                "role": "user",
                "content": "Hello",
                "created_at": MagicMock(timestamp=lambda: 1234567890.0),
                "metadata": {},
            },
            {
                "role": "assistant",
                "content": "Hi there!",
                "created_at": MagicMock(timestamp=lambda: 1234567891.0),
                "metadata": {},
            },
        ][:limit]
    
    async def add_message(
        self,
        role: str,
        content: str,
        metadata: Dict[str, Any] = None,
    ) -> None:
        """Mock add_message method."""
        pass


class MockSessionManager:
    """Mock SessionManager for testing."""
    
    def __init__(self):
        self.sessions = {}
    
    def add_session(self, session: MockSession) -> None:
        """Add a session to the mock manager."""
        self.sessions[session.session_id] = session
    
    async def get_session(self, session_id: str) -> MockSession:
        """Get a session by ID."""
        return self.sessions.get(session_id)
    
    async def list_sessions(self, include_archived: bool = False) -> List[MockSession]:
        """List all sessions."""
        return list(self.sessions.values())


class MockRunContext:
    """Mock RunContext for testing."""
    
    def __init__(self, session_manager: MockSessionManager, session_id: str):
        self.deps = MagicMock()
        self.deps.session_manager = session_manager
        self.deps.session_id = session_id


@pytest.mark.asyncio
async def test_can_access_session_same_session():
    """Test that a session can always access itself."""
    session_manager = MockSessionManager()
    session = MockSession("session1", "slack", "user1", "dm1")
    session_manager.add_session(session)
    
    result = await can_access_session(session_manager, "session1", "session1")
    assert result is True


@pytest.mark.asyncio
async def test_can_access_session_same_user():
    """Test that sessions from the same user can access each other."""
    session_manager = MockSessionManager()
    session1 = MockSession("session1", "slack", "user1", "dm1")
    session2 = MockSession("session2", "telegram", "user1", "dm2")
    session_manager.add_session(session1)
    session_manager.add_session(session2)
    
    result = await can_access_session(session_manager, "session1", "session2")
    assert result is True


@pytest.mark.asyncio
async def test_can_access_session_different_user():
    """Test that sessions from different users cannot access each other."""
    session_manager = MockSessionManager()
    session1 = MockSession("session1", "slack", "user1", "dm1")
    session2 = MockSession("session2", "telegram", "user2", "dm2")
    session_manager.add_session(session1)
    session_manager.add_session(session2)
    
    result = await can_access_session(session_manager, "session1", "session2")
    assert result is False


@pytest.mark.asyncio
async def test_sessions_list_success():
    """Test listing accessible sessions."""
    session_manager = MockSessionManager()
    session1 = MockSession("session1", "slack", "user1", "dm1", message_count=5)
    session2 = MockSession("session2", "telegram", "user1", "dm2", message_count=10)
    session_manager.add_session(session1)
    session_manager.add_session(session2)
    
    ctx = MockRunContext(session_manager, "session1")
    
    result = await sessions_list(ctx)
    
    assert len(result) == 2
    assert result[0]["session_id"] == "session1"
    assert result[0]["message_count"] == 5
    assert result[1]["session_id"] == "session2"
    assert result[1]["message_count"] == 10


@pytest.mark.asyncio
async def test_sessions_list_permission_denied():
    """Test that sessions_list fails when session_tools_enabled is False."""
    session_manager = MockSessionManager()
    session = MockSession("session1", "slack", "user1", "dm1", session_tools_enabled=False)
    session_manager.add_session(session)
    
    ctx = MockRunContext(session_manager, "session1")
    
    with pytest.raises(PermissionError) as exc_info:
        await sessions_list(ctx)
    
    assert "not enabled" in str(exc_info.value)


@pytest.mark.asyncio
async def test_sessions_history_success():
    """Test retrieving message history from another session."""
    session_manager = MockSessionManager()
    session1 = MockSession("session1", "slack", "user1", "dm1")
    session2 = MockSession("session2", "telegram", "user1", "dm2")
    session_manager.add_session(session1)
    session_manager.add_session(session2)
    
    ctx = MockRunContext(session_manager, "session1")
    
    result = await sessions_history(ctx, "session2", limit=10)
    
    assert len(result) == 2
    assert result[0]["role"] == "user"
    assert result[0]["content"] == "Hello"
    assert result[1]["role"] == "assistant"
    assert result[1]["content"] == "Hi there!"


@pytest.mark.asyncio
async def test_sessions_history_permission_denied():
    """Test that sessions_history fails when session_tools_enabled is False."""
    session_manager = MockSessionManager()
    session1 = MockSession("session1", "slack", "user1", "dm1", session_tools_enabled=False)
    session2 = MockSession("session2", "telegram", "user1", "dm2")
    session_manager.add_session(session1)
    session_manager.add_session(session2)
    
    ctx = MockRunContext(session_manager, "session1")
    
    with pytest.raises(PermissionError) as exc_info:
        await sessions_history(ctx, "session2")
    
    assert "not enabled" in str(exc_info.value)


@pytest.mark.asyncio
async def test_sessions_history_access_denied():
    """Test that sessions_history fails when accessing another user's session."""
    session_manager = MockSessionManager()
    session1 = MockSession("session1", "slack", "user1", "dm1")
    session2 = MockSession("session2", "telegram", "user2", "dm2")
    session_manager.add_session(session1)
    session_manager.add_session(session2)
    
    ctx = MockRunContext(session_manager, "session1")
    
    with pytest.raises(PermissionError) as exc_info:
        await sessions_history(ctx, "session2")
    
    assert "do not have permission" in str(exc_info.value)


@pytest.mark.asyncio
async def test_sessions_history_session_not_found():
    """Test that sessions_history fails when target session doesn't exist."""
    session_manager = MockSessionManager()
    session1 = MockSession("session1", "slack", "user1", "dm1")
    session_manager.add_session(session1)
    
    ctx = MockRunContext(session_manager, "session1")
    
    with pytest.raises(SessionNotFoundError) as exc_info:
        await sessions_history(ctx, "nonexistent")
    
    assert "not found" in str(exc_info.value)


@pytest.mark.asyncio
async def test_sessions_send_success():
    """Test sending a message to another session."""
    session_manager = MockSessionManager()
    session1 = MockSession("session1", "slack", "user1", "dm1")
    session2 = MockSession("session2", "telegram", "user1", "dm2")
    session_manager.add_session(session1)
    session_manager.add_session(session2)
    
    ctx = MockRunContext(session_manager, "session1")
    
    result = await sessions_send(ctx, "session2", "Test message")
    
    assert result["status"] == "delivered"
    assert result["session_id"] == "session2"
    assert result["message_length"] == 12


@pytest.mark.asyncio
async def test_sessions_send_permission_denied():
    """Test that sessions_send fails when session_tools_enabled is False."""
    session_manager = MockSessionManager()
    session1 = MockSession("session1", "slack", "user1", "dm1", session_tools_enabled=False)
    session2 = MockSession("session2", "telegram", "user1", "dm2")
    session_manager.add_session(session1)
    session_manager.add_session(session2)
    
    ctx = MockRunContext(session_manager, "session1")
    
    with pytest.raises(PermissionError) as exc_info:
        await sessions_send(ctx, "session2", "Test message")
    
    assert "not enabled" in str(exc_info.value)


@pytest.mark.asyncio
async def test_sessions_send_access_denied():
    """Test that sessions_send fails when accessing another user's session."""
    session_manager = MockSessionManager()
    session1 = MockSession("session1", "slack", "user1", "dm1")
    session2 = MockSession("session2", "telegram", "user2", "dm2")
    session_manager.add_session(session1)
    session_manager.add_session(session2)
    
    ctx = MockRunContext(session_manager, "session1")
    
    with pytest.raises(PermissionError) as exc_info:
        await sessions_send(ctx, "session2", "Test message")
    
    assert "do not have permission" in str(exc_info.value)


@pytest.mark.asyncio
async def test_sessions_send_empty_message():
    """Test that sessions_send fails with empty message."""
    session_manager = MockSessionManager()
    session1 = MockSession("session1", "slack", "user1", "dm1")
    session2 = MockSession("session2", "telegram", "user1", "dm2")
    session_manager.add_session(session1)
    session_manager.add_session(session2)
    
    ctx = MockRunContext(session_manager, "session1")
    
    with pytest.raises(ValueError) as exc_info:
        await sessions_send(ctx, "session2", "")
    
    assert "cannot be empty" in str(exc_info.value)


@pytest.mark.asyncio
async def test_sessions_history_limit_validation():
    """Test that sessions_history validates and clamps the limit parameter."""
    session_manager = MockSessionManager()
    session1 = MockSession("session1", "slack", "user1", "dm1")
    session2 = MockSession("session2", "telegram", "user1", "dm2")
    session_manager.add_session(session1)
    session_manager.add_session(session2)
    
    ctx = MockRunContext(session_manager, "session1")
    
    # Test with limit < 1 (should default to 10)
    result = await sessions_history(ctx, "session2", limit=0)
    assert len(result) <= 10
    
    # Test with limit > 100 (should clamp to 100)
    result = await sessions_history(ctx, "session2", limit=200)
    assert len(result) <= 100
