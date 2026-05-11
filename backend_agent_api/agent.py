import asyncpg
from pydantic_ai import Agent, RunContext
from dataclasses import dataclass
from dotenv import load_dotenv
from httpx import AsyncClient
from pathlib import Path
from typing import Optional
import os

from vertex_provider import get_model
from vertex_embeddings import VertexEmbeddingClient

# Check if we're in production
is_production = os.getenv("ENVIRONMENT") == "production"

if not is_production:
    # Development: prioritize .env file
    project_root = Path(__file__).resolve().parent
    dotenv_path = project_root / '.env'
    load_dotenv(dotenv_path, override=True)
else:
    # Production: use cloud platform env vars only
    load_dotenv()

from prompt import AGENT_SYSTEM_PROMPT
from tools import (
    web_search_tool,
    image_analysis_tool,
    retrieve_relevant_documents_tool,
    list_documents_tool,
    get_document_content_tool,
    execute_sql_query_tool,
    execute_safe_code_tool
)

# ========== Pydantic AI Agent ==========
@dataclass
class AgentDeps:
    db_pool: asyncpg.Pool
    embedding_client: VertexEmbeddingClient
    http_client: AsyncClient
    brave_api_key: str | None
    searxng_base_url: str | None
    memories: str
    slack_user_id: str
    session_manager: Optional[object] = None  # SessionManager instance
    session_id: Optional[str] = None  # Current session ID for session tools
    session: Optional[object] = None  # Session instance for tool access control

agent = Agent(
    get_model(),
    system_prompt=AGENT_SYSTEM_PROMPT,
    deps_type=AgentDeps,
    retries=2,
    instrument=True,
)

@agent.system_prompt  
def add_memories(ctx: RunContext[str]) -> str:
    return f"\nUser Memories:\n{ctx.deps.memories}"

@agent.tool
async def web_search(ctx: RunContext[AgentDeps], query: str) -> str:
    """
    Search the web with a specific query and get a summary of the top search results.
    
    Args:
        ctx: The context for the agent including the HTTP client and optional Brave API key/SearXNG base url
        query: The query for the web search
        
    Returns:
        A summary of the web search.
        For Brave, this is a single paragraph.
        For SearXNG, this is a list of the top search results including the most relevant snippet from the page.
    """
    print("Calling web_search tool")
    return await web_search_tool(query, ctx.deps.http_client, ctx.deps.brave_api_key, ctx.deps.searxng_base_url)    

@agent.tool
async def retrieve_relevant_documents(ctx: RunContext[AgentDeps], user_query: str) -> str:
    """
    Retrieve relevant document chunks based on the query with RAG.
    
    Args:
        ctx: The context including the database pool and embedding client
        user_query: The user's question or query
        
    Returns:
        A formatted string containing the top 4 most relevant documents chunks
    """
    print("Calling retrieve_relevant_documents tool")
    return await retrieve_relevant_documents_tool(ctx.deps.db_pool, ctx.deps.embedding_client, user_query)

@agent.tool
async def list_documents(ctx: RunContext[AgentDeps]) -> str:
    """
    Retrieve a list of all available documents.
    
    Returns:
        List[str]: List of documents including their metadata (URL/path, schema if applicable, etc.)
    """
    print("Calling list_documents tool")
    return await list_documents_tool(ctx.deps.db_pool)

@agent.tool
async def get_document_content(ctx: RunContext[AgentDeps], document_id: str) -> str:
    """
    Retrieve the full content of a specific document by combining all its chunks.
    
    Args:
        ctx: The context including the database pool
        document_id: The ID (or file path) of the document to retrieve
        
    Returns:
        str: The full content of the document with all chunks combined in order
    """
    print("Calling get_document_content tool")
    return await get_document_content_tool(ctx.deps.db_pool, document_id)

@agent.tool
async def execute_sql_query(ctx: RunContext[AgentDeps], sql_query: str) -> str:
    """
    Run a SQL query - use this to query from the document_rows table once you know the file ID you are querying. 
    dataset_id is the file_id and you are always using the row_data for filtering, which is a jsonb field that has 
    all the keys from the file schema given in the document_metadata table.

    Never use a placeholder file ID. Always use the list_documents tool first to get the file ID.

    Example query:

    SELECT AVG((row_data->>'revenue')::numeric)
    FROM document_rows
    WHERE dataset_id = '123';

    Example query 2:

    SELECT 
        row_data->>'category' as category,
        SUM((row_data->>'sales')::numeric) as total_sales
    FROM document_rows
    WHERE dataset_id = '123'
    GROUP BY row_data->>'category';
    
    Args:
        ctx: The context including the database pool
        sql_query: The SQL query to execute (must be read-only)
        
    Returns:
        str: The results of the SQL query in JSON format
    """
    print(f"Calling execute_sql_query tool with SQL: {sql_query }")
    return await execute_sql_query_tool(ctx.deps.db_pool, sql_query)    

