"""DM Pairing Security Module.

This module implements the DM pairing security mechanism that requires
user approval before the agent responds to direct messages. It provides:

- Approval code generation (6-digit secure codes)
- Approval code validation with expiration
- User approval persistence
- Approval revocation
- Integration with SessionManager for DM access control

The DM pairing flow:
1. User sends first DM → system generates approval code
2. System sends approval code to user via channel
3. User provides code → system validates and approves
4. Approved users can create Main_Sessions for DMs
5. Admins can revoke approval at any time

Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7
"""

import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import asyncpg

from db_channels import (
    ensure_channel_user,
    get_channel_user,
    update_channel_user_approval,
)

logger = logging.getLogger(__name__)

# Default approval code expiration time (15 minutes)
DEFAULT_APPROVAL_CODE_EXPIRATION_SECONDS = 900


class DMPairing:
    """Manages DM pairing security for user approval.
    
    The DMPairing class provides methods for:
    - Generating secure 6-digit approval codes
    - Storing codes with expiration in the database
    - Validating codes and marking users as approved
    - Checking user approval status
    - Revoking user approval
    
    All approval codes expire after a configurable time (default: 15 minutes).
    """
    
    def __init__(
        self,
        pool: asyncpg.Pool,
        approval_code_expiration_seconds: int = DEFAULT_APPROVAL_CODE_EXPIRATION_SECONDS,
    ):
        """Initialize the DMPairing manager.
        
        Args:
            pool: Database connection pool
            approval_code_expiration_seconds: Time in seconds before approval codes expire
        """
        self.pool = pool
        self.approval_code_expiration_seconds = approval_code_expiration_seconds
    
    def generate_approval_code(self) -> str:
        """Generate a secure 6-digit approval code.
        
        Uses secrets module for cryptographically secure random number generation.
        
        Returns:
            6-digit approval code as a string (e.g., "123456")
        """
        # Generate a random 6-digit number using secrets for security
        code = secrets.randbelow(1000000)
        # Format with leading zeros to ensure 6 digits
        return f"{code:06d}"
    
    async def store_approval_code(
        self,
        channel_id: str,
        user_id: str,
        user_name: Optional[str] = None,
    ) -> str:
        """Generate and store an approval code for a user.
        
        Creates or updates the channel_user record with a new approval code
        and expiration timestamp. The user is marked as not approved.
        
        Args:
            channel_id: Channel identifier
            user_id: Platform-specific user ID
            user_name: Optional user display name
            
        Returns:
            The generated approval code
        """
        # Ensure the user exists in the database
        await ensure_channel_user(self.pool, channel_id, user_id, user_name)
        
        # Generate approval code
        approval_code = self.generate_approval_code()
        
        # Calculate expiration time
        expires_at = datetime.now(timezone.utc) + timedelta(
            seconds=self.approval_code_expiration_seconds
        )
        
        # Store code and expiration, mark as not approved
        await update_channel_user_approval(
            self.pool,
            channel_id,
            user_id,
            approved=False,
            approval_code=approval_code,
            approval_code_expires_at=expires_at.isoformat(),
        )
        
        logger.info(
            f"Generated approval code for user {user_id} on channel {channel_id} "
            f"(expires at {expires_at.isoformat()})"
        )
        
        return approval_code
    
    async def validate_approval_code(
        self,
        channel_id: str,
        user_id: str,
        provided_code: str,
    ) -> bool:
        """Validate an approval code provided by a user.
        
        Checks if:
        1. The user exists in the database
        2. The provided code matches the stored code
        3. The code has not expired
        
        Args:
            channel_id: Channel identifier
            user_id: Platform-specific user ID
            provided_code: The approval code provided by the user
            
        Returns:
            True if the code is valid and not expired, False otherwise
        """
        # Get the user record
        user = await get_channel_user(self.pool, channel_id, user_id)
        
        if not user:
            logger.warning(
                f"Approval code validation failed: user {user_id} not found "
                f"on channel {channel_id}"
            )
            return False
        
        # Check if approval code matches
        stored_code = user.get("approval_code")
        if not stored_code or stored_code != provided_code:
            logger.warning(
                f"Approval code validation failed: code mismatch for user {user_id} "
                f"on channel {channel_id}"
            )
            return False
        
        # Check if code has expired
        expires_at = user.get("approval_code_expires_at")
        if not expires_at:
            logger.warning(
                f"Approval code validation failed: no expiration time for user {user_id} "
                f"on channel {channel_id}"
            )
            return False
        
        # Convert to datetime if it's a string
        if isinstance(expires_at, str):
            expires_at = datetime.fromisoformat(expires_at)
        
        # Ensure timezone-aware comparison
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        
        now = datetime.now(timezone.utc)
        
        if now > expires_at:
            logger.warning(
                f"Approval code validation failed: code expired for user {user_id} "
                f"on channel {channel_id} (expired at {expires_at.isoformat()})"
            )
            return False
        
        logger.info(
            f"Approval code validated successfully for user {user_id} "
            f"on channel {channel_id}"
        )
        
        return True
    
    async def approve_user(
        self,
        channel_id: str,
        user_id: str,
    ) -> None:
        """Mark a user as approved after successful code validation.
        
        Clears the approval code and expiration, and sets approved=True.
        
        Args:
            channel_id: Channel identifier
            user_id: Platform-specific user ID
        """
        await update_channel_user_approval(
            self.pool,
            channel_id,
            user_id,
            approved=True,
            approval_code=None,
            approval_code_expires_at=None,
        )
        
        logger.info(f"Approved user {user_id} on channel {channel_id}")
    
    async def is_user_approved(
        self,
        channel_id: str,
        user_id: str,
    ) -> bool:
        """Check if a user is approved for DM access.
        
        Args:
            channel_id: Channel identifier
            user_id: Platform-specific user ID
            
        Returns:
            True if the user is approved, False otherwise
        """
        user = await get_channel_user(self.pool, channel_id, user_id)
        
        if not user:
            return False
        
        return user.get("approved", False)
    
    async def revoke_approval(
        self,
        channel_id: str,
        user_id: str,
    ) -> None:
        """Revoke a user's approval for DM access.
        
        Sets approved=False and clears any approval code.
        
        Args:
            channel_id: Channel identifier
            user_id: Platform-specific user ID
        """
        await update_channel_user_approval(
            self.pool,
            channel_id,
            user_id,
            approved=False,
            approval_code=None,
            approval_code_expires_at=None,
        )
        
        logger.info(f"Revoked approval for user {user_id} on channel {channel_id}")
    
    async def handle_dm_pairing_flow(
        self,
        channel_id: str,
        user_id: str,
        user_name: Optional[str] = None,
        provided_code: Optional[str] = None,
    ) -> tuple[bool, Optional[str]]:
        """Handle the complete DM pairing flow for a user.
        
        This is a convenience method that handles the entire flow:
        1. Check if user is already approved → return (True, None)
        2. If code provided → validate and approve if valid
        3. If no code → generate and store new code
        
        Args:
            channel_id: Channel identifier
            user_id: Platform-specific user ID
            user_name: Optional user display name
            provided_code: Optional approval code provided by user
            
        Returns:
            Tuple of (is_approved, approval_code)
            - If user is approved: (True, None)
            - If code is valid: (True, None) after approving
            - If code is invalid: (False, None)
            - If no code provided: (False, new_code)
        """
        # Check if user is already approved
        if await self.is_user_approved(channel_id, user_id):
            return (True, None)
        
        # If user provided a code, validate it
        if provided_code:
            is_valid = await self.validate_approval_code(
                channel_id,
                user_id,
                provided_code,
            )
            
            if is_valid:
                # Approve the user
                await self.approve_user(channel_id, user_id)
                return (True, None)
            else:
                # Invalid code
                return (False, None)
        
        # No code provided, generate and store a new one
        approval_code = await self.store_approval_code(
            channel_id,
            user_id,
            user_name,
        )
        
        return (False, approval_code)


# Global DM pairing instance
_dm_pairing: Optional[DMPairing] = None


def initialize_dm_pairing(
    pool: asyncpg.Pool,
    approval_code_expiration_seconds: int = DEFAULT_APPROVAL_CODE_EXPIRATION_SECONDS,
) -> DMPairing:
    """Initialize the global DM pairing instance.
    
    Args:
        pool: Database connection pool
        approval_code_expiration_seconds: Time in seconds before approval codes expire
        
    Returns:
        DMPairing instance
    """
    global _dm_pairing
    
    _dm_pairing = DMPairing(pool, approval_code_expiration_seconds)
    logger.info(
        f"Initialized DM pairing with {approval_code_expiration_seconds}s code expiration"
    )
    
    return _dm_pairing


def get_dm_pairing() -> Optional[DMPairing]:
    """Get the global DM pairing instance.
    
    Returns:
        DMPairing instance, or None if not initialized
    """
    return _dm_pairing
