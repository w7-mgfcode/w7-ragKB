"""Unit tests for browser tool functionality.

Tests cover:
- Browser instance creation and management
- Navigation operations
- Element interaction (click, fill)
- Screenshot capture
- JavaScript execution
- Timeout enforcement
- Instance limit enforcement
- Cleanup on session end
"""

import asyncio
import base64
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from tools.browser_tool import (
    BrowserInstance,
    browser_navigate,
    browser_click,
    browser_screenshot,
    browser_fill_form,
    browser_execute_js,
    get_session_browser,
    close_session_browser,
    cleanup_all_browsers,
    BrowserToolError,
    BrowserInstanceLimitError,
    BrowserTimeoutError,
    ElementNotFoundError,
    MAX_BROWSER_INSTANCES,
    _browser_instances,
)


@pytest.fixture
def mock_page():
    """Create a mock Playwright page."""
    page = AsyncMock()
    page.goto = AsyncMock()
    page.click = AsyncMock()
    page.fill = AsyncMock()
    page.screenshot = AsyncMock(return_value=b"fake_screenshot_data")
    page.evaluate = AsyncMock(return_value="test_result")
    page.query_selector = AsyncMock()
    return page


@pytest.fixture
def mock_context(mock_page):
    """Create a mock Playwright browser context."""
    context = AsyncMock()
    context.new_page = AsyncMock(return_value=mock_page)
    context.close = AsyncMock()
    return context


@pytest.fixture
def mock_browser(mock_context):
    """Create a mock Playwright browser."""
    browser = AsyncMock()
    browser.new_context = AsyncMock(return_value=mock_context)
    browser.close = AsyncMock()
    return browser


@pytest.fixture
def mock_playwright(mock_browser):
    """Create a mock Playwright instance."""
    playwright = AsyncMock()
    playwright.chromium.launch = AsyncMock(return_value=mock_browser)
    playwright.stop = AsyncMock()
    return playwright


@pytest.fixture(autouse=True)
async def cleanup_browser_instances():
    """Clean up browser instances after each test."""
    yield
    # Clear the global browser instances dict
    _browser_instances.clear()
    # Reset module-level variables
    import tools.browser_tool as bt
    bt._browser = None
    bt._playwright_instance = None


class TestBrowserInstance:
    """Tests for BrowserInstance class."""
    
    @pytest.mark.asyncio
    async def test_navigate_success(self, mock_context, mock_page):
        """Test successful navigation to a URL."""
        instance = BrowserInstance("test_session", mock_context, mock_page)
        
        await instance.navigate("https://example.com")
        
        mock_page.goto.assert_called_once()
        call_args = mock_page.goto.call_args
        assert call_args[0][0] == "https://example.com"
        assert call_args[1]["wait_until"] == "domcontentloaded"
    
    @pytest.mark.asyncio
    async def test_navigate_timeout(self, mock_context, mock_page):
        """Test navigation timeout handling."""
        from playwright.async_api import TimeoutError as PlaywrightTimeoutError
        
        mock_page.goto.side_effect = PlaywrightTimeoutError("Navigation timeout")
        instance = BrowserInstance("test_session", mock_context, mock_page)
        
        with pytest.raises(BrowserTimeoutError) as exc_info:
            await instance.navigate("https://example.com")
        
        assert "timed out" in str(exc_info.value).lower()
    
    @pytest.mark.asyncio
    async def test_click_success(self, mock_context, mock_page):
        """Test successful element click."""
        instance = BrowserInstance("test_session", mock_context, mock_page)
        
        await instance.click("#submit-button")
        
        mock_page.click.assert_called_once_with("#submit-button", timeout=30000)
    
    @pytest.mark.asyncio
    async def test_click_element_not_found(self, mock_context, mock_page):
        """Test click when element is not found."""
        mock_page.click.side_effect = Exception("selector not found")
        instance = BrowserInstance("test_session", mock_context, mock_page)
        
        with pytest.raises(ElementNotFoundError) as exc_info:
            await instance.click("#nonexistent")
        
        assert "#nonexistent" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_fill_form_success(self, mock_context, mock_page):
        """Test successful form field filling."""
        instance = BrowserInstance("test_session", mock_context, mock_page)
        
        await instance.fill_form("#email", "test@example.com")
        
        mock_page.fill.assert_called_once_with("#email", "test@example.com", timeout=30000)
    
    @pytest.mark.asyncio
    async def test_screenshot_full_page(self, mock_context, mock_page):
        """Test full page screenshot capture."""
        instance = BrowserInstance("test_session", mock_context, mock_page)
        
        screenshot_bytes = await instance.screenshot(full_page=True)
        
        assert screenshot_bytes == b"fake_screenshot_data"
        mock_page.screenshot.assert_called_once_with(full_page=True)
    
    @pytest.mark.asyncio
    async def test_screenshot_element(self, mock_context, mock_page):
        """Test element-specific screenshot capture."""
        mock_element = AsyncMock()
        mock_element.screenshot = AsyncMock(return_value=b"element_screenshot")
        mock_page.query_selector.return_value = mock_element
        
        instance = BrowserInstance("test_session", mock_context, mock_page)
        
        screenshot_bytes = await instance.screenshot(selector="#target")
        
        assert screenshot_bytes == b"element_screenshot"
        mock_page.query_selector.assert_called_once_with("#target")
        mock_element.screenshot.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_screenshot_element_not_found(self, mock_context, mock_page):
        """Test screenshot when element selector doesn't match."""
        mock_page.query_selector.return_value = None
        instance = BrowserInstance("test_session", mock_context, mock_page)
        
        with pytest.raises(ElementNotFoundError) as exc_info:
            await instance.screenshot(selector="#nonexistent")
        
        assert "#nonexistent" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_execute_js_success(self, mock_context, mock_page):
        """Test successful JavaScript execution."""
        mock_page.evaluate.return_value = "window.location.href"
        instance = BrowserInstance("test_session", mock_context, mock_page)
        
        result = await instance.execute_js("window.location.href")
        
        assert result == "window.location.href"
        mock_page.evaluate.assert_called_once_with("window.location.href")
    
    @pytest.mark.asyncio
    async def test_execute_js_timeout(self, mock_context, mock_page):
        """Test JavaScript execution timeout."""
        async def slow_evaluate(script):
            await asyncio.sleep(100)  # Simulate slow execution
            return "result"
        
        mock_page.evaluate.side_effect = slow_evaluate
        instance = BrowserInstance("test_session", mock_context, mock_page)
        
        with pytest.raises(BrowserTimeoutError) as exc_info:
            await instance.execute_js("slow_script()", timeout_ms=100)
        
        assert "timed out" in str(exc_info.value).lower()
    
    @pytest.mark.asyncio
    async def test_close(self, mock_context, mock_page):
        """Test browser instance cleanup."""
        instance = BrowserInstance("test_session", mock_context, mock_page)
        
        await instance.close()
        
        mock_context.close.assert_called_once()


