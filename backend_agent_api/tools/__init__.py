"""Tools package for the AI agent.

This package contains tool implementations for:
- Session tools: Inter-session communication (sessions_list, sessions_history, sessions_send)
- Browser tools: Web automation (browser_navigate, browser_click, browser_screenshot, etc.)

It also exposes legacy tool functions that live in ``../tools.py`` so
existing imports like ``from tools import web_search_tool`` keep working.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from .session_tools import (
    sessions_list,
    sessions_history,
    sessions_send,
    SessionToolsError,
    PermissionError,
    SessionNotFoundError,
)

from .browser_tool import (
    browser_navigate,
    browser_click,
    browser_screenshot,
    browser_fill_form,
    browser_execute_js,
    close_session_browser,
    cleanup_all_browsers,
    BrowserToolError,
    BrowserInstanceLimitError,
    BrowserTimeoutError,
    ElementNotFoundError,
    BrowserCrashedError,
)

# Legacy exports from backend_agent_api/tools.py (module path conflict safe-load)
_legacy_tools_path = Path(__file__).resolve().parent.parent / "tools.py"
_legacy_spec = importlib.util.spec_from_file_location("legacy_tools_module", _legacy_tools_path)
if _legacy_spec is None or _legacy_spec.loader is None:
    raise ImportError(f"Failed to load legacy tools module from {_legacy_tools_path}")
_legacy_tools = importlib.util.module_from_spec(_legacy_spec)
_legacy_spec.loader.exec_module(_legacy_tools)

web_search_tool = _legacy_tools.web_search_tool
image_analysis_tool = _legacy_tools.image_analysis_tool
retrieve_relevant_documents_tool = _legacy_tools.retrieve_relevant_documents_tool
retrieve_grounded_context_tool = _legacy_tools.retrieve_grounded_context_tool
list_documents_tool = _legacy_tools.list_documents_tool
get_document_content_tool = _legacy_tools.get_document_content_tool
execute_sql_query_tool = _legacy_tools.execute_sql_query_tool
execute_safe_code_tool = _legacy_tools.execute_safe_code_tool

__all__ = [
    # Session tools
    "sessions_list",
    "sessions_history",
    "sessions_send",
    "SessionToolsError",
    "PermissionError",
    "SessionNotFoundError",
    # Browser tools
    "browser_navigate",
    "browser_click",
    "browser_screenshot",
    "browser_fill_form",
    "browser_execute_js",
    "close_session_browser",
    "cleanup_all_browsers",
    "BrowserToolError",
    "BrowserInstanceLimitError",
    "BrowserTimeoutError",
    "ElementNotFoundError",
    "BrowserCrashedError",
    # Legacy tools
    "web_search_tool",
    "image_analysis_tool",
    "retrieve_relevant_documents_tool",
    "retrieve_grounded_context_tool",
    "list_documents_tool",
    "get_document_content_tool",
    "execute_sql_query_tool",
    "execute_safe_code_tool",
]
