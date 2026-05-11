"""Integration tests for DM pairing with real database.

These tests use a real PostgreSQL connection to verify the complete
DM pairing flow end-to-end.

Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7
"""

import asyncio
import os
from datetime import datetime, timedelta, timezone

import asyncpg
import pytest

from dm_pairing import DMPairing, initialize_dm_pairing


# Skip integration tests if DATABASE_URI is not set
pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URI"),
    reason="DATABASE_URI not set - skipping integration tests",
)


@pytest.fixture
async def db_pool():
    """Create a database connection pool for testing."""
    database_uri = os.getenv("DATABASE_URI")
    if not database_uri:
        pytest.skip("DATABASE_URI not set")
    
    pool = await asyncpg.create_pool(database_uri, min_size=1, max_size=5)
    yield pool
    await pool.close()


@pytest.fixture
async def dm_pairing_instance(db_pool):
    """Create a DMPairing instance with real database."""
    return DMPairing(db_pool, approval_code_expiration_seconds=900)


@pytest.fixture
async def test_channel(db_pool):
    """Create a test channel for integration tests."""
    channel_id = "test-channel-dm-pairing"
    
    # Create channel
    await db_pool.execute(
        """
        INSERT INTO channels (channel_id, channel_type, config, enabled)
        VALUES ($1, 'telegram', '{}'::jsonb, TRUE)
        ON CONFLICT (channel_id) DO NOTHING
        """,
        channel_id,
    )
    
    yield channel_id
    
    # Cleanup
    await db_pool.execute(
        "DELETE FROM channel_users WHERE channel_id = $1",
        channel_id,
    )
    await db_pool.execute(
        "DELETE FROM channels WHERE channel_id = $1",
        channel_id,
    )


@pytest.mark.asyncio
async def test_complete_dm_pairing_flow(dm_pairing_instance, test_channel):
    """Test the complete DM pairing flow from start to finish."""
    user_id = "test-user-001"
    user_name = "Test User"
    
    # Step 1: User is not approved initially
    is_approved = await dm_pairing_instance.is_user_approved(test_channel, user_id)
    assert is_approved is False
    
    # Step 2: Generate and store approval code
    approval_code = await dm_pairing_instance.store_approval_code(
        test_channel,
        user_id,
        user_name,
    )
    
    assert approval_code is not None
    assert len(approval_code) == 6
    assert approval_code.isdigit()
    
    # Step 3: Validate the approval code
    is_valid = await dm_pairing_instance.validate_approval_code(
        test_channel,
        user_id,
        approval_code,
    )
    assert is_valid is True
    
    # Step 4: Approve the user
    await dm_pairing_instance.approve_user(test_channel, user_id)
    
    # Step 5: Verify user is now approved
    is_approved = await dm_pairing_instance.is_user_approved(test_channel, user_id)
    assert is_approved is True
    
    # Step 6: Revoke approval
    await dm_pairing_instance.revoke_approval(test_channel, user_id)
    
    # Step 7: Verify user is no longer approved
    is_approved = await dm_pairing_instance.is_user_approved(test_channel, user_id)
    assert is_approved is False


@pytest.mark.asyncio
async def test_invalid_approval_code(dm_pairing_instance, test_channel):
    """Test that invalid approval codes are rejected."""
    user_id = "test-user-002"
    
    # Generate and store approval code
    approval_code = await dm_pairing_instance.store_approval_code(
        test_channel,
        user_id,
    )
    
    # Try to validate with wrong code
    is_valid = await dm_pairing_instance.validate_approval_code(
        test_channel,
        user_id,
        "999999",  # Wrong code
    )
    assert is_valid is False
    
    # User should not be approved
    is_approved = await dm_pairing_instance.is_user_approved(test_channel, user_id)
    assert is_approved is False


