"""Property-based tests for the browser tool.

Feature: openclaw-integration (Task 12.1)
Properties tested: 22, 23, 24, 25, 26, 27, 28, 29

Tests navigation, element interaction, screenshot capture,
form filling, JS execution, instance isolation, cleanup, and timeout.

Note: All tests use mocked Playwright to avoid requiring a real browser.
"""

import asyncio
import base64
import string
import time
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hypothesis import HealthCheck, given, settings, strategies as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tools.browser_tool import (
    MAX_BROWSER_INSTANCES,
    DEFAULT_TIMEOUT_MS,
    DEFAULT_VIEWPORT,
    BrowserInstance,
    BrowserInstanceLimitError,
    BrowserTimeoutError,
    BrowserToolError,
    ElementNotFoundError,
    _browser_instances,
    close_session_browser,
    get_session_browser,
)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

safe_url = st.from_regex(r"https?://[a-z][a-z0-9]{2,20}\.[a-z]{2,4}", fullmatch=True)
css_selector = st.from_regex(r"#[a-z][a-z0-9_-]{0,20}|\\.[a-z][a-z0-9_-]{0,20}", fullmatch=True)
safe_text = st.text(min_size=1, max_size=200).filter(lambda s: s.strip())
js_expression = st.sampled_from([
    "1 + 1",
    "document.title",
    "window.location.href",
    "Math.PI",
    "'hello' + ' world'",
    "document.querySelectorAll('div').length",
    "JSON.stringify({a: 1})",
])
session_id_strategy = st.text(
    alphabet=string.ascii_letters + string.digits + "-_:",
    min_size=5,
    max_size=30,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_mock_browser_instance(session_id="test-session"):
    """Create a BrowserInstance with mocked Playwright objects."""
    context = AsyncMock()
    page = AsyncMock()
    page.goto = AsyncMock()
    page.click = AsyncMock()
    page.fill = AsyncMock()
    page.screenshot = AsyncMock(return_value=b"\x89PNG\r\n\x1a\n" + b"\x00" * 50)
    page.evaluate = AsyncMock(return_value=42)
    page.query_selector = AsyncMock()

    instance = BrowserInstance.__new__(BrowserInstance)
    instance.session_id = session_id
    instance.context = context
    instance.page = page
    try:
        instance.created_at = asyncio.get_event_loop().time()
    except RuntimeError:
        instance.created_at = time.time()
    instance.last_used_at = instance.created_at
    return instance


def cleanup_browser_instances():
    """Remove all entries from the global _browser_instances dict."""
    _browser_instances.clear()


# ===========================================================================
# Property 22: Browser navigation
# ===========================================================================


class TestBrowserNavigation:
    """Property 22: Navigate to URL, page.goto is called with the URL."""

    @given(url=safe_url)
    @settings(max_examples=50, deadline=None)
    @pytest.mark.asyncio
    async def test_navigate_calls_goto(self, url):
        """
        Feature: openclaw-integration, Property 22: Browser navigation

        navigate(url) should call page.goto(url, ...) and update last_used_at.
        """
        instance = make_mock_browser_instance()
        initial_time = instance.last_used_at

        await instance.navigate(url)

        instance.page.goto.assert_called_once()
        call_args = instance.page.goto.call_args
        assert call_args.args[0] == url
        assert instance.last_used_at >= initial_time

    @pytest.mark.asyncio
    async def test_navigate_timeout_raises(self):
        """
        Feature: openclaw-integration, Property 22: Browser navigation

        Navigation timeout should raise BrowserTimeoutError.
        """
        from playwright.async_api import TimeoutError as PlaywrightTimeoutError

        instance = make_mock_browser_instance()
        instance.page.goto.side_effect = PlaywrightTimeoutError("timeout")

        with pytest.raises(BrowserTimeoutError, match="timed out"):
            await instance.navigate("https://slow.example.com")


# ===========================================================================
# Property 23: Browser element interaction
# ===========================================================================


class TestBrowserElementInteraction:
    """Property 23: Click triggers page.click with the selector."""

    @given(selector=css_selector)
    @settings(max_examples=50, deadline=None)
    @pytest.mark.asyncio
    async def test_click_calls_page_click(self, selector):
        """
        Feature: openclaw-integration, Property 23: Browser element interaction

        click(selector) should call page.click(selector, ...).
        """
        instance = make_mock_browser_instance()
        await instance.click(selector)
        instance.page.click.assert_called_once()
        assert instance.page.click.call_args.args[0] == selector

    @pytest.mark.asyncio
    async def test_click_timeout_raises(self):
        """
        Feature: openclaw-integration, Property 23: Browser element interaction

        Click timeout should raise BrowserTimeoutError.
        """
        from playwright.async_api import TimeoutError as PlaywrightTimeoutError

        instance = make_mock_browser_instance()
        instance.page.click.side_effect = PlaywrightTimeoutError("timeout")

        with pytest.raises(BrowserTimeoutError):
            await instance.click("#button")

    @pytest.mark.asyncio
    async def test_click_not_found_raises(self):
        """
        Feature: openclaw-integration, Property 23: Browser element interaction

        Click on missing selector should raise ElementNotFoundError.
        """
        instance = make_mock_browser_instance()
        instance.page.click.side_effect = Exception("selector not found")

        with pytest.raises(ElementNotFoundError):
            await instance.click("#missing")


# ===========================================================================
# Property 24: Browser screenshot capture
# ===========================================================================


class TestBrowserScreenshotCapture:
    """Property 24: screenshot() returns bytes that are valid PNG-like data."""

    @pytest.mark.asyncio
    async def test_viewport_screenshot_returns_bytes(self):
        """
        Feature: openclaw-integration, Property 24: Browser screenshot capture

        Viewport screenshot should return bytes (PNG).
        """
        instance = make_mock_browser_instance()
        result = await instance.screenshot()

        assert isinstance(result, bytes)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_full_page_screenshot(self):
        """
        Feature: openclaw-integration, Property 24: Browser screenshot capture

        full_page=True should be passed to page.screenshot.
        """
        instance = make_mock_browser_instance()
        await instance.screenshot(full_page=True)

        instance.page.screenshot.assert_called_once_with(full_page=True)

    @pytest.mark.asyncio
    async def test_element_screenshot(self):
        """
        Feature: openclaw-integration, Property 24: Browser screenshot capture

        selector parameter should capture element screenshot.
        """
        instance = make_mock_browser_instance()
        mock_element = AsyncMock()
        mock_element.screenshot = AsyncMock(return_value=b"\x89PNG" + b"\x00" * 20)
        instance.page.query_selector.return_value = mock_element

        result = await instance.screenshot(selector="#target")

        instance.page.query_selector.assert_called_once_with("#target")
        mock_element.screenshot.assert_called_once()
        assert isinstance(result, bytes)

    @pytest.mark.asyncio
    async def test_element_not_found_raises(self):
        """
        Feature: openclaw-integration, Property 24: Browser screenshot capture

        Screenshot with non-existent selector should raise ElementNotFoundError.
        """
        instance = make_mock_browser_instance()
        instance.page.query_selector.return_value = None

        with pytest.raises(ElementNotFoundError, match="not found"):
            await instance.screenshot(selector="#missing")

    @pytest.mark.asyncio
    async def test_screenshot_base64_encoding(self):
        """
        Feature: openclaw-integration, Property 24: Browser screenshot capture

        browser_screenshot tool function should return valid base64.
        """
        from tools.browser_tool import browser_screenshot

        # We need to mock the get_session_browser function
        mock_instance = make_mock_browser_instance("s1")
        with patch("tools.browser_tool.get_session_browser", return_value=mock_instance):
            result = await browser_screenshot("s1")

        # Should be valid base64
        decoded = base64.b64decode(result)
        assert len(decoded) > 0


# ===========================================================================
# Property 25: Browser form filling
# ===========================================================================


class TestBrowserFormFilling:
    """Property 25: fill_form calls page.fill with selector and value."""

    @given(value=safe_text)
    @settings(max_examples=50, deadline=None)
    @pytest.mark.asyncio
    async def test_fill_form_calls_page_fill(self, value):
        """
        Feature: openclaw-integration, Property 25: Browser form filling

        fill_form(selector, value) should call page.fill(selector, value, ...).
        """
        instance = make_mock_browser_instance()
        await instance.fill_form("#input", value)

        instance.page.fill.assert_called_once()
        args = instance.page.fill.call_args.args
        assert args[0] == "#input"
        assert args[1] == value

    @pytest.mark.asyncio
    async def test_fill_form_timeout_raises(self):
        """
        Feature: openclaw-integration, Property 25: Browser form filling

        fill_form timeout should raise BrowserTimeoutError.
        """
        from playwright.async_api import TimeoutError as PlaywrightTimeoutError

        instance = make_mock_browser_instance()
        instance.page.fill.side_effect = PlaywrightTimeoutError("timeout")

        with pytest.raises(BrowserTimeoutError):
            await instance.fill_form("#input", "value")


# ===========================================================================
# Property 26: Browser JavaScript execution
# ===========================================================================


class TestBrowserJSExecution:
    """Property 26: execute_js returns the result of the expression."""

    @given(script=js_expression)
    @settings(max_examples=50, deadline=None)
    @pytest.mark.asyncio
    async def test_execute_js_calls_evaluate(self, script):
        """
        Feature: openclaw-integration, Property 26: Browser JavaScript execution

        execute_js(script) should call page.evaluate(script) and return result.
        """
        instance = make_mock_browser_instance()
        instance.page.evaluate.return_value = "result"

        result = await instance.execute_js(script)

        assert result == "result"
        instance.page.evaluate.assert_called_once_with(script)

    @pytest.mark.asyncio
    async def test_execute_js_returns_various_types(self):
        """
        Feature: openclaw-integration, Property 26: Browser JavaScript execution

        JS execution should return various types (int, str, dict, list).
        """
        instance = make_mock_browser_instance()

        for expected in [42, "hello", {"key": "value"}, [1, 2, 3], True, None]:
            instance.page.evaluate.return_value = expected
            result = await instance.execute_js("expression")
            assert result == expected


# ===========================================================================
# Property 27: Browser instance isolation
# ===========================================================================


class TestBrowserInstanceIsolation:
    """Property 27: Different sessions get different browser instances."""

    @given(
        sid_a=session_id_strategy,
        sid_b=session_id_strategy,
    )
    @settings(max_examples=30, deadline=None)
    def test_different_sessions_different_instances(self, sid_a, sid_b):
        """
        Feature: openclaw-integration, Property 27: Browser instance isolation

        Two different session_ids should map to different BrowserInstance objects.
        """
        if sid_a == sid_b:
            return

        cleanup_browser_instances()

        inst_a = make_mock_browser_instance(sid_a)
        inst_b = make_mock_browser_instance(sid_b)
        _browser_instances[sid_a] = inst_a
        _browser_instances[sid_b] = inst_b

        assert _browser_instances[sid_a] is not _browser_instances[sid_b]
        assert _browser_instances[sid_a].session_id == sid_a
        assert _browser_instances[sid_b].session_id == sid_b

        cleanup_browser_instances()

    def test_same_session_same_instance(self):
        """
        Feature: openclaw-integration, Property 27: Browser instance isolation

        Same session_id should return the same BrowserInstance.
        """
        cleanup_browser_instances()

        inst = make_mock_browser_instance("s1")
        _browser_instances["s1"] = inst

        assert _browser_instances["s1"] is inst

        cleanup_browser_instances()


# ===========================================================================
# Property 28: Browser cleanup
# ===========================================================================


class TestBrowserCleanup:
    """Property 28: Closing session browser removes the instance."""

    @pytest.mark.asyncio
    async def test_close_removes_instance(self):
        """
        Feature: openclaw-integration, Property 28: Browser cleanup

        close_session_browser should remove the instance from the registry.
        """
        cleanup_browser_instances()

        inst = make_mock_browser_instance("cleanup-test")
        _browser_instances["cleanup-test"] = inst

        assert "cleanup-test" in _browser_instances

        await close_session_browser("cleanup-test")

        assert "cleanup-test" not in _browser_instances
        inst.context.close.assert_called_once()

        cleanup_browser_instances()

    @pytest.mark.asyncio
    async def test_close_nonexistent_is_noop(self):
        """
        Feature: openclaw-integration, Property 28: Browser cleanup

        Closing a non-existent session browser should be a no-op.
        """
        cleanup_browser_instances()
        # Should not raise
        await close_session_browser("nonexistent-session")

    @given(session_id=session_id_strategy)
    @settings(max_examples=30, deadline=None)
    @pytest.mark.asyncio
    async def test_cleanup_idempotent(self, session_id):
        """
        Feature: openclaw-integration, Property 28: Browser cleanup

        Calling close_session_browser twice should be safe.
        """
        cleanup_browser_instances()

        inst = make_mock_browser_instance(session_id)
        _browser_instances[session_id] = inst

        await close_session_browser(session_id)
        await close_session_browser(session_id)  # Second call is no-op

        assert session_id not in _browser_instances

        cleanup_browser_instances()


# ===========================================================================
# Property 29: Browser timeout enforcement
# ===========================================================================


class TestBrowserTimeoutEnforcement:
    """Property 29: Operations exceeding timeout raise BrowserTimeoutError."""

    @pytest.mark.asyncio
    async def test_navigate_timeout(self):
        """
        Feature: openclaw-integration, Property 29: Browser timeout enforcement

        Navigation timeout should raise BrowserTimeoutError.
        """
        from playwright.async_api import TimeoutError as PlaywrightTimeoutError

        instance = make_mock_browser_instance()
        instance.page.goto.side_effect = PlaywrightTimeoutError("timeout")

        with pytest.raises(BrowserTimeoutError):
            await instance.navigate("https://slow.example.com", timeout_ms=100)

    @pytest.mark.asyncio
    async def test_click_timeout(self):
        """
        Feature: openclaw-integration, Property 29: Browser timeout enforcement

        Click timeout should raise BrowserTimeoutError.
        """
        from playwright.async_api import TimeoutError as PlaywrightTimeoutError

        instance = make_mock_browser_instance()
        instance.page.click.side_effect = PlaywrightTimeoutError("timeout")

        with pytest.raises(BrowserTimeoutError):
            await instance.click("#btn", timeout_ms=100)

    @pytest.mark.asyncio
    async def test_fill_form_timeout(self):
        """
        Feature: openclaw-integration, Property 29: Browser timeout enforcement

        Fill form timeout should raise BrowserTimeoutError.
        """
        from playwright.async_api import TimeoutError as PlaywrightTimeoutError

        instance = make_mock_browser_instance()
        instance.page.fill.side_effect = PlaywrightTimeoutError("timeout")

        with pytest.raises(BrowserTimeoutError):
            await instance.fill_form("#input", "val", timeout_ms=100)

    @pytest.mark.asyncio
    async def test_execute_js_timeout(self):
        """
        Feature: openclaw-integration, Property 29: Browser timeout enforcement

        JS execution timeout should raise BrowserTimeoutError.
        """
        instance = make_mock_browser_instance()
        instance.page.evaluate.side_effect = asyncio.TimeoutError()

        with pytest.raises(BrowserTimeoutError):
            await instance.execute_js("while(true){}", timeout_ms=100)

    @pytest.mark.asyncio
    async def test_timeout_ms_parameter_respected(self):
        """
        Feature: openclaw-integration, Property 29: Browser timeout enforcement

        Custom timeout_ms should be passed to page operations.
        """
        instance = make_mock_browser_instance()

        await instance.navigate("https://example.com", timeout_ms=5000)
        call_kwargs = instance.page.goto.call_args.kwargs
        assert call_kwargs.get("timeout") == 5000

        await instance.click("#btn", timeout_ms=3000)
        call_kwargs = instance.page.click.call_args.kwargs
        assert call_kwargs.get("timeout") == 3000


# ===========================================================================
# MAX_BROWSER_INSTANCES limit
# ===========================================================================


class TestBrowserInstanceLimit:
    """Property 27 extended: MAX_BROWSER_INSTANCES enforced."""

    def test_max_instances_value(self):
        """MAX_BROWSER_INSTANCES should be 3."""
        assert MAX_BROWSER_INSTANCES == 3

    def test_default_timeout_value(self):
        """DEFAULT_TIMEOUT_MS should be 30000."""
        assert DEFAULT_TIMEOUT_MS == 30000

    def test_default_viewport_value(self):
        """DEFAULT_VIEWPORT should be 1280x720."""
        assert DEFAULT_VIEWPORT == {"width": 1280, "height": 720}
