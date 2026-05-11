"""Unit tests for SessionManager class.

Tests cover:
- Session creation and retrieval (idempotent)
- Session lifecycle (create, archive, delete)
- Session listing and filtering
- Memory limits enforcement
- Inactive session cleanup
- Metrics collection
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from session import Session
from session_manager import SessionManager


@pytest.fixture
def mock_pool():
    """Create a mock database connection pool."""
    pool = MagicMock()
    return pool


@pytest.fixture
def session_manager(mock_pool):
    """Create a SessionManager instance for testing."""
    return SessionManager(mock_pool)


@pytest.fixture
def sample_db_row():
    """Create a sample database row for session."""
    return {
        "session_id": "slack-main:user123:dm",
        "channel_id": "slack-main",
        "user_id": "user123",
        "chat_id": "dm",
        "session_type": "main",
        "activation_mode": "mention",
        "tool_allowlist": '["*"]',
        "message_count": 0,
        "token_usage": "{}",
        "created_at": datetime.now(timezone.utc),
        "last_activity_at": datetime.now(timezone.utc),
    }


class TestSessionManagerLifecycle:
    """Tests for SessionManager start/stop lifecycle."""
    
    @pytest.mark.asyncio
    async def test_start_session_manager(self, session_manager):
        """Test starting the session manager."""
        await session_manager.start()
        
        assert session_manager._running is True
        assert session_manager._cleanup_task is not None
        
        # Clean up
        await session_manager.stop()
    
    @pytest.mark.asyncio
    async def test_stop_session_manager(self, session_manager):
        """Test stopping the session manager."""
        await session_manager.start()
        await session_manager.stop()
        
        assert session_manager._running is False
    
    @pytest.mark.asyncio
    async def test_start_already_running(self, session_manager):
        """Test that starting an already running manager is a no-op."""
        await session_manager.start()
        
        # Try to start again
        await session_manager.start()
        
        assert session_manager._running is True
        
        # Clean up
        await session_manager.stop()


class TestSessionCreation:
    """Tests for session creation."""
    
    @pytest.mark.asyncio
    async def test_create_session(self, session_manager, sample_db_row):
        """Test creating a new session."""
        with patch("session_manager.get_or_create_session", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = sample_db_row
            
            session = await session_manager.create_session(
                channel_id="slack-main",
                user_id="user123",
                chat_id="dm",
                session_type="main",
            )
            
            assert isinstance(session, Session)
            assert session.session_id == "slack-main:user123:dm"
            assert session.channel_id == "slack-main"
            assert session.user_id == "user123"
            
            # Should be added to cache
            assert "slack-main:user123:dm" in session_manager.sessions
    
    @pytest.mark.asyncio
    async def test_create_session_idempotent(self, session_manager, sample_db_row):
        """Test that creating the same session twice returns the same instance."""
        with patch("session_manager.get_or_create_session", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = sample_db_row
            
            session1 = await session_manager.create_session(
                channel_id="slack-main",
                user_id="user123",
                chat_id="dm",
                session_type="main",
            )
            
            # Create again with same parameters
            session2 = await session_manager.create_session(
                channel_id="slack-main",
                user_id="user123",
                chat_id="dm",
                session_type="main",
            )
            
            # Should return the same instance from cache
            assert session1 is session2
            
            # Database should only be called once
            assert mock_create.call_count == 1
    
    @pytest.mark.asyncio
    async def test_create_session_with_thread(self, session_manager, sample_db_row):
        """Test creating a session with thread_id."""
        sample_db_row["session_id"] = "slack-main:user123:C123:thread456"
        
        with patch("session_manager.get_or_create_session", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = sample_db_row
            
            session = await session_manager.create_session(
                channel_id="slack-main",
                user_id="user123",
                chat_id="C123",
                thread_id="thread456",
                session_type="group",
            )
            
            assert session.session_id == "slack-main:user123:C123:thread456"


class TestSessionRetrieval:
    """Tests for session retrieval."""
    
    @pytest.mark.asyncio
    async def test_get_session_from_cache(self, session_manager, sample_db_row):
        """Test retrieving a session from cache."""
        # Add session to cache
        with patch("session_manager.get_or_create_session", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = sample_db_row
            
            session1 = await session_manager.create_session(
                channel_id="slack-main",
                user_id="user123",
                chat_id="dm",
                session_type="main",
            )
        
        # Retrieve from cache (no database call)
        with patch("session_manager.get_session", new_callable=AsyncMock) as mock_get:
            session2 = await session_manager.get_session("slack-main:user123:dm")
            
            assert session2 is session1
            mock_get.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_get_session_from_database(self, session_manager, sample_db_row):
        """Test retrieving a session from database when not in cache."""
        with patch("session_manager.get_session", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = sample_db_row
            
            session = await session_manager.get_session("slack-main:user123:dm")
            
            assert isinstance(session, Session)
            assert session.session_id == "slack-main:user123:dm"
            
            # Should be added to cache
            assert "slack-main:user123:dm" in session_manager.sessions
    
    @pytest.mark.asyncio
    async def test_get_session_not_found(self, session_manager):
        """Test retrieving a non-existent session."""
        with patch("session_manager.get_session", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None
            
            session = await session_manager.get_session("nonexistent")
            
            assert session is None
    
    @pytest.mark.asyncio
    async def test_get_or_create_session_existing(self, session_manager, sample_db_row):
        """Test get_or_create returns existing session."""
        with patch("session_manager.get_or_create_session", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = sample_db_row
            
            # Create session
            session1 = await session_manager.get_or_create_session(
                channel_id="slack-main",
                user_id="user123",
                chat_id="dm",
            )
            
            # Get or create again
            session2 = await session_manager.get_or_create_session(
                channel_id="slack-main",
                user_id="user123",
                chat_id="dm",
            )
            
            assert session1 is session2


class TestSessionListing:
    """Tests for session listing and filtering."""
    
    @pytest.mark.asyncio
    async def test_list_all_sessions(self, session_manager, sample_db_row):
        """Test listing all sessions."""
        with patch("session_manager.list_sessions", new_callable=AsyncMock) as mock_list:
            mock_list.return_value = [sample_db_row]
            
            sessions = await session_manager.list_sessions()
            
            assert len(sessions) == 1
            assert isinstance(sessions[0], Session)
    
    @pytest.mark.asyncio
    async def test_list_sessions_by_channel(self, session_manager, sample_db_row):
        """Test listing sessions filtered by channel."""
        with patch("session_manager.list_sessions", new_callable=AsyncMock) as mock_list:
            mock_list.return_value = [sample_db_row]
            
            sessions = await session_manager.list_sessions(channel_id="slack-main")
            
            assert len(sessions) == 1
            mock_list.assert_called_once_with(
                session_manager.pool,
                "slack-main",
                None,
                None,
                False,
            )
    
    @pytest.mark.asyncio
    async def test_list_sessions_by_user(self, session_manager, sample_db_row):
        """Test listing sessions filtered by user."""
        with patch("session_manager.list_sessions", new_callable=AsyncMock) as mock_list:
            mock_list.return_value = [sample_db_row]
            
            sessions = await session_manager.list_sessions(user_id="user123")
            
            assert len(sessions) == 1
    
    @pytest.mark.asyncio
    async def test_list_sessions_include_archived(self, session_manager, sample_db_row):
        """Test listing sessions including archived ones."""
        with patch("session_manager.list_sessions", new_callable=AsyncMock) as mock_list:
            mock_list.return_value = [sample_db_row]
            
            sessions = await session_manager.list_sessions(include_archived=True)
            
            assert len(sessions) == 1
            mock_list.assert_called_once_with(
                session_manager.pool,
                None,
                None,
                None,
                True,
            )


class TestSessionArchival:
    """Tests for session archival and deletion."""
    
    @pytest.mark.asyncio
    async def test_archive_session(self, session_manager, sample_db_row):
        """Test archiving a session."""
        # Add session to cache
        with patch("session_manager.get_or_create_session", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = sample_db_row
            
            await session_manager.create_session(
                channel_id="slack-main",
                user_id="user123",
                chat_id="dm",
                session_type="main",
            )
        
        # Archive the session
        with patch("session_manager.archive_session", new_callable=AsyncMock) as mock_archive:
            await session_manager.archive_session("slack-main:user123:dm")
            
            # Should be removed from cache
            assert "slack-main:user123:dm" not in session_manager.sessions
    
    @pytest.mark.asyncio
    async def test_delete_session(self, session_manager, sample_db_row):
        """Test deleting a session."""
        # Add session to cache
        with patch("session_manager.get_or_create_session", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = sample_db_row
            
            await session_manager.create_session(
                channel_id="slack-main",
                user_id="user123",
                chat_id="dm",
                session_type="main",
            )
        
        # Delete the session
        with patch("session_manager.delete_session", new_callable=AsyncMock) as mock_delete:
            await session_manager.delete_session("slack-main:user123:dm")
            
            # Should be removed from cache
            assert "slack-main:user123:dm" not in session_manager.sessions


class TestMemoryManagement:
    """Tests for memory limits and cleanup."""
    
    @pytest.mark.asyncio
    async def test_enforce_memory_limits(self, session_manager, sample_db_row):
        """Test that memory limits are enforced."""
        # Mock MAX_ACTIVE_SESSIONS to a small number
        with patch("session_manager.MAX_ACTIVE_SESSIONS", 5):
            # Create 10 sessions
            with patch("session_manager.get_or_create_session", new_callable=AsyncMock) as mock_create, \
                 patch("session_manager.archive_session", new_callable=AsyncMock) as mock_archive:
                
                for i in range(10):
                    row = sample_db_row.copy()
                    row["session_id"] = f"slack-main:user{i}:dm"
                    mock_create.return_value = row
                    
                    await session_manager.create_session(
                        channel_id="slack-main",
                        user_id=f"user{i}",
                        chat_id="dm",
                        session_type="main",
                    )
                
                # Should have archived 5 sessions (10 - 5 = 5)
                assert mock_archive.call_count == 5
    
    @pytest.mark.asyncio
    async def test_cleanup_inactive_sessions(self, session_manager, sample_db_row):
        """Test that inactive sessions are cleaned up."""
        import time
        
        # Create a session with old last_activity_at
        with patch("session_manager.get_or_create_session", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = sample_db_row
            
            session = await session_manager.create_session(
                channel_id="slack-main",
                user_id="user123",
                chat_id="dm",
                session_type="main",
            )
            
            # Set last_activity_at to 2 hours ago
            session.last_activity_at = time.time() - 7200
        
        # Run cleanup
        with patch("session_manager.archive_session", new_callable=AsyncMock) as mock_archive:
            await session_manager._cleanup_inactive_sessions()
            
            # Should archive the inactive session
            mock_archive.assert_called_once_with("slack-main:user123:dm")
    
    def test_get_active_session_count(self, session_manager):
        """Test getting active session count."""
        # Add some sessions to cache
        session_manager.sessions = {
            "session1": MagicMock(),
            "session2": MagicMock(),
            "session3": MagicMock(),
        }
        
        assert session_manager.get_active_session_count() == 3


class TestMetrics:
    """Tests for metrics collection."""
    
    def test_get_metrics(self, session_manager):
        """Test getting session manager metrics."""
        # Add some sessions to cache
        session_manager.sessions = {
            "session1": MagicMock(),
            "session2": MagicMock(),
        }
        
        metrics = session_manager.get_metrics()
        
        assert "active_sessions" in metrics
        assert metrics["active_sessions"] == 2
        assert "max_active_sessions" in metrics
        assert "inactive_timeout_seconds" in metrics
        assert "cleanup_interval_seconds" in metrics


class TestSessionFromDbRow:
    """Tests for converting database rows to Session instances."""
    
    def test_session_from_db_row(self, session_manager, sample_db_row):
        """Test creating a Session from a database row."""
        session = session_manager._session_from_db_row(sample_db_row)
        
        assert isinstance(session, Session)
        assert session.session_id == sample_db_row["session_id"]
        assert session.channel_id == sample_db_row["channel_id"]
        assert session.user_id == sample_db_row["user_id"]
    
    def test_session_from_db_row_with_json_fields(self, session_manager, sample_db_row):
        """Test parsing JSON fields from database row."""
        sample_db_row["tool_allowlist"] = '["read_*", "web_*"]'
        sample_db_row["token_usage"] = '{"input_tokens": 100}'
        
        session = session_manager._session_from_db_row(sample_db_row)
        
        assert session.tool_allowlist == ["read_*", "web_*"]
        assert session.token_usage == {"input_tokens": 100}