class TestBrowserManagement:
    """Tests for browser instance management."""
    
    @pytest.mark.asyncio
    async def test_get_session_browser_creates_new_instance(
        self,
        mock_playwright,
        mock_browser,
        mock_context,
        mock_page,
    ):
        """Test that get_session_browser creates a new instance for new session."""
        with patch("tools.browser_tool.async_playwright") as mock_ap:
            mock_ap.return_value.__aenter__.return_value = mock_playwright
            
            instance = await get_session_browser("session1")
            
            assert instance.session_id == "session1"
            assert "session1" in _browser_instances
            mock_browser.new_context.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_session_browser_reuses_existing_instance(
        self,
        mock_playwright,
        mock_browser,
        mock_context,
        mock_page,
    ):
        """Test that get_session_browser reuses existing instance for same session."""
        with patch("tools.browser_tool.async_playwright") as mock_ap:
            mock_ap.return_value.__aenter__.return_value = mock_playwright
            
            instance1 = await get_session_browser("session1")
            instance2 = await get_session_browser("session1")
            
            assert instance1 is instance2
            # Should only create context once
            assert mock_browser.new_context.call_count == 1
    
    @pytest.mark.asyncio
    async def test_browser_instance_limit_enforcement(
        self,
        mock_playwright,
        mock_browser,
        mock_context,
        mock_page,
    ):
        """Test that browser instance limit is enforced."""
        with patch("tools.browser_tool.async_playwright") as mock_ap:
            mock_ap.return_value.__aenter__.return_value = mock_playwright
            
            # Create MAX_BROWSER_INSTANCES instances
            for i in range(MAX_BROWSER_INSTANCES):
                await get_session_browser(f"session{i}")
            
            # Attempting to create one more should fail
            with pytest.raises(BrowserInstanceLimitError) as exc_info:
                await get_session_browser("session_overflow")
            
            assert str(MAX_BROWSER_INSTANCES) in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_close_session_browser(
        self,
        mock_playwright,
        mock_browser,
        mock_context,
        mock_page,
    ):
        """Test closing a session's browser instance."""
        with patch("tools.browser_tool.async_playwright") as mock_ap:
            mock_ap.return_value.__aenter__.return_value = mock_playwright
            
            await get_session_browser("session1")
            assert "session1" in _browser_instances
            
            await close_session_browser("session1")
            
            assert "session1" not in _browser_instances
            mock_context.close.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_close_nonexistent_session_browser(self):
        """Test closing a browser for a session that doesn't exist."""
        # Should not raise an error
        await close_session_browser("nonexistent_session")
    
    @pytest.mark.asyncio
    async def test_cleanup_all_browsers(
        self,
        mock_playwright,
        mock_browser,
        mock_context,
        mock_page,
    ):
        """Test cleanup of all browser instances."""
        with patch("tools.browser_tool.async_playwright") as mock_ap:
            mock_ap.return_value.__aenter__.return_value = mock_playwright
            
            # Create multiple instances
            await get_session_browser("session1")
            await get_session_browser("session2")
            
            assert len(_browser_instances) == 2
            
            await cleanup_all_browsers()
            
            assert len(_browser_instances) == 0
            # All contexts should be closed
            assert mock_context.close.call_count == 2
            mock_browser.close.assert_called_once()
            mock_playwright.stop.assert_called_once()