@agent.tool
async def image_analysis(ctx: RunContext[AgentDeps], document_id: str, query: str) -> str:
    """
    Analyzes an image based on the document ID of the image provided.
    This function pulls the binary of the image from the knowledge base
    and passes that into a subagent with a vision LLM
    Before calling this tool, call list_documents to see the images available
    and to get the exact document ID for the image.
    
    Args:
        ctx: The context including the database pool
        document_id: The ID (or file path) of the image to analyze
        query: What to extract from the image analysis
        
    Returns:
        str: An analysis of the image based on the query
    """
    print("Calling image_analysis tool")
    return await image_analysis_tool(ctx.deps.db_pool, document_id, query)    

# Using the MCP server instead for code execution, but you can use this simple version
# if you don't want to use MCP for whatever reason! Just uncomment the line below:
@agent.tool
async def execute_code(ctx: RunContext[AgentDeps], code: str) -> str:
    """
    Executes a given Python code string in a protected environment.
    Use print to output anything that you need as a result of executing the code.
    
    Args:
        code: Python code to execute
        
    Returns:
        str: Anything printed out to standard output with the print command
    """    
    print(f"executing code: {code}")
    print(f"Result is: {execute_safe_code_tool(code)}")
    return execute_safe_code_tool(code)

# ========== Session Tools ==========
# Import session tools
from tools.session_tools import (
    sessions_list as sessions_list_impl,
    sessions_history as sessions_history_impl,
    sessions_send as sessions_send_impl,
)

# ========== Browser Tools ==========
# Import browser tools
from tools.browser_tool import (
    browser_navigate as browser_navigate_impl,
    browser_click as browser_click_impl,
    browser_screenshot as browser_screenshot_impl,
    browser_fill_form as browser_fill_form_impl,
    browser_execute_js as browser_execute_js_impl,
)

@agent.tool
async def list_sessions(ctx: RunContext[AgentDeps]) -> str:
    """
    List all active conversation sessions that you have access to.
    
    This tool shows sessions from the same user across different channels,
    allowing you to coordinate multi-session tasks and share information
    between conversations.
    
    Returns:
        A formatted list of accessible sessions with their metadata including
        session_id, channel, user, message count, and last activity timestamp.
    """
    if not ctx.deps.session_manager or not ctx.deps.session_id:
        return "Session tools are not available in this context."
    
    try:
        sessions = await sessions_list_impl(ctx)
        
        if not sessions:
            return "No accessible sessions found."
        
        # Format sessions for display
        result = f"Found {len(sessions)} accessible session(s):\n\n"
        for session in sessions:
            result += f"• Session ID: {session['session_id']}\n"
            result += f"  Channel: {session['channel_id']}\n"
            result += f"  User: {session['user_id']}\n"
            result += f"  Type: {session['session_type']}\n"
            result += f"  Messages: {session['message_count']}\n"
            result += f"  Last active: {session['last_activity']}\n\n"
        
        return result
    
    except Exception as e:
        return f"Error listing sessions: {str(e)}"

@agent.tool
async def get_session_history(
    ctx: RunContext[AgentDeps],
    session_id: str,
    limit: int = 10,
) -> str:
    """
    Retrieve message history from another conversation session.
    
    Use this tool to review what was discussed in a different session,
    enabling you to maintain context across multiple conversations or
    coordinate tasks that span multiple sessions.
    
    Args:
        session_id: The ID of the session to retrieve history from
        limit: Maximum number of recent messages to retrieve (default: 10, max: 100)
        
    Returns:
        A formatted list of messages from the target session in chronological order.
    """
    if not ctx.deps.session_manager or not ctx.deps.session_id:
        return "Session tools are not available in this context."
    
    try:
        messages = await sessions_history_impl(ctx, session_id, limit)
        
        if not messages:
            return f"No messages found in session {session_id}."
        
        # Format messages for display
        result = f"Message history for session {session_id} ({len(messages)} messages):\n\n"
        for msg in messages:
            role = msg['role'].upper()
            content = msg['content'][:200]  # Truncate long messages
            if len(msg['content']) > 200:
                content += "..."
            result += f"[{role}] {content}\n\n"
        
        return result
    
    except Exception as e:
        return f"Error retrieving session history: {str(e)}"

