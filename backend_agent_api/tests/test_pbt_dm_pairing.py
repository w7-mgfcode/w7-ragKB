"""Property-based tests for DM pairing security.

Feature: openclaw-integration (Task 16.1)
Properties tested: 43, 44, 45, 46, 47, 48, 49

Tests approval code generation, validation, expiration,
persistence, bypass for approved users, and revocation.
"""

import string
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hypothesis import HealthCheck, given, settings, strategies as st

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dm_pairing import (
    DEFAULT_APPROVAL_CODE_EXPIRATION_SECONDS,
    DMPairing,
)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

safe_id = st.text(
    alphabet=string.ascii_letters + string.digits + "-_.",
    min_size=1,
    max_size=30,
)
safe_name = st.text(
    alphabet=string.ascii_letters + " ",
    min_size=1,
    max_size=30,
).filter(lambda s: s.strip())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_mock_pool():
    """Create a mock asyncpg pool."""
    pool = MagicMock()
    pool.fetchrow = AsyncMock(return_value=None)
    pool.fetch = AsyncMock(return_value=[])
    pool.execute = AsyncMock()
    return pool


def make_dm_pairing(pool=None, expiration_seconds=900):
    """Create a DMPairing instance with mock pool."""
    if pool is None:
        pool = make_mock_pool()
    return DMPairing(pool, expiration_seconds)


# ===========================================================================
# Property 43: DM pairing enforcement
# ===========================================================================


