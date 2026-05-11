"""Unit tests for DM pairing security module.

Tests cover:
- Approval code generation (6-digit, unique)
- Code storage with expiration
- Code validation (valid, invalid, expired)
- User approval flow
- Approval persistence
- Approval revocation
- Integration with SessionManager

Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7
"""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dm_pairing import (
    DEFAULT_APPROVAL_CODE_EXPIRATION_SECONDS,
    DMPairing,
    get_dm_pairing,
    initialize_dm_pairing,
)


@pytest.fixture
def mock_pool():
    """Create a mock database connection pool."""
    pool = MagicMock()
    pool.fetchrow = AsyncMock()
    pool.fetch = AsyncMock()
    pool.execute = AsyncMock()
    return pool


@pytest.fixture
def dm_pairing(mock_pool):
    """Create a DMPairing instance with mock pool."""
    return DMPairing(mock_pool)


@pytest.fixture
def dm_pairing_short_expiry(mock_pool):
    """Create a DMPairing instance with short expiry for testing."""
    return DMPairing(mock_pool, approval_code_expiration_seconds=2)


class TestApprovalCodeGeneration:
    """Test approval code generation."""
    
    def test_generate_approval_code_format(self, dm_pairing):
        """Test that generated codes are 6-digit strings."""
        code = dm_pairing.generate_approval_code()
        
        assert isinstance(code, str)
        assert len(code) == 6
        assert code.isdigit()
    
    def test_generate_approval_code_leading_zeros(self, dm_pairing):
        """Test that codes with leading zeros are properly formatted."""
        # Generate multiple codes to increase chance of getting one with leading zeros
        codes = [dm_pairing.generate_approval_code() for _ in range(100)]
        
        # All should be 6 digits
        assert all(len(code) == 6 for code in codes)
        assert all(code.isdigit() for code in codes)
    
    def test_generate_approval_code_uniqueness(self, dm_pairing):
        """Test that generated codes are reasonably unique."""
        codes = [dm_pairing.generate_approval_code() for _ in range(100)]
        
        # Should have high uniqueness (allow some duplicates due to randomness)
        unique_codes = set(codes)
        assert len(unique_codes) > 90  # At least 90% unique


class TestStoreApprovalCode:
    """Test approval code storage."""
    
    @pytest.mark.asyncio
    async def test_store_approval_code_success(self, dm_pairing, mock_pool):
        """Test successful approval code storage."""
        with patch("dm_pairing.ensure_channel_user", new_callable=AsyncMock) as mock_ensure, \
             patch("dm_pairing.update_channel_user_approval", new_callable=AsyncMock) as mock_update:
            
            code = await dm_pairing.store_approval_code(
                "telegram-bot1",
                "user123",
                "John Doe",
            )
            
            # Should ensure user exists
            mock_ensure.assert_called_once_with(
                mock_pool,
                "telegram-bot1",
                "user123",
                "John Doe",
            )
            
            # Should update approval status
            mock_update.assert_called_once()
            call_args = mock_update.call_args
            
            assert call_args[0][0] == mock_pool
            assert call_args[0][1] == "telegram-bot1"
            assert call_args[0][2] == "user123"
            assert call_args[1]["approved"] is False
            assert call_args[1]["approval_code"] == code
            assert call_args[1]["approval_code_expires_at"] is not None
            
            # Code should be 6 digits
            assert len(code) == 6
            assert code.isdigit()
    
    @pytest.mark.asyncio
    async def test_store_approval_code_expiration_time(self, dm_pairing, mock_pool):
        """Test that expiration time is set correctly."""
        with patch("dm_pairing.ensure_channel_user", new_callable=AsyncMock), \
             patch("dm_pairing.update_channel_user_approval", new_callable=AsyncMock) as mock_update:
            
            before = datetime.now(timezone.utc)
            await dm_pairing.store_approval_code("telegram-bot1", "user123")
            after = datetime.now(timezone.utc)
            
            call_args = mock_update.call_args
            expires_at_str = call_args[1]["approval_code_expires_at"]
            expires_at = datetime.fromisoformat(expires_at_str)
            
            # Should expire in approximately 15 minutes (900 seconds)
            expected_min = before + timedelta(seconds=DEFAULT_APPROVAL_CODE_EXPIRATION_SECONDS)
            expected_max = after + timedelta(seconds=DEFAULT_APPROVAL_CODE_EXPIRATION_SECONDS)
            
            assert expected_min <= expires_at <= expected_max


