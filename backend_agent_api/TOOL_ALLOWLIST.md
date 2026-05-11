# Tool Allowlist Implementation

## Overview

The tool allowlist system provides per-session access control for AI agent tools. It enables fine-grained security policies by restricting which tools the agent can use in different conversation contexts (main sessions, group chats, webhooks).

## Features

- **Wildcard Pattern Matching**: Support for patterns like `*`, `read_*`, `web_*`, `execute_*`
- **Denylist Precedence**: Denylists override allowlists for dangerous tools
- **Dynamic Updates**: Change tool permissions for active sessions without restart
- **Audit Logging**: All blocked tool attempts are logged for security monitoring
- **Session Type Defaults**: Different default permissions for main, group, and webhook sessions

## Architecture

### Components

1. **tool_allowlist.py**: Core allowlist management with pattern matching and audit logging
2. **session.py**: Session-level tool permission checks via `is_tool_allowed()` and `log_blocked_tool()`
3. **session_manager.py**: Automatic allowlist initialization when creating sessions
4. **agent_tool_filter.py**: Tool name mapping and permission checking utilities
5. **sql/003_tool_access_log.sql**: Database schema for audit logging

### Database Schema

```sql
-- Tool access audit log
CREATE TABLE tool_access_log (
    log_id BIGSERIAL PRIMARY KEY,
    session_id TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    user_id TEXT,
    channel_id TEXT,
    access_granted BOOLEAN NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'
);

-- Add tool_denylist to sessions table
ALTER TABLE sessions ADD COLUMN tool_denylist JSONB DEFAULT '[]';
```

## Usage

### Default Allowlists by Session Type

**Main Sessions (DMs)**:
- Allowlist: `["*"]` (all tools allowed)
- Denylist: `[]` (no restrictions)

**Group Sessions**:
- Allowlist: `["web_search", "retrieve_relevant_documents", "list_documents", "get_document_content", "execute_sql_query", "image_analysis"]`
- Denylist: `[]`

**Webhook Sessions**:
- Allowlist: `["web_search", "retrieve_relevant_documents", "list_documents"]` (read-only)
- Denylist: `[]`

### Checking Tool Permissions

```python
from session import Session

# Check if a tool is allowed in a session
if session.is_tool_allowed("execute_code"):
    # Tool is allowed, execute it
    result = await execute_code(code)
else:
    # Tool is blocked, log the attempt
    await session.log_blocked_tool("execute_code")
    return "I don't have permission to use that tool in this conversation."
```

### Wildcard Pattern Matching

The allowlist supports fnmatch-style wildcard patterns:

```python
# Allow all tools
tool_allowlist = ["*"]

# Allow all web-related tools
tool_allowlist = ["web_*"]  # Matches: web_search, web_fetch, etc.

# Allow all read operations
tool_allowlist = ["read_*", "list_*", "get_*"]

# Allow specific tools
tool_allowlist = ["web_search", "list_documents", "execute_sql_query"]
```

### Denylist Precedence

Denylists always take precedence over allowlists:

```python
# Allow all tools except execution tools
tool_allowlist = ["*"]
tool_denylist = ["execute_*", "browser_*"]

# Result:
# - web_search: ALLOWED
# - list_documents: ALLOWED
# - execute_code: BLOCKED (matches execute_*)
# - execute_sql_query: BLOCKED (matches execute_*)
# - browser_navigate: BLOCKED (matches browser_*)
```

### Dynamic Allowlist Updates

Update tool permissions for an active session:

```python
# Update allowlist and denylist
await session.update_tool_allowlist(
    tool_allowlist=["web_*", "list_*"],
    tool_denylist=["execute_*"],
)

# Changes take effect immediately
assert session.is_tool_allowed("web_search") == True
assert session.is_tool_allowed("execute_code") == False
```

### Audit Logging

All blocked tool attempts are logged to the `tool_access_log` table:

```python
# When a tool is blocked, log it
await session.log_blocked_tool("execute_code")

# Query audit logs
SELECT session_id, tool_name, user_id, channel_id, timestamp
FROM tool_access_log
WHERE access_granted = FALSE
ORDER BY timestamp DESC;
```

## Integration with Agent

### Tool Permission Checking

Tool implementations should check permissions before execution:

```python
from pydantic_ai import RunContext

@agent.tool
async def execute_code(ctx: RunContext[AgentDeps], code: str) -> str:
    """Execute Python code (requires permission)."""
    
    # Get session from context
    session = getattr(ctx.deps, 'session', None)
    
    if session is not None:
        # Check if tool is allowed
        if not session.is_tool_allowed("execute_code"):
            # Log blocked attempt
            await session.log_blocked_tool("execute_code")
            
            # Return error message
            return (
                "I don't have permission to execute code in this conversation. "
                "Please contact an administrator if you need this capability."
            )
    
    # Tool is allowed, execute normally
    return execute_safe_code_tool(code)
```

