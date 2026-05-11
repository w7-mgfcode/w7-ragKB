"""Session Manager for lifecycle management of conversation sessions.

This module implements the SessionManager class which handles:
- Session creation and retrieval (idempotent)
- Session lifecycle (create, archive, delete)
- Session isolation with independent message storage
- Memory limits and automatic cleanup
- Session lookup and filtering

The SessionManager maintains an in-memory cache of active sessions
and coordinates with the database for persistence.
"""

import asyncio
import logging
import time
from typing import Dict, List, Optional

import asyncpg

from db_sessions import (
    archive_session,
    create_session,
    delete_session,
    generate_session_id,
    get_or_create_session,
    get_session,
    list_sessions,
)
from session import Session
from tool_allowlist import get_tool_allowlist

logger = logging.getLogger(__name__)

# Session manager configuration
MAX_ACTIVE_SESSIONS = 1000  # Maximum sessions to keep in memory
SESSION_INACTIVE_TIMEOUT = 3600  # Seconds before archiving inactive sessions (1 hour)
CLEANUP_INTERVAL = 300  # Seconds between cleanup runs (5 minutes)


class SessionManager:
    """Manages the lifecycle of conversation sessions.
    
    The SessionManager provides:
    - Idempotent session creation (get_or_create)
    - Session retrieval by session_id or routing components
    - Session archival for inactive sessions
    - Memory management with automatic cleanup
    - Session listing and filtering
    
    Sessions are cached in memory for fast access and persisted to the database.
    """
    
    def __init__(self, pool: asyncpg.Pool):
        """Initialize the SessionManager.
        
        Args:
            pool: Database connection pool
        """
        self.pool = pool
        self.sessions: Dict[str, Session] = {}
        self._cleanup_task: Optional[asyncio.Task] = None
        self._running = False
    
    async def start(self) -> None:
        """Start the session manager and cleanup task."""
        if self._running:
            logger.warning("SessionManager already running")
            return
        
        self._running = True
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("SessionManager started")
    
    async def stop(self) -> None:
        """Stop the session manager and cleanup task."""
        if not self._running:
            return
        
        self._running = False
        
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        
        logger.info("SessionManager stopped")
    
    async def create_session(
        self,
        channel_id: str,
        user_id: str,
        chat_id: str,
        thread_id: Optional[str] = None,
        session_type: str = "main",
        activation_mode: str = "mention",
        tool_allowlist: Optional[List[str]] = None,
        dm_policy: str = "open",
        **kwargs,
    ) -> Session:
        """Create a new session.
        
        This is idempotent - if a session with the same routing components
        already exists, it will be returned instead of creating a duplicate.
        
        For Main_Sessions (DMs), checks DM pairing approval if dm_policy="pairing".
        
        Args:
            channel_id: Channel identifier
            user_id: Platform-specific user ID
            chat_id: DM, group, or thread identifier
            thread_id: Optional thread identifier
            session_type: Type of session (main, group, webhook)
            activation_mode: Activation mode (mention, always, manual)
            tool_allowlist: List of allowed tools (default: all tools allowed)
            dm_policy: DM policy ("open" or "pairing") - only applies to Main_Sessions
            **kwargs: Additional session configuration options
            
        Returns:
            Session instance
            
        Raises:
            PermissionError: If DM pairing is enabled and user is not approved
        """
        # Check DM pairing approval for Main_Sessions if policy is "pairing"
        if session_type == "main" and dm_policy == "pairing":
            from dm_pairing import get_dm_pairing
            
            dm_pairing = get_dm_pairing()
            if dm_pairing:
                is_approved = await dm_pairing.is_user_approved(channel_id, user_id)
                
                if not is_approved:
                    logger.warning(
                        f"DM pairing: User {user_id} on channel {channel_id} "
                        f"is not approved for Main_Session creation"
                    )
                    raise PermissionError(
                        f"User {user_id} is not approved for DM access. "
                        f"Please complete the DM pairing process first."
                    )
        
        # Generate session_id from routing components
        session_id = generate_session_id(channel_id, user_id, chat_id, thread_id)
        
        # Check if session already exists in cache
        if session_id in self.sessions:
            logger.debug(f"Session {session_id} already exists in cache")
            return self.sessions[session_id]
        
        # Initialize tool allowlist if not provided
        if tool_allowlist is None:
            try:
                tool_allowlist_manager = get_tool_allowlist()
                tool_allowlist, tool_denylist = tool_allowlist_manager.initialize_allowlist(
                    channel_id=channel_id,
                    user_id=user_id,
                    session_type=session_type,
                )
                # Store denylist in kwargs for session creation
                kwargs['tool_denylist'] = tool_denylist
            except RuntimeError:
                # ToolAllowlist not initialized, use default
                logger.warning("ToolAllowlist not initialized, using default allowlist")
                tool_allowlist = None
        
        # Get or create in database
        session_data = await get_or_create_session(
            self.pool,
            session_id,
            channel_id,
            user_id,
            chat_id,
            session_type,
            activation_mode,
            tool_allowlist,
        )
        
        # Create Session instance
        session = self._session_from_db_row(session_data, **kwargs)
        
        # Add to cache
        self.sessions[session_id] = session
        
        # Check memory limits
        await self._enforce_memory_limits()
        
        logger.info(
            f"Created session {session_id} "
            f"(type: {session_type}, channel: {channel_id}, user: {user_id})"
        )
        
        return session
    
    async def get_session(self, session_id: str) -> Optional[Session]:
        """Retrieve a session by session_id.
        
        Args:
            session_id: Unique session identifier
            
        Returns:
            Session instance, or None if not found
        """
        # Check cache first
        if session_id in self.sessions:
            return self.sessions[session_id]
        
        # Fetch from database
        session_data = await get_session(self.pool, session_id)
        
        if not session_data:
            return None
        
        # Create Session instance and add to cache
        session = self._session_from_db_row(session_data)
        self.sessions[session_id] = session
        
        return session
    
    async def get_or_create_session(
        self,
        channel_id: str,
        user_id: str,
        chat_id: str,
        thread_id: Optional[str] = None,
        session_type: str = "main",
        activation_mode: str = "mention",
        tool_allowlist: Optional[List[str]] = None,
        dm_policy: str = "open",
        **kwargs,
    ) -> Session:
        """Get an existing session or create a new one.
        
        This is the primary method for session retrieval and implements
        idempotent session creation.
        
        For Main_Sessions (DMs), checks DM pairing approval if dm_policy="pairing".
        
        Args:
            channel_id: Channel identifier
            user_id: Platform-specific user ID
            chat_id: DM, group, or thread identifier
            thread_id: Optional thread identifier
            session_type: Type of session (main, group, webhook)
            activation_mode: Activation mode (mention, always, manual)
            tool_allowlist: List of allowed tools (default: all tools allowed)
            dm_policy: DM policy ("open" or "pairing") - only applies to Main_Sessions
            **kwargs: Additional session configuration options
            
        Returns:
            Session instance
            
        Raises:
            PermissionError: If DM pairing is enabled and user is not approved
        """
        # Generate session_id
        session_id = generate_session_id(channel_id, user_id, chat_id, thread_id)
        
        # Try to get existing session
        session = await self.get_session(session_id)
        
        if session:
            return session
        
        # Create new session
        return await self.create_session(
            channel_id,
            user_id,
            chat_id,
            thread_id,
            session_type,
            activation_mode,
            tool_allowlist,
            dm_policy,
            **kwargs,
        )
    
    async def list_sessions(
        self,
        channel_id: Optional[str] = None,
        user_id: Optional[str] = None,
        session_type: Optional[str] = None,
        include_archived: bool = False,
    ) -> List[Session]:
        """List sessions with optional filters.
        
        Args:
            channel_id: Optional filter by channel
            user_id: Optional filter by user
            session_type: Optional filter by session type
            include_archived: If True, include archived sessions
            
        Returns:
            List of Session instances
        """
        # Fetch from database
        sessions_data = await list_sessions(
            self.pool,
            channel_id,
            user_id,
            session_type,
            include_archived,
        )
        
        # Convert to Session instances
        sessions = []
        for session_data in sessions_data:
            session_id = session_data["session_id"]
            
            # Use cached session if available
            if session_id in self.sessions:
                sessions.append(self.sessions[session_id])
            else:
                session = self._session_from_db_row(session_data)
                sessions.append(session)
        
        return sessions
    
    async def archive_session(self, session_id: str) -> None:
        """Archive a session by setting archived_at timestamp.
        
        Archived sessions are removed from the in-memory cache but
        remain in the database with their message history.
        
        Also closes any browser instances associated with the session.
        
        Args:
            session_id: Unique session identifier
        """
        # Close browser instance if exists
        from tools.browser_tool import close_session_browser
        await close_session_browser(session_id)
        
        await archive_session(self.pool, session_id)
        
        # Remove from cache
        if session_id in self.sessions:
            del self.sessions[session_id]
        
        logger.info(f"Archived session {session_id}")
    
    async def delete_session(self, session_id: str) -> None:
        """Delete a session and all its messages.
        
        This permanently removes the session from the database.
        Use archive_session instead to preserve history.
        
        Also closes any browser instances associated with the session.
        
        Args:
            session_id: Unique session identifier
        """
        # Close browser instance if exists
        from tools.browser_tool import close_session_browser
        await close_session_browser(session_id)
        
        await delete_session(self.pool, session_id)
        
        # Remove from cache
        if session_id in self.sessions:
            del self.sessions[session_id]
        
        logger.info(f"Deleted session {session_id}")
    
    def get_active_session_count(self) -> int:
        """Get the number of active sessions in memory.
        
        Returns:
            Number of active sessions
        """
        return len(self.sessions)
    
    def _session_from_db_row(
        self,
        row: Dict,
        **kwargs,
    ) -> Session:
        """Create a Session instance from a database row.
        
        Args:
            row: Database row dictionary
            **kwargs: Additional session configuration options
            
        Returns:
            Session instance
        """
        # Extract tool_allowlist from JSONB
        tool_allowlist = row.get("tool_allowlist", ["*"])
        if isinstance(tool_allowlist, str):
            import json
            tool_allowlist = json.loads(tool_allowlist)
        
        # Extract tool_denylist from JSONB
        tool_denylist = row.get("tool_denylist", [])
        if isinstance(tool_denylist, str):
            import json
            tool_denylist = json.loads(tool_denylist)
        
        # Extract token_usage from JSONB
        token_usage = row.get("token_usage", {})
        if isinstance(token_usage, str):
            import json
            token_usage = json.loads(token_usage)
        
        # Convert timestamps to float
        created_at = None
        if row.get("created_at"):
            created_at = row["created_at"].timestamp()
        
        last_activity_at = None
        if row.get("last_activity_at"):
            last_activity_at = row["last_activity_at"].timestamp()
        
        return Session(
            pool=self.pool,
            session_id=row["session_id"],
            channel_id=row["channel_id"],
            user_id=row["user_id"],
            chat_id=row["chat_id"],
            session_type=row["session_type"],
            activation_mode=row.get("activation_mode", "mention"),
            tool_allowlist=tool_allowlist,
            tool_denylist=tool_denylist,
            message_count=row.get("message_count", 0),
            token_usage=token_usage,
            created_at=created_at,
            last_activity_at=last_activity_at,
            **kwargs,
        )
    
    async def _enforce_memory_limits(self) -> None:
        """Enforce memory limits by archiving least recently used sessions.
        
        If the number of active sessions exceeds MAX_ACTIVE_SESSIONS,
        archive the least recently used sessions until we're under the limit.
        """
        if len(self.sessions) <= MAX_ACTIVE_SESSIONS:
            return
        
        # Sort sessions by last_activity_at (oldest first)
        sorted_sessions = sorted(
            self.sessions.values(),
            key=lambda s: s.last_activity_at,
        )
        
        # Calculate how many to archive
        to_archive = len(self.sessions) - MAX_ACTIVE_SESSIONS
        
        logger.info(
            f"Memory limit exceeded ({len(self.sessions)}/{MAX_ACTIVE_SESSIONS}), "
            f"archiving {to_archive} sessions"
        )
        
        # Archive oldest sessions
        for session in sorted_sessions[:to_archive]:
            await self.archive_session(session.session_id)
    
    async def _cleanup_inactive_sessions(self) -> None:
        """Archive sessions that have been inactive for too long.
        
        Sessions inactive for longer than SESSION_INACTIVE_TIMEOUT
        are automatically archived to free memory.
        """
        now = time.time()
        inactive_sessions = []
        
        for session in self.sessions.values():
            if now - session.last_activity_at > SESSION_INACTIVE_TIMEOUT:
                inactive_sessions.append(session.session_id)
        
        if inactive_sessions:
            logger.info(f"Archiving {len(inactive_sessions)} inactive sessions")
            
            for session_id in inactive_sessions:
                await self.archive_session(session_id)
    
    async def _cleanup_loop(self) -> None:
        """Background task that periodically cleans up inactive sessions."""
        logger.info(f"Starting session cleanup loop (interval: {CLEANUP_INTERVAL}s)")
        
        while self._running:
            try:
                await asyncio.sleep(CLEANUP_INTERVAL)
                
                if not self._running:
                    break
                
                logger.debug("Running session cleanup")
                await self._cleanup_inactive_sessions()
                await self._enforce_memory_limits()
                
            except asyncio.CancelledError:
                break
            
            except Exception as e:
                logger.error(f"Error in session cleanup loop: {e}", exc_info=True)
        
        logger.info("Session cleanup loop stopped")
    
    def get_metrics(self) -> Dict:
        """Get session manager metrics.
        
        Returns:
            Dictionary containing metrics
        """
        return {
            "active_sessions": len(self.sessions),
            "max_active_sessions": MAX_ACTIVE_SESSIONS,
            "inactive_timeout_seconds": SESSION_INACTIVE_TIMEOUT,
            "cleanup_interval_seconds": CLEANUP_INTERVAL,
        }


# Global session manager instance
_session_manager: Optional[SessionManager] = None


async def start_session_manager(pool: asyncpg.Pool) -> SessionManager:
    """Start the global session manager.
    
    Args:
        pool: Database connection pool
        
    Returns:
        SessionManager instance
    """
    global _session_manager
    
    if _session_manager is None:
        _session_manager = SessionManager(pool)
    
    await _session_manager.start()
    return _session_manager


async def stop_session_manager() -> None:
    """Stop the global session manager."""
    global _session_manager
    
    if _session_manager:
        await _session_manager.stop()


def get_session_manager() -> Optional[SessionManager]:
    """Get the global session manager instance.
    
    Returns:
        SessionManager instance, or None if not started
    """
    return _session_manager