class TestValidateApprovalCode:
    """Test approval code validation."""
    
    @pytest.mark.asyncio
    async def test_validate_approval_code_success(self, dm_pairing):
        """Test successful code validation."""
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
        
        with patch("dm_pairing.get_channel_user", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {
                "approval_code": "123456",
                "approval_code_expires_at": expires_at,
            }
            
            is_valid = await dm_pairing.validate_approval_code(
                "telegram-bot1",
                "user123",
                "123456",
            )
            
            assert is_valid is True
    
    @pytest.mark.asyncio
    async def test_validate_approval_code_user_not_found(self, dm_pairing):
        """Test validation fails when user not found."""
        with patch("dm_pairing.get_channel_user", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None
            
            is_valid = await dm_pairing.validate_approval_code(
                "telegram-bot1",
                "user123",
                "123456",
            )
            
            assert is_valid is False
    
    @pytest.mark.asyncio
    async def test_validate_approval_code_mismatch(self, dm_pairing):
        """Test validation fails when code doesn't match."""
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
        
        with patch("dm_pairing.get_channel_user", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {
                "approval_code": "123456",
                "approval_code_expires_at": expires_at,
            }
            
            is_valid = await dm_pairing.validate_approval_code(
                "telegram-bot1",
                "user123",
                "654321",  # Wrong code
            )
            
            assert is_valid is False
    
    @pytest.mark.asyncio
    async def test_validate_approval_code_expired(self, dm_pairing):
        """Test validation fails when code is expired."""
        expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)  # Expired
        
        with patch("dm_pairing.get_channel_user", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {
                "approval_code": "123456",
                "approval_code_expires_at": expires_at,
            }
            
            is_valid = await dm_pairing.validate_approval_code(
                "telegram-bot1",
                "user123",
                "123456",
            )
            
            assert is_valid is False
    
    @pytest.mark.asyncio
    async def test_validate_approval_code_no_code_stored(self, dm_pairing):
        """Test validation fails when no code is stored."""
        with patch("dm_pairing.get_channel_user", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {
                "approval_code": None,
                "approval_code_expires_at": None,
            }
            
            is_valid = await dm_pairing.validate_approval_code(
                "telegram-bot1",
                "user123",
                "123456",
            )
            
            assert is_valid is False
    
    @pytest.mark.asyncio
    async def test_validate_approval_code_string_timestamp(self, dm_pairing):
        """Test validation works with string timestamp from database."""
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
        expires_at_str = expires_at.isoformat()
        
        with patch("dm_pairing.get_channel_user", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {
                "approval_code": "123456",
                "approval_code_expires_at": expires_at_str,  # String format
            }
            
            is_valid = await dm_pairing.validate_approval_code(
                "telegram-bot1",
                "user123",
                "123456",
            )
            
            assert is_valid is True


class TestApproveUser:
    """Test user approval."""
    
    @pytest.mark.asyncio
    async def test_approve_user_success(self, dm_pairing, mock_pool):
        """Test successful user approval."""
        with patch("dm_pairing.update_channel_user_approval", new_callable=AsyncMock) as mock_update:
            await dm_pairing.approve_user("telegram-bot1", "user123")
            
            mock_update.assert_called_once_with(
                mock_pool,
                "telegram-bot1",
                "user123",
                approved=True,
                approval_code=None,
                approval_code_expires_at=None,
            )


class TestIsUserApproved:
    """Test checking user approval status."""
    
    @pytest.mark.asyncio
    async def test_is_user_approved_true(self, dm_pairing):
        """Test checking approved user."""
        with patch("dm_pairing.get_channel_user", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {"approved": True}
            
            is_approved = await dm_pairing.is_user_approved("telegram-bot1", "user123")
            
            assert is_approved is True
    
    @pytest.mark.asyncio
    async def test_is_user_approved_false(self, dm_pairing):
        """Test checking unapproved user."""
        with patch("dm_pairing.get_channel_user", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {"approved": False}
            
            is_approved = await dm_pairing.is_user_approved("telegram-bot1", "user123")
            
            assert is_approved is False
    
    @pytest.mark.asyncio
    async def test_is_user_approved_user_not_found(self, dm_pairing):
        """Test checking non-existent user."""
        with patch("dm_pairing.get_channel_user", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None
            
            is_approved = await dm_pairing.is_user_approved("telegram-bot1", "user123")
            
            assert is_approved is False


class TestRevokeApproval:
    """Test approval revocation."""
    
    @pytest.mark.asyncio
    async def test_revoke_approval_success(self, dm_pairing, mock_pool):
        """Test successful approval revocation."""
        with patch("dm_pairing.update_channel_user_approval", new_callable=AsyncMock) as mock_update:
            await dm_pairing.revoke_approval("telegram-bot1", "user123")
            
            mock_update.assert_called_once_with(
                mock_pool,
                "telegram-bot1",
                "user123",
                approved=False,
                approval_code=None,
                approval_code_expires_at=None,
            )


class TestHandleDMPairingFlow:
    """Test the complete DM pairing flow."""
    
    @pytest.mark.asyncio
    async def test_handle_dm_pairing_flow_already_approved(self, dm_pairing):
        """Test flow when user is already approved."""
        with patch.object(dm_pairing, "is_user_approved", new_callable=AsyncMock) as mock_is_approved:
            mock_is_approved.return_value = True
            
            is_approved, code = await dm_pairing.handle_dm_pairing_flow(
                "telegram-bot1",
                "user123",
            )
            
            assert is_approved is True
            assert code is None
    
    @pytest.mark.asyncio
    async def test_handle_dm_pairing_flow_valid_code(self, dm_pairing):
        """Test flow with valid approval code."""
        with patch.object(dm_pairing, "is_user_approved", new_callable=AsyncMock) as mock_is_approved, \
             patch.object(dm_pairing, "validate_approval_code", new_callable=AsyncMock) as mock_validate, \
             patch.object(dm_pairing, "approve_user", new_callable=AsyncMock) as mock_approve:
            
            mock_is_approved.return_value = False
            mock_validate.return_value = True
            
            is_approved, code = await dm_pairing.handle_dm_pairing_flow(
                "telegram-bot1",
                "user123",
                provided_code="123456",
            )
            
            assert is_approved is True
            assert code is None
            mock_approve.assert_called_once_with("telegram-bot1", "user123")
    
    @pytest.mark.asyncio
    async def test_handle_dm_pairing_flow_invalid_code(self, dm_pairing):
        """Test flow with invalid approval code."""
        with patch.object(dm_pairing, "is_user_approved", new_callable=AsyncMock) as mock_is_approved, \
             patch.object(dm_pairing, "validate_approval_code", new_callable=AsyncMock) as mock_validate, \
             patch.object(dm_pairing, "approve_user", new_callable=AsyncMock) as mock_approve:
            
            mock_is_approved.return_value = False
            mock_validate.return_value = False
            
            is_approved, code = await dm_pairing.handle_dm_pairing_flow(
                "telegram-bot1",
                "user123",
                provided_code="999999",
            )
            
            assert is_approved is False
            assert code is None
            mock_approve.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_handle_dm_pairing_flow_generate_code(self, dm_pairing):
        """Test flow when generating new approval code."""
        with patch.object(dm_pairing, "is_user_approved", new_callable=AsyncMock) as mock_is_approved, \
             patch.object(dm_pairing, "store_approval_code", new_callable=AsyncMock) as mock_store:
            
            mock_is_approved.return_value = False
            mock_store.return_value = "123456"
            
            is_approved, code = await dm_pairing.handle_dm_pairing_flow(
                "telegram-bot1",
                "user123",
                "John Doe",
            )
            
            assert is_approved is False
            assert code == "123456"
            mock_store.assert_called_once_with("telegram-bot1", "user123", "John Doe")


class TestGlobalInstance:
    """Test global DM pairing instance management."""
    
    def test_initialize_dm_pairing(self, mock_pool):
        """Test initializing global instance."""
        dm_pairing = initialize_dm_pairing(mock_pool)
        
        assert dm_pairing is not None
        assert isinstance(dm_pairing, DMPairing)
        assert dm_pairing.pool == mock_pool
    
    def test_get_dm_pairing(self, mock_pool):
        """Test getting global instance."""
        initialize_dm_pairing(mock_pool)
        dm_pairing = get_dm_pairing()
        
        assert dm_pairing is not None
        assert isinstance(dm_pairing, DMPairing)
    
    def test_initialize_dm_pairing_custom_expiration(self, mock_pool):
        """Test initializing with custom expiration time."""
        dm_pairing = initialize_dm_pairing(mock_pool, approval_code_expiration_seconds=600)
        
        assert dm_pairing.approval_code_expiration_seconds == 600


class TestCodeExpiration:
    """Test approval code expiration behavior."""
    
    @pytest.mark.asyncio
    async def test_code_expires_after_timeout(self, dm_pairing_short_expiry):
        """Test that codes expire after the configured timeout."""
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=2)
        
        with patch("dm_pairing.get_channel_user", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {
                "approval_code": "123456",
                "approval_code_expires_at": expires_at,
            }
            
            # Should be valid immediately
            is_valid = await dm_pairing_short_expiry.validate_approval_code(
                "telegram-bot1",
                "user123",
                "123456",
            )
            assert is_valid is True
            
            # Wait for expiration
            await asyncio.sleep(3)
            
            # Should be invalid after expiration
            is_valid = await dm_pairing_short_expiry.validate_approval_code(
                "telegram-bot1",
                "user123",
                "123456",
            )
            assert is_valid is False


class TestSessionManagerIntegration:
    """Test integration with SessionManager."""
    
    @pytest.mark.asyncio
    async def test_session_creation_requires_approval(self, mock_pool):
        """Test that Main_Session creation requires approval when dm_policy='pairing'."""
        from session_manager import SessionManager
        
        session_manager = SessionManager(mock_pool)
        
        with patch("dm_pairing.get_dm_pairing") as mock_get_dm_pairing, \
             patch("session_manager.get_or_create_session", new_callable=AsyncMock):
            
            # Mock DM pairing to return unapproved user
            mock_dm_pairing = MagicMock()
            mock_dm_pairing.is_user_approved = AsyncMock(return_value=False)
            mock_get_dm_pairing.return_value = mock_dm_pairing
            
            # Should raise PermissionError
            with pytest.raises(PermissionError) as exc_info:
                await session_manager.create_session(
                    channel_id="telegram-bot1",
                    user_id="user123",
                    chat_id="dm",
                    session_type="main",
                    dm_policy="pairing",
                )
            
            assert "not approved" in str(exc_info.value).lower()
    
    @pytest.mark.asyncio
    async def test_session_creation_allowed_when_approved(self, mock_pool):
        """Test that Main_Session creation succeeds when user is approved."""
        from session_manager import SessionManager
        
        session_manager = SessionManager(mock_pool)
        
        with patch("dm_pairing.get_dm_pairing") as mock_get_dm_pairing, \
             patch("session_manager.generate_session_id") as mock_gen_id, \
             patch("session_manager.get_or_create_session", new_callable=AsyncMock) as mock_get_or_create, \
             patch.object(session_manager, "_session_from_db_row") as mock_from_row:
            
            # Mock DM pairing to return approved user
            mock_dm_pairing = MagicMock()
            mock_dm_pairing.is_user_approved = AsyncMock(return_value=True)
            mock_get_dm_pairing.return_value = mock_dm_pairing
            
            # Mock session creation
            mock_gen_id.return_value = "telegram-bot1:user123:dm"
            mock_get_or_create.return_value = {
                "session_id": "telegram-bot1:user123:dm",
                "channel_id": "telegram-bot1",
                "user_id": "user123",
                "chat_id": "dm",
                "session_type": "main",
                "activation_mode": "mention",
                "tool_allowlist": ["*"],
                "message_count": 0,
                "token_usage": {},
                "created_at": datetime.now(timezone.utc),
                "last_activity_at": datetime.now(timezone.utc),
            }
            
            mock_session = MagicMock()
            mock_from_row.return_value = mock_session
            
            # Should succeed
            session = await session_manager.create_session(
                channel_id="telegram-bot1",
                user_id="user123",
                chat_id="dm",
                session_type="main",
                dm_policy="pairing",
            )
            
            assert session == mock_session
    
    @pytest.mark.asyncio
    async def test_session_creation_open_policy_no_check(self, mock_pool):
        """Test that Main_Session creation with dm_policy='open' doesn't check approval."""
        from session_manager import SessionManager
        
        session_manager = SessionManager(mock_pool)
        
        with patch("dm_pairing.get_dm_pairing") as mock_get_dm_pairing, \
             patch("session_manager.generate_session_id") as mock_gen_id, \
             patch("session_manager.get_or_create_session", new_callable=AsyncMock) as mock_get_or_create, \
             patch.object(session_manager, "_session_from_db_row") as mock_from_row:
            
            # Mock DM pairing
            mock_dm_pairing = MagicMock()
            mock_dm_pairing.is_user_approved = AsyncMock(return_value=False)
            mock_get_dm_pairing.return_value = mock_dm_pairing
            
            # Mock session creation
            mock_gen_id.return_value = "telegram-bot1:user123:dm"
            mock_get_or_create.return_value = {
                "session_id": "telegram-bot1:user123:dm",
                "channel_id": "telegram-bot1",
                "user_id": "user123",
                "chat_id": "dm",
                "session_type": "main",
                "activation_mode": "mention",
                "tool_allowlist": ["*"],
                "message_count": 0,
                "token_usage": {},
                "created_at": datetime.now(timezone.utc),
                "last_activity_at": datetime.now(timezone.utc),
            }
            
            mock_session = MagicMock()
            mock_from_row.return_value = mock_session
            
            # Should succeed without checking approval
            session = await session_manager.create_session(
                channel_id="telegram-bot1",
                user_id="user123",
                chat_id="dm",
                session_type="main",
                dm_policy="open",  # Open policy
            )
            
            assert session == mock_session
            # Should not call is_user_approved
            mock_dm_pairing.is_user_approved.assert_not_called()
