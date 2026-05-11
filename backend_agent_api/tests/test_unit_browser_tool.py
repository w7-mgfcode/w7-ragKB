"""Unit tests for the browser tool.

Feature: openclaw-integration (Task 12.2)
Tests: BrowserInstance lifecycle, get/close session browser,
cleanup_all_browsers, error hierarchy, screenshot encoding,
tool function wrappers, instance limit enforcement.
"""

import asyncio
import base64
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tools.browser_tool import (
    MAX_BROWSER_INSTANCES,
    DEFAULT_TIMEOUT_MS,
    DEFAULT_VIEWPORT,
    BrowserCrashedError,
    BrowserInstance,
    BrowserInstanceLimitError,
    BrowserTimeoutError,
    BrowserToolError,
    ElementNotFoundError,
    _browser_instances,
    browser_click,
    browser_execute_js,
    browser_fill_form,
    browser_navigate,
    browser_screenshot,
    cleanup_all_browsers,
    close_session_browser,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_mock_instance(session_id="test-s1"):
    """Create a BrowserInstance with mocked page/context."""
    context = AsyncMock()
    page = AsyncMock()
    page.goto = AsyncMock()
    page.click = AsyncMock()
    page.fill = AsyncMock()
    page.screenshot = AsyncMock(return_value=b"\x89PNG\r\n" + b"\x00" * 20)
    page.evaluate = AsyncMock(return_value="result")
    page.query_selector = AsyncMock()

    instance = BrowserInstance.__new__(BrowserInstance)
    instance.session_id = session_id
    instance.context = context
    instance.page = page
    instance.created_at = asyncio.get_event_loop().time()
    instance.last_used_at = instance.created_at
    return instance


def setup_instances():
    """Clear global instances before test."""
    _browser_instances.clear()


# ===========================================================================
# Error class hierarchy
# ===========================================================================


class TestErrorHierarchy:
    """Unit tests for error class hierarchy."""

    def test_browser_tool_error_is_exception(self):
        assert issubclass(BrowserToolError, Exception)

    def test_instance_limit_error_is_browser_error(self):
        assert issubclass(BrowserInstanceLimitError, BrowserToolError)

    def test_timeout_error_is_browser_error(self):
        assert issubclass(BrowserTimeoutError, BrowserToolError)

    def test_element_not_found_is_browser_error(self):
        assert issubclass(ElementNotFoundError, BrowserToolError)

    def test_crashed_error_is_browser_error(self):
        assert issubclass(BrowserCrashedError, BrowserToolError)

    def test_error_messages(self):
        """Error instances should carry descriptive messages."""
        e = BrowserInstanceLimitError("too many")
        assert "too many" in str(e)

        e = BrowserTimeoutError("took too long")
        assert "took too long" in str(e)

        e = ElementNotFoundError("no such element")
        assert "no such element" in str(e)


# ===========================================================================
# BrowserInstance methods
# ===========================================================================


class TestBrowserInstanceMethods:
    """Unit tests for BrowserInstance methods."""

    @pytest.mark.asyncio
    async def test_navigate_success(self):
        """navigate should call page.goto and log."""
        inst = make_mock_instance()
        await inst.navigate("https://example.com")

        inst.page.goto.assert_called_once()
        assert inst.page.goto.call_args.args[0] == "https://example.com"

    @pytest.mark.asyncio
    async def test_navigate_with_custom_timeout(self):
        """navigate should pass timeout_ms to page.goto."""
        inst = make_mock_instance()
        await inst.navigate("https://example.com", timeout_ms=5000)

        kwargs = inst.page.goto.call_args.kwargs
        assert kwargs["timeout"] == 5000

    @pytest.mark.asyncio
    async def test_click_success(self):
        """click should call page.click with selector."""
        inst = make_mock_instance()
        await inst.click("#btn")

        inst.page.click.assert_called_once()
        assert inst.page.click.call_args.args[0] == "#btn"

    @pytest.mark.asyncio
    async def test_fill_form_success(self):
        """fill_form should call page.fill with selector and value."""
        inst = make_mock_instance()
        await inst.fill_form("#name", "Alice")

        inst.page.fill.assert_called_once()
        args = inst.page.fill.call_args.args
        assert args[0] == "#name"
        assert args[1] == "Alice"

    @pytest.mark.asyncio
    async def test_screenshot_viewport(self):
        """screenshot without selector should capture viewport."""
        inst = make_mock_instance()
        result = await inst.screenshot()

        assert isinstance(result, bytes)
        inst.page.screenshot.assert_called_once_with(full_page=False)

    @pytest.mark.asyncio
    async def test_screenshot_full_page(self):
        """screenshot with full_page=True should pass flag."""
        inst = make_mock_instance()
        await inst.screenshot(full_page=True)

        inst.page.screenshot.assert_called_once_with(full_page=True)

    @pytest.mark.asyncio
    async def test_screenshot_element(self):
        """screenshot with selector should capture element."""
        inst = make_mock_instance()
        mock_el = AsyncMock()
        mock_el.screenshot = AsyncMock(return_value=b"PNG_DATA")
        inst.page.query_selector.return_value = mock_el

        result = await inst.screenshot(selector="#target")

        inst.page.query_selector.assert_called_once_with("#target")
        assert result == b"PNG_DATA"

    @pytest.mark.asyncio
    async def test_screenshot_element_not_found(self):
        """screenshot with missing selector should raise ElementNotFoundError."""
        inst = make_mock_instance()
        inst.page.query_selector.return_value = None

        with pytest.raises(ElementNotFoundError):
            await inst.screenshot(selector="#missing")

    @pytest.mark.asyncio
    async def test_execute_js_success(self):
        """execute_js should call page.evaluate and return result."""
        inst = make_mock_instance()
        inst.page.evaluate.return_value = 42

        result = await inst.execute_js("1 + 1")
        assert result == 42

    @pytest.mark.asyncio
    async def test_execute_js_timeout(self):
        """execute_js timeout should raise BrowserTimeoutError."""
        inst = make_mock_instance()
        inst.page.evaluate.side_effect = asyncio.TimeoutError()

        with pytest.raises(BrowserTimeoutError):
            await inst.execute_js("while(true){}", timeout_ms=100)

    @pytest.mark.asyncio
    async def test_close_closes_context(self):
        """close should close the browser context."""
        inst = make_mock_instance()
        await inst.close()

        inst.context.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_last_used_at_updated(self):
        """Operations should update last_used_at."""
        inst = make_mock_instance()
        initial = inst.last_used_at

        await inst.navigate("https://example.com")
        assert inst.last_used_at >= initial

        t1 = inst.last_used_at
        await inst.click("#btn")
        assert inst.last_used_at >= t1


# ===========================================================================
# close_session_browser
# ===========================================================================


class TestCloseSessionBrowser:
    """Unit tests for close_session_browser."""

    @pytest.mark.asyncio
    async def test_close_existing_session(self):
        """Closing existing session should remove from registry."""
        setup_instances()
        inst = make_mock_instance("s1")
        _browser_instances["s1"] = inst

        await close_session_browser("s1")

        assert "s1" not in _browser_instances
        inst.context.close.assert_called_once()
        setup_instances()

    @pytest.mark.asyncio
    async def test_close_nonexistent_session(self):
        """Closing nonexistent session should not raise."""
        setup_instances()
        await close_session_browser("nonexistent")
        setup_instances()

    @pytest.mark.asyncio
    async def test_close_preserves_other_sessions(self):
        """Closing one session should not affect others."""
        setup_instances()
        inst1 = make_mock_instance("s1")
        inst2 = make_mock_instance("s2")
        _browser_instances["s1"] = inst1
        _browser_instances["s2"] = inst2

        await close_session_browser("s1")

        assert "s1" not in _browser_instances
        assert "s2" in _browser_instances
        assert _browser_instances["s2"] is inst2
        setup_instances()


# ===========================================================================
# cleanup_all_browsers
# ===========================================================================


class TestCleanupAllBrowsers:
    """Unit tests for cleanup_all_browsers."""

    @pytest.mark.asyncio
    async def test_cleanup_all_removes_all(self):
        """cleanup_all_browsers should close all instances."""
        setup_instances()
        for i in range(3):
            _browser_instances[f"s{i}"] = make_mock_instance(f"s{i}")

        # We need to mock the global _browser and _playwright_instance
        with patch("tools.browser_tool._browser", None), \
             patch("tools.browser_tool._playwright_instance", None):
            await cleanup_all_browsers()

        assert len(_browser_instances) == 0
        setup_instances()

    @pytest.mark.asyncio
    async def test_cleanup_empty_is_safe(self):
        """cleanup_all_browsers with no instances should be safe."""
        setup_instances()
        with patch("tools.browser_tool._browser", None), \
             patch("tools.browser_tool._playwright_instance", None):
            await cleanup_all_browsers()
        setup_instances()


# ===========================================================================
# Tool function wrappers
# ===========================================================================


class TestToolFunctionWrappers:
    """Unit tests for browser_navigate, browser_click, etc."""

    @pytest.mark.asyncio
    async def test_browser_navigate_returns_status(self):
        """browser_navigate should return status dict."""
        mock_inst = make_mock_instance("s1")
        with patch("tools.browser_tool.get_session_browser", return_value=mock_inst):
            result = await browser_navigate("s1", "https://example.com")

        assert result == {"status": "navigated", "url": "https://example.com"}

    @pytest.mark.asyncio
    async def test_browser_click_returns_status(self):
        """browser_click should return status dict."""
        mock_inst = make_mock_instance("s1")
        with patch("tools.browser_tool.get_session_browser", return_value=mock_inst):
            result = await browser_click("s1", "#btn")

        assert result == {"status": "clicked", "selector": "#btn"}

    @pytest.mark.asyncio
    async def test_browser_screenshot_returns_base64(self):
        """browser_screenshot should return base64-encoded string."""
        mock_inst = make_mock_instance("s1")
        with patch("tools.browser_tool.get_session_browser", return_value=mock_inst):
            result = await browser_screenshot("s1")

        assert isinstance(result, str)
        # Should be valid base64
        decoded = base64.b64decode(result)
        assert len(decoded) > 0

    @pytest.mark.asyncio
    async def test_browser_fill_form_returns_status(self):
        """browser_fill_form should return status dict with value_length."""
        mock_inst = make_mock_instance("s1")
        with patch("tools.browser_tool.get_session_browser", return_value=mock_inst):
            result = await browser_fill_form("s1", "#name", "Alice")

        assert result["status"] == "filled"
        assert result["selector"] == "#name"
        assert result["value_length"] == 5

    @pytest.mark.asyncio
    async def test_browser_execute_js_returns_result(self):
        """browser_execute_js should return JS evaluation result."""
        mock_inst = make_mock_instance("s1")
        mock_inst.page.evaluate.return_value = 42
        # execute_js wraps asyncio.wait_for around page.evaluate
        with patch("tools.browser_tool.get_session_browser", return_value=mock_inst):
            result = await browser_execute_js("s1", "1+1")

        assert result == 42


# ===========================================================================
# Configuration constants
# ===========================================================================


class TestBrowserConstants:
    """Unit tests for configuration constants."""

    def test_max_instances(self):
        assert MAX_BROWSER_INSTANCES == 3

    def test_default_timeout(self):
        assert DEFAULT_TIMEOUT_MS == 30000

    def test_default_viewport(self):
        assert DEFAULT_VIEWPORT["width"] == 1280
        assert DEFAULT_VIEWPORT["height"] == 720