class TestBrowserToolFunctions:
    """Tests for browser tool functions exposed to the agent."""
    
    @pytest.mark.asyncio
    async def test_browser_navigate(
        self,
        mock_playwright,
        mock_browser,
        mock_context,
        mock_page,
    ):
        """Test browser_navigate tool function."""
        with patch("tools.browser_tool.async_playwright") as mock_ap:
            mock_ap.return_value.__aenter__.return_value = mock_playwright
            
            result = await browser_navigate("session1", "https://example.com")
            
            assert result["status"] == "navigated"
            assert result["url"] == "https://example.com"
            mock_page.goto.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_browser_click(
        self,
        mock_playwright,
        mock_browser,
        mock_context,
        mock_page,
    ):
        """Test browser_click tool function."""
        with patch("tools.browser_tool.async_playwright") as mock_ap:
            mock_ap.return_value.__aenter__.return_value = mock_playwright
            
            result = await browser_click("session1", "#button")
            
            assert result["status"] == "clicked"
            assert result["selector"] == "#button"
            mock_page.click.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_browser_screenshot(
        self,
        mock_playwright,
        mock_browser,
        mock_context,
        mock_page,
    ):
        """Test browser_screenshot tool function."""
        with patch("tools.browser_tool.async_playwright") as mock_ap:
            mock_ap.return_value.__aenter__.return_value = mock_playwright
            
            result = await browser_screenshot("session1")
            
            # Should return base64-encoded string
            assert isinstance(result, str)
            # Verify it's valid base64
            decoded = base64.b64decode(result)
            assert decoded == b"fake_screenshot_data"
    
    @pytest.mark.asyncio
    async def test_browser_fill_form(
        self,
        mock_playwright,
        mock_browser,
        mock_context,
        mock_page,
    ):
        """Test browser_fill_form tool function."""
        with patch("tools.browser_tool.async_playwright") as mock_ap:
            mock_ap.return_value.__aenter__.return_value = mock_playwright
            
            result = await browser_fill_form("session1", "#email", "test@example.com")
            
            assert result["status"] == "filled"
            assert result["selector"] == "#email"
            assert result["value_length"] == len("test@example.com")
            mock_page.fill.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_browser_execute_js(
        self,
        mock_playwright,
        mock_browser,
        mock_context,
        mock_page,
    ):
        """Test browser_execute_js tool function."""
        with patch("tools.browser_tool.async_playwright") as mock_ap:
            mock_ap.return_value.__aenter__.return_value = mock_playwright
            mock_page.evaluate.return_value = "https://example.com"
            
            result = await browser_execute_js("session1", "window.location.href")
            
            assert result == "https://example.com"
            mock_page.evaluate.assert_called_once_with("window.location.href")


class TestErrorHandling:
    """Tests for error handling and edge cases."""
    
    @pytest.mark.asyncio
    async def test_navigate_with_invalid_url(
        self,
        mock_playwright,
        mock_browser,
        mock_context,
        mock_page,
    ):
        """Test navigation with invalid URL."""
        with patch("tools.browser_tool.async_playwright") as mock_ap:
            mock_ap.return_value.__aenter__.return_value = mock_playwright
            mock_page.goto.side_effect = Exception("Invalid URL")
            
            with pytest.raises(BrowserToolError) as exc_info:
                await browser_navigate("session1", "not-a-valid-url")
            
            assert "Failed to navigate" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_concurrent_browser_operations(
        self,
        mock_playwright,
        mock_browser,
        mock_context,
        mock_page,
    ):
        """Test concurrent operations on different browser instances."""
        with patch("tools.browser_tool.async_playwright") as mock_ap:
            mock_ap.return_value.__aenter__.return_value = mock_playwright
            
            # Create multiple instances concurrently
            tasks = [
                browser_navigate("session1", "https://example1.com"),
                browser_navigate("session2", "https://example2.com"),
            ]
            
            results = await asyncio.gather(*tasks)
            
            assert len(results) == 2
            assert results[0]["url"] == "https://example1.com"
            assert results[1]["url"] == "https://example2.com"