@agent.tool
async def send_to_session(
    ctx: RunContext[AgentDeps],
    session_id: str,
    message: str,
) -> str:
    """
    Send a message to another conversation session.
    
    Use this tool to deliver information or updates to a different session,
    enabling coordination across multiple conversations. The message will
    appear in the target session as if it came from you (the agent).
    
    Args:
        session_id: The ID of the target session to send the message to
        message: The message content to send
        
    Returns:
        Confirmation that the message was delivered successfully.
    """
    if not ctx.deps.session_manager or not ctx.deps.session_id:
        return "Session tools are not available in this context."
    
    try:
        result = await sessions_send_impl(ctx, session_id, message)
        return (
            f"Message delivered successfully to session {result['session_id']}. "
            f"Sent {result['message_length']} characters."
        )
    
    except Exception as e:
        return f"Error sending message to session: {str(e)}"


# ========== Browser Tools ==========

@agent.tool
async def navigate_browser(ctx: RunContext[AgentDeps], url: str) -> str:
    """
    Navigate the browser to a specific URL.
    
    This tool opens a web page in a headless browser instance that persists
    for the duration of this conversation session. Use this to start interacting
    with web applications, forms, or any web content.
    
    Args:
        url: The URL to navigate to (must include protocol, e.g., https://example.com)
        
    Returns:
        Confirmation that navigation was successful.
    """
    if not ctx.deps.session_id:
        return "Browser tools are not available in this context."
    
    try:
        result = await browser_navigate_impl(ctx.deps.session_id, url)
        return f"Successfully navigated to {result['url']}"
    
    except Exception as e:
        return f"Error navigating browser: {str(e)}"


@agent.tool
async def click_element(ctx: RunContext[AgentDeps], selector: str) -> str:
    """
    Click an element on the current web page using a CSS selector.
    
    Use this tool to interact with buttons, links, or any clickable elements
    on the page. The browser must already be navigated to a page using
    navigate_browser before calling this tool.
    
    Args:
        selector: CSS selector for the element to click (e.g., "#submit-button", ".login-link")
        
    Returns:
        Confirmation that the element was clicked successfully.
    """
    if not ctx.deps.session_id:
        return "Browser tools are not available in this context."
    
    try:
        result = await browser_click_impl(ctx.deps.session_id, selector)
        return f"Successfully clicked element: {result['selector']}"
    
    except Exception as e:
        return f"Error clicking element: {str(e)}"


@agent.tool
async def capture_screenshot(
    ctx: RunContext[AgentDeps],
    selector: Optional[str] = None,
    full_page: bool = False,
) -> str:
    """
    Capture a screenshot of the current web page or a specific element.
    
    Use this tool to visually inspect the current state of the web page,
    verify that actions were successful, or capture content for analysis.
    The screenshot is returned as a base64-encoded PNG image.
    
    Args:
        selector: Optional CSS selector to screenshot a specific element only
        full_page: If True, captures the entire scrollable page (default: False, viewport only)
        
    Returns:
        Base64-encoded PNG image of the screenshot.
    """
    if not ctx.deps.session_id:
        return "Browser tools are not available in this context."
    
    try:
        screenshot_base64 = await browser_screenshot_impl(
            ctx.deps.session_id,
            selector=selector,
            full_page=full_page,
        )
        return f"Screenshot captured successfully (base64 PNG, {len(screenshot_base64)} characters)"
    
    except Exception as e:
        return f"Error capturing screenshot: {str(e)}"


@agent.tool
async def fill_form_field(
    ctx: RunContext[AgentDeps],
    selector: str,
    value: str,
) -> str:
    """
    Fill a form field on the current web page with a specific value.
    
    Use this tool to input text into form fields, text areas, or any input
    elements. The browser must already be navigated to a page with the form.
    
    Args:
        selector: CSS selector for the form field (e.g., "#email", "input[name='username']")
        value: The text value to fill into the field
        
    Returns:
        Confirmation that the field was filled successfully.
    """
    if not ctx.deps.session_id:
        return "Browser tools are not available in this context."
    
    try:
        result = await browser_fill_form_impl(ctx.deps.session_id, selector, value)
        return (
            f"Successfully filled form field: {result['selector']} "
            f"(value length: {result['value_length']} characters)"
        )
    
    except Exception as e:
        return f"Error filling form field: {str(e)}"


@agent.tool
async def execute_javascript(ctx: RunContext[AgentDeps], script: str) -> str:
    """
    Execute JavaScript code in the browser context and return the result.
    
    Use this tool to interact with the page's JavaScript environment, extract
    data from the DOM, trigger JavaScript functions, or inspect page state.
    The script should be a valid JavaScript expression or statement.
    
    Args:
        script: JavaScript code to execute (e.g., "document.title", "window.location.href")
        
    Returns:
        The result of the JavaScript execution as a string.
    """
    if not ctx.deps.session_id:
        return "Browser tools are not available in this context."
    
    try:
        result = await browser_execute_js_impl(ctx.deps.session_id, script)
        return f"JavaScript execution result: {result}"
    
    except Exception as e:
        return f"Error executing JavaScript: {str(e)}"