@pytest.mark.asyncio
async def test_approval_code_expiration(db_pool, test_channel):
    """Test that approval codes expire after the configured time."""
    # Create DM pairing with very short expiration (2 seconds)
    dm_pairing = DMPairing(db_pool, approval_code_expiration_seconds=2)
    
    user_id = "test-user-003"
    
    # Generate and store approval code
    approval_code = await dm_pairing.store_approval_code(
        test_channel,
        user_id,
    )
    
    # Should be valid immediately
    is_valid = await dm_pairing.validate_approval_code(
        test_channel,
        user_id,
        approval_code,
    )
    assert is_valid is True
    
    # Wait for expiration
    await asyncio.sleep(3)
    
    # Should be invalid after expiration
    is_valid = await dm_pairing.validate_approval_code(
        test_channel,
        user_id,
        approval_code,
    )
    assert is_valid is False


@pytest.mark.asyncio
async def test_handle_dm_pairing_flow_convenience_method(dm_pairing_instance, test_channel):
    """Test the convenience method for handling the complete flow."""
    user_id = "test-user-004"
    user_name = "Test User 4"
    
    # First call: user not approved, no code provided → should generate code
    is_approved, code = await dm_pairing_instance.handle_dm_pairing_flow(
        test_channel,
        user_id,
        user_name,
    )
    
    assert is_approved is False
    assert code is not None
    assert len(code) == 6
    
    # Second call: provide the code → should approve user
    is_approved, code = await dm_pairing_instance.handle_dm_pairing_flow(
        test_channel,
        user_id,
        user_name,
        provided_code=code,
    )
    
    assert is_approved is True
    assert code is None
    
    # Third call: user already approved → should return approved immediately
    is_approved, code = await dm_pairing_instance.handle_dm_pairing_flow(
        test_channel,
        user_id,
        user_name,
    )
    
    assert is_approved is True
    assert code is None


@pytest.mark.asyncio
async def test_multiple_users_independent_approval(dm_pairing_instance, test_channel):
    """Test that multiple users have independent approval states."""
    user1_id = "test-user-005"
    user2_id = "test-user-006"
    
    # Generate codes for both users
    code1 = await dm_pairing_instance.store_approval_code(test_channel, user1_id)
    code2 = await dm_pairing_instance.store_approval_code(test_channel, user2_id)
    
    # Codes should be different
    assert code1 != code2
    
    # Approve only user1
    is_valid = await dm_pairing_instance.validate_approval_code(
        test_channel,
        user1_id,
        code1,
    )
    assert is_valid is True
    
    await dm_pairing_instance.approve_user(test_channel, user1_id)
    
    # User1 should be approved, user2 should not
    assert await dm_pairing_instance.is_user_approved(test_channel, user1_id) is True
    assert await dm_pairing_instance.is_user_approved(test_channel, user2_id) is False


@pytest.mark.asyncio
async def test_approval_persists_across_instances(db_pool, test_channel):
    """Test that approval state persists across DMPairing instances."""
    user_id = "test-user-007"
    
    # Create first instance and approve user
    dm_pairing1 = DMPairing(db_pool)
    code = await dm_pairing1.store_approval_code(test_channel, user_id)
    await dm_pairing1.validate_approval_code(test_channel, user_id, code)
    await dm_pairing1.approve_user(test_channel, user_id)
    
    # Create second instance and check approval
    dm_pairing2 = DMPairing(db_pool)
    is_approved = await dm_pairing2.is_user_approved(test_channel, user_id)
    
    assert is_approved is True


@pytest.mark.asyncio
async def test_global_instance_initialization(db_pool):
    """Test global instance initialization and retrieval."""
    from dm_pairing import get_dm_pairing, initialize_dm_pairing
    
    # Initialize global instance
    dm_pairing = initialize_dm_pairing(db_pool, approval_code_expiration_seconds=600)
    
    assert dm_pairing is not None
    assert dm_pairing.approval_code_expiration_seconds == 600
    
    # Retrieve global instance
    retrieved = get_dm_pairing()
    assert retrieved is dm_pairing