### Tool Name Mapping

The `agent_tool_filter.py` module provides a mapping between agent tool function names and permission names:

```python
from agent_tool_filter import TOOL_NAME_MAP, get_tool_permission_name

# Map function names to permission names
TOOL_NAME_MAP = {
    "web_search": "web_search",
    "execute_code": "execute_code",
    "list_sessions": "sessions_list",
    "navigate_browser": "browser_navigate",
    # ...
}

# Get permission name for a tool function
permission_name = get_tool_permission_name("list_sessions")
# Returns: "sessions_list"
```

## Security Considerations

### Principle of Least Privilege

- **Main Sessions**: Full access by default (trusted user context)
- **Group Sessions**: Limited tools (shared context, multiple users)
- **Webhook Sessions**: Read-only tools (external triggers, untrusted)

### Dangerous Tools

Consider adding these to denylists for untrusted contexts:

- `execute_*`: Code execution tools (execute_code, execute_sql_query)
- `browser_*`: Browser automation tools (browser_navigate, browser_click)
- `sessions_*`: Inter-session communication tools (sessions_send)

### Audit Trail

The `tool_access_log` table provides:

- **Security monitoring**: Detect unauthorized tool access attempts
- **Policy refinement**: Identify tools that users need but are blocked
- **Incident investigation**: Track tool usage during security incidents

Query blocked attempts:

```sql
-- Most frequently blocked tools
SELECT tool_name, COUNT(*) as blocked_count
FROM tool_access_log
WHERE access_granted = FALSE
GROUP BY tool_name
ORDER BY blocked_count DESC;

-- Blocked attempts by session
SELECT session_id, user_id, channel_id, COUNT(*) as blocked_count
FROM tool_access_log
WHERE access_granted = FALSE
GROUP BY session_id, user_id, channel_id
ORDER BY blocked_count DESC;
```

## Testing

### Unit Tests

Run unit tests for tool allowlist functionality:

```bash
pytest tests/test_tool_allowlist.py -v
```

Tests cover:
- Wildcard pattern matching
- Denylist precedence
- Dynamic allowlist updates
- Audit logging
- Session integration

### Integration Tests

Run integration tests for end-to-end flows:

```bash
pytest tests/test_tool_allowlist_integration.py -v
```

Tests cover:
- Session creation with allowlists
- Tool permission checking
- Blocked tool logging
- Dynamic updates

## Configuration

### Customizing Default Allowlists

Edit `tool_allowlist.py` to customize default allowlists:

```python
# Default tool allowlists by session type
DEFAULT_ALLOWLISTS = {
    "main": ["*"],  # Main sessions: all tools
    "group": [
        "web_search",
        "retrieve_relevant_documents",
        "list_documents",
        # Add more tools as needed
    ],
    "webhook": [
        "web_search",
        "retrieve_relevant_documents",
        # Minimal read-only tools
    ],
}

# Default denylists by channel type
DEFAULT_DENYLISTS = {
    "telegram": [],
    "discord": [],
    "slack": [],
    "whatsapp": [],
}
```

### Per-Channel Policies

Implement channel-specific policies by modifying `initialize_allowlist()`:

```python
def initialize_allowlist(
    self,
    channel_id: str,
    user_id: str,
    session_type: str,
) -> tuple[List[str], List[str]]:
    """Initialize tool allowlist based on session context."""
    
    # Get default allowlist
    allowlist = DEFAULT_ALLOWLISTS.get(session_type, ["*"]).copy()
    
    # Extract channel type
    channel_type = channel_id.split("-")[0]
    
    # Get default denylist
    denylist = DEFAULT_DENYLISTS.get(channel_type, []).copy()
    
    # Add custom logic here
    # Example: Block execution tools on public channels
    if channel_type == "telegram" and session_type == "group":
        denylist.extend(["execute_*", "browser_*"])
    
    return allowlist, denylist
```

## Troubleshooting

### Tool Always Blocked

Check the session's allowlist and denylist:

```python
print(f"Allowlist: {session.tool_allowlist}")
print(f"Denylist: {session.tool_denylist}")
print(f"Tool allowed: {session.is_tool_allowed('tool_name')}")
```

### Audit Logs Not Created

Ensure the database migration has been applied:

```bash
psql -U postgres -d your_database -f sql/003_tool_access_log.sql
```

### Allowlist Not Initialized

Ensure `init_tool_allowlist()` is called in `main.py`:

```python
from tool_allowlist import init_tool_allowlist

# Initialize tool allowlist
init_tool_allowlist(db_pool)
```

## Future Enhancements

- **User-specific allowlists**: Override defaults based on user roles
- **Time-based restrictions**: Limit tool access to specific time windows
- **Rate limiting**: Throttle tool usage per session
- **Tool usage quotas**: Limit number of tool calls per session
- **Admin UI**: Web interface for managing tool allowlists
