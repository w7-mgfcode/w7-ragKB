"""Integration tests for Session and SessionManager.

These tests verify the complete session management workflow.
"""

import os
import pytest
from db_sessions import generate_session_id


# Skip integration tests if no database is available
pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URI"),
    reason="DATABASE_URI not set, skipping integration tests",
)


class TestSessionIdGeneration:
    """Tests for session_id generation."""
    
    def test_generate_session_id_dm(self):
        """Test generating session_id for DM."""
        session_id = generate_session_id("slack-main", "user123", "dm")
        assert session_id == "slack-main:user123:dm"
    
    def test_generate_session_id_group(self):
        """Test generating session_id for group chat."""
        session_id = generate_session_id("discord-main", "user456", "guild789")
        assert session_id == "discord-main:user456:guild789"
    
    def test_generate_session_id_thread(self):
        """Test generating session_id for thread."""
        session_id = generate_session_id(
            "slack-main",
            "user789",
            "C123",
            "thread456",
        )
        assert session_id == "slack-main:user789:C123:thread456"
    
    def test_session_id_deterministic(self):
        """Test that session_id generation is deterministic."""
        session_id1 = generate_session_id("slack", "user", "chat")
        session_id2 = generate_session_id("slack", "user", "chat")
        assert session_id1 == session_id2