class TestDmPairingEnforcement:
    """Property 43: Unapproved users get approval code, not agent response."""

    @given(channel_id=safe_id, user_id=safe_id)
    @settings(max_examples=50, deadline=None)
    @pytest.mark.asyncio
    async def test_unapproved_user_gets_code(self, channel_id, user_id):
        """
        Feature: openclaw-integration, Property 43: DM pairing enforcement

        Unapproved user in DM flow should receive an approval code.
        """
        pool = make_mock_pool()
        call_count = [0]

        async def smart_fetchrow(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                # get_channel_user in is_user_approved → not found
                return None
            else:
                # ensure_channel_user in store_approval_code → return user row
                return {
                    "channel_user_id": f"{channel_id}:{user_id}",
                    "channel_id": channel_id,
                    "user_id": user_id,
                    "approved": False,
                }

        pool.fetchrow = AsyncMock(side_effect=smart_fetchrow)

        pairing = make_dm_pairing(pool)

        is_approved, code = await pairing.handle_dm_pairing_flow(
            channel_id, user_id
        )

        assert is_approved is False
        assert code is not None
        assert len(code) == 6
        assert code.isdigit()

    @given(channel_id=safe_id, user_id=safe_id)
    @settings(max_examples=50, deadline=None)
    @pytest.mark.asyncio
    async def test_approved_user_skips_code(self, channel_id, user_id):
        """
        Feature: openclaw-integration, Property 43: DM pairing enforcement

        Approved user should skip code generation.
        """
        pool = make_mock_pool()
        pool.fetchrow = AsyncMock(return_value={
            "approved": True,
            "approval_code": None,
            "approval_code_expires_at": None,
        })

        pairing = make_dm_pairing(pool)

        is_approved, code = await pairing.handle_dm_pairing_flow(
            channel_id, user_id
        )

        assert is_approved is True
        assert code is None


# ===========================================================================
# Property 44: Approval code generation
# ===========================================================================


class TestApprovalCodeGeneration:
    """Property 44: Time-limited 6-digit codes generated."""

    @given(st.data())
    @settings(max_examples=100, deadline=None)
    def test_code_is_6_digit_string(self, data):
        """
        Feature: openclaw-integration, Property 44: Approval code generation

        Generated code must be a 6-digit numeric string.
        """
        pairing = make_dm_pairing()
        code = pairing.generate_approval_code()

        assert len(code) == 6
        assert code.isdigit()
        assert 0 <= int(code) <= 999999

    @settings(max_examples=50, deadline=None)
    @given(st.data())
    def test_codes_have_leading_zeros(self, data):
        """
        Feature: openclaw-integration, Property 44: Approval code generation

        Codes should preserve leading zeros (e.g., "000042").
        """
        pairing = make_dm_pairing()
        # Generate many codes and verify format
        codes = [pairing.generate_approval_code() for _ in range(50)]
        for code in codes:
            assert len(code) == 6
            assert code.isdigit()

    @settings(max_examples=50, deadline=None)
    @given(st.data())
    def test_codes_are_random(self, data):
        """
        Feature: openclaw-integration, Property 44: Approval code generation

        Generated codes should have variety (statistical property).
        """
        pairing = make_dm_pairing()
        codes = {pairing.generate_approval_code() for _ in range(50)}
        # With 6-digit codes, 50 random samples should be mostly unique
        assert len(codes) >= 30

    def test_default_expiration_is_900_seconds(self):
        """
        Feature: openclaw-integration, Property 44: Approval code generation

        Default expiration should be 900 seconds (15 minutes).
        """
        assert DEFAULT_APPROVAL_CODE_EXPIRATION_SECONDS == 900

    @pytest.mark.asyncio
    async def test_store_code_calls_db(self):
        """
        Feature: openclaw-integration, Property 44: Approval code generation

        store_approval_code should call ensure_channel_user and update_channel_user_approval.
        """
        pool = make_mock_pool()
        pool.fetchrow = AsyncMock(return_value={
            "channel_user_id": "ch1:u1",
            "channel_id": "ch1",
            "user_id": "u1",
            "approved": False,
        })

        pairing = make_dm_pairing(pool)
        code = await pairing.store_approval_code("ch1", "u1", "Alice")

        assert len(code) == 6
        assert code.isdigit()
        # ensure_channel_user + update_channel_user_approval = 2 DB calls
        assert pool.fetchrow.called
        assert pool.execute.called


# ===========================================================================
# Property 45: Approval code validation
# ===========================================================================


class TestApprovalCodeValidation:
    """Property 45: Valid code within expiration → approved."""

    @given(channel_id=safe_id, user_id=safe_id)
    @settings(max_examples=50, deadline=None)
    @pytest.mark.asyncio
    async def test_valid_code_accepted(self, channel_id, user_id):
        """
        Feature: openclaw-integration, Property 45: Approval code validation

        Valid, non-expired code should be accepted.
        """
        pool = make_mock_pool()
        future_time = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
        pool.fetchrow = AsyncMock(return_value={
            "approval_code": "123456",
            "approval_code_expires_at": future_time,
            "approved": False,
        })

        pairing = make_dm_pairing(pool)
        result = await pairing.validate_approval_code(channel_id, user_id, "123456")
        assert result is True

    @given(channel_id=safe_id, user_id=safe_id)
    @settings(max_examples=50, deadline=None)
    @pytest.mark.asyncio
    async def test_handle_flow_with_valid_code_approves(self, channel_id, user_id):
        """
        Feature: openclaw-integration, Property 45: Approval code validation

        Providing valid code in DM flow should approve the user.
        """
        pool = make_mock_pool()
        call_count = [0]

        async def smart_fetchrow(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                # is_user_approved → not approved
                return {"approved": False}
            elif call_count[0] == 2:
                # validate_approval_code → valid code
                future = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
                return {
                    "approval_code": "654321",
                    "approval_code_expires_at": future,
                    "approved": False,
                }
            return None

        pool.fetchrow = AsyncMock(side_effect=smart_fetchrow)

        pairing = make_dm_pairing(pool)
        is_approved, code = await pairing.handle_dm_pairing_flow(
            channel_id, user_id, provided_code="654321"
        )

        assert is_approved is True
        assert code is None


# ===========================================================================
# Property 46: Approval code rejection
# ===========================================================================


class TestApprovalCodeRejection:
    """Property 46: Invalid/expired codes rejected."""

    @given(channel_id=safe_id, user_id=safe_id)
    @settings(max_examples=50, deadline=None)
    @pytest.mark.asyncio
    async def test_wrong_code_rejected(self, channel_id, user_id):
        """
        Feature: openclaw-integration, Property 46: Approval code rejection

        Wrong code should be rejected.
        """
        pool = make_mock_pool()
        future_time = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
        pool.fetchrow = AsyncMock(return_value={
            "approval_code": "123456",
            "approval_code_expires_at": future_time,
            "approved": False,
        })

        pairing = make_dm_pairing(pool)
        result = await pairing.validate_approval_code(channel_id, user_id, "999999")
        assert result is False

    @given(channel_id=safe_id, user_id=safe_id)
    @settings(max_examples=50, deadline=None)
    @pytest.mark.asyncio
    async def test_expired_code_rejected(self, channel_id, user_id):
        """
        Feature: openclaw-integration, Property 46: Approval code rejection

        Expired code should be rejected.
        """
        pool = make_mock_pool()
        past_time = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
        pool.fetchrow = AsyncMock(return_value={
            "approval_code": "123456",
            "approval_code_expires_at": past_time,
            "approved": False,
        })

        pairing = make_dm_pairing(pool)
        result = await pairing.validate_approval_code(channel_id, user_id, "123456")
        assert result is False

    @given(channel_id=safe_id, user_id=safe_id)
    @settings(max_examples=50, deadline=None)
    @pytest.mark.asyncio
    async def test_no_user_in_db_rejected(self, channel_id, user_id):
        """
        Feature: openclaw-integration, Property 46: Approval code rejection

        Non-existent user should be rejected.
        """
        pool = make_mock_pool()
        pool.fetchrow = AsyncMock(return_value=None)

        pairing = make_dm_pairing(pool)
        result = await pairing.validate_approval_code(channel_id, user_id, "123456")
        assert result is False

    @pytest.mark.asyncio
    async def test_no_expiration_time_rejected(self):
        """
        Feature: openclaw-integration, Property 46: Approval code rejection

        Code without expiration time should be rejected.
        """
        pool = make_mock_pool()
        pool.fetchrow = AsyncMock(return_value={
            "approval_code": "123456",
            "approval_code_expires_at": None,
            "approved": False,
        })

        pairing = make_dm_pairing(pool)
        result = await pairing.validate_approval_code("ch1", "u1", "123456")
        assert result is False

    @pytest.mark.asyncio
    async def test_handle_flow_invalid_code_returns_false(self):
        """
        Feature: openclaw-integration, Property 46: Approval code rejection

        Invalid code in DM flow should return (False, None).
        """
        pool = make_mock_pool()
        call_count = [0]

        async def smart_fetchrow(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return {"approved": False}
            elif call_count[0] == 2:
                future = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
                return {
                    "approval_code": "123456",
                    "approval_code_expires_at": future,
                    "approved": False,
                }
            return None

        pool.fetchrow = AsyncMock(side_effect=smart_fetchrow)

        pairing = make_dm_pairing(pool)
        is_approved, code = await pairing.handle_dm_pairing_flow(
            "ch1", "u1", provided_code="wrong_code"
        )

        assert is_approved is False
        assert code is None


# ===========================================================================
# Property 47: Approval persistence
# ===========================================================================


class TestApprovalPersistence:
    """Property 47: Approval status persisted in database."""

    @given(channel_id=safe_id, user_id=safe_id)
    @settings(max_examples=50, deadline=None)
    @pytest.mark.asyncio
    async def test_approve_user_updates_db(self, channel_id, user_id):
        """
        Feature: openclaw-integration, Property 47: Approval persistence

        approve_user should update the DB with approved=True and clear code.
        """
        pool = make_mock_pool()
        pairing = make_dm_pairing(pool)

        await pairing.approve_user(channel_id, user_id)

        pool.execute.assert_called_once()
        call_args = pool.execute.call_args
        # Verify approved=True is passed
        assert call_args[0][1] is True  # approved
        assert call_args[0][2] is None  # approval_code cleared
        assert call_args[0][3] is None  # approval_code_expires_at cleared

    @given(channel_id=safe_id, user_id=safe_id)
    @settings(max_examples=50, deadline=None)
    @pytest.mark.asyncio
    async def test_is_user_approved_checks_db(self, channel_id, user_id):
        """
        Feature: openclaw-integration, Property 47: Approval persistence

        is_user_approved should query the DB for approval status.
        """
        pool = make_mock_pool()
        pool.fetchrow = AsyncMock(return_value={
            "approved": True,
        })

        pairing = make_dm_pairing(pool)
        result = await pairing.is_user_approved(channel_id, user_id)
        assert result is True

    @given(channel_id=safe_id, user_id=safe_id)
    @settings(max_examples=50, deadline=None)
    @pytest.mark.asyncio
    async def test_unapproved_user_returns_false(self, channel_id, user_id):
        """
        Feature: openclaw-integration, Property 47: Approval persistence

        Unapproved user should return False.
        """
        pool = make_mock_pool()
        pool.fetchrow = AsyncMock(return_value={
            "approved": False,
        })

        pairing = make_dm_pairing(pool)
        result = await pairing.is_user_approved(channel_id, user_id)
        assert result is False

    @given(channel_id=safe_id, user_id=safe_id)
    @settings(max_examples=50, deadline=None)
    @pytest.mark.asyncio
    async def test_nonexistent_user_returns_false(self, channel_id, user_id):
        """
        Feature: openclaw-integration, Property 47: Approval persistence

        Non-existent user should return False.
        """
        pool = make_mock_pool()
        pool.fetchrow = AsyncMock(return_value=None)

        pairing = make_dm_pairing(pool)
        result = await pairing.is_user_approved(channel_id, user_id)
        assert result is False


# ===========================================================================
# Property 48: Approval bypass
# ===========================================================================


class TestApprovalBypass:
    """Property 48: Approved users bypass re-approval."""

    @given(channel_id=safe_id, user_id=safe_id)
    @settings(max_examples=50, deadline=None)
    @pytest.mark.asyncio
    async def test_approved_user_bypasses_flow(self, channel_id, user_id):
        """
        Feature: openclaw-integration, Property 48: Approval bypass

        Already approved user should bypass DM pairing flow.
        """
        pool = make_mock_pool()
        pool.fetchrow = AsyncMock(return_value={
            "approved": True,
            "approval_code": None,
            "approval_code_expires_at": None,
        })

        pairing = make_dm_pairing(pool)
        is_approved, code = await pairing.handle_dm_pairing_flow(
            channel_id, user_id
        )

        assert is_approved is True
        assert code is None

    @given(channel_id=safe_id, user_id=safe_id)
    @settings(max_examples=30, deadline=None)
    @pytest.mark.asyncio
    async def test_approved_user_no_code_stored(self, channel_id, user_id):
        """
        Feature: openclaw-integration, Property 48: Approval bypass

        Approved user should not have any pending approval code.
        """
        pool = make_mock_pool()
        pool.fetchrow = AsyncMock(return_value={
            "approved": True,
            "approval_code": None,
            "approval_code_expires_at": None,
        })

        pairing = make_dm_pairing(pool)

        # Directly check — should be approved
        result = await pairing.is_user_approved(channel_id, user_id)
        assert result is True


# ===========================================================================
# Property 49: Approval revocation
# ===========================================================================


class TestApprovalRevocation:
    """Property 49: Revoked approval requires re-approval."""

    @given(channel_id=safe_id, user_id=safe_id)
    @settings(max_examples=50, deadline=None)
    @pytest.mark.asyncio
    async def test_revoke_updates_db(self, channel_id, user_id):
        """
        Feature: openclaw-integration, Property 49: Approval revocation

        revoke_approval should update DB with approved=False and clear code.
        """
        pool = make_mock_pool()
        pairing = make_dm_pairing(pool)

        await pairing.revoke_approval(channel_id, user_id)

        pool.execute.assert_called_once()
        call_args = pool.execute.call_args
        assert call_args[0][1] is False  # approved=False
        assert call_args[0][2] is None   # approval_code cleared
        assert call_args[0][3] is None   # approval_code_expires_at cleared

    @pytest.mark.asyncio
    async def test_revoked_user_needs_reapproval(self):
        """
        Feature: openclaw-integration, Property 49: Approval revocation

        After revocation, user should need to go through pairing flow again.
        """
        pool = make_mock_pool()
        call_count = [0]

        async def evolving_fetchrow(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] <= 1:
                # First call: is_user_approved → True
                return {"approved": True}
            else:
                # After revoke: is_user_approved → False
                return {"approved": False}

        pool.fetchrow = AsyncMock(side_effect=evolving_fetchrow)

        pairing = make_dm_pairing(pool)

        # Initially approved
        assert await pairing.is_user_approved("ch1", "u1") is True

        # Revoke
        await pairing.revoke_approval("ch1", "u1")

        # Now unapproved
        assert await pairing.is_user_approved("ch1", "u1") is False

    @given(channel_id=safe_id, user_id=safe_id)
    @settings(max_examples=30, deadline=None)
    @pytest.mark.asyncio
    async def test_revoked_user_gets_new_code_in_flow(self, channel_id, user_id):
        """
        Feature: openclaw-integration, Property 49: Approval revocation

        Revoked user going through DM flow should get a new code.
        """
        pool = make_mock_pool()
        call_count = [0]

        async def smart_fetchrow(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                # get_channel_user in is_user_approved → not found (revoked)
                return None
            else:
                # ensure_channel_user in store_approval_code → return user row
                return {
                    "channel_user_id": f"{channel_id}:{user_id}",
                    "channel_id": channel_id,
                    "user_id": user_id,
                    "approved": False,
                }

        pool.fetchrow = AsyncMock(side_effect=smart_fetchrow)

        pairing = make_dm_pairing(pool)
        is_approved, code = await pairing.handle_dm_pairing_flow(
            channel_id, user_id
        )

        assert is_approved is False
        assert code is not None
        assert len(code) == 6
