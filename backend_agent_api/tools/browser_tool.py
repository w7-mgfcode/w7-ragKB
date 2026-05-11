"""Browser automation tool for web interaction.

This module implements browser automation capabilities using Playwright,
enabling the AI agent to:
- Navigate to URLs
- Click elements
- Fill forms
- Capture screenshots
- Execute JavaScript

Each session maintains its own browser instance for state isolation.
Browser instances are automatically cleaned up when sessions end.
A maximum of 3 concurrent browser instances is enforced to manage resources.
"""

import asyncio
import base64
import logging
from typing import Any, Dict, Optional

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    TimeoutError as PlaywrightTimeoutError,
    async_playwright,
)

logger = logging.getLogger(__name__)

# Global browser instance management
_browser_instances: Dict[str, "BrowserInstance"] = {}
_playwright_instance: Optional[Playwright] = None
_browser: Optional[Browser] = None
_lock = asyncio.Lock()

# Configuration
MAX_BROWSER_INSTANCES = 3
DEFAULT_TIMEOUT_MS = 30000  # 30 seconds
DEFAULT_VIEWPORT = {"width": 1280, "height": 720}


class BrowserToolError(Exception):
    """Base exception for browser tool errors."""
    pass


class BrowserInstanceLimitError(BrowserToolError):
    """Raised when maximum browser instances limit is exceeded."""
    pass


class BrowserTimeoutError(BrowserToolError):
    """Raised when browser operation times out."""
    pass


class ElementNotFoundError(BrowserToolError):
    """Raised when element selector does not match any elements."""
    pass


class BrowserCrashedError(BrowserToolError):
    """Raised when browser instance crashes."""
    pass


class BrowserInstance:
    """Represents a browser instance for a specific session.
    
    Each session gets its own browser context and page to maintain
    isolation between different conversations.
    """
    
    def __init__(
        self,
        session_id: str,
        context: BrowserContext,
        page: Page,
    ):
        self.session_id = session_id
        self.context = context
        self.page = page
        self.created_at = asyncio.get_event_loop().time()
        self.last_used_at = self.created_at
    
    async def navigate(self, url: str, timeout_ms: int = DEFAULT_TIMEOUT_MS) -> None:
        """Navigate to a URL.
        
        Args:
            url: URL to navigate to
            timeout_ms: Navigation timeout in milliseconds
            
        Raises:
            BrowserTimeoutError: If navigation times out
        """
        try:
            self.last_used_at = asyncio.get_event_loop().time()
            await self.page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
            logger.info(f"Session {self.session_id} navigated to {url}")
        except PlaywrightTimeoutError as e:
            logger.error(f"Navigation timeout for session {self.session_id}: {url}")
            raise BrowserTimeoutError(f"Navigation to {url} timed out after {timeout_ms}ms") from e
        except Exception as e:
            logger.error(f"Navigation error for session {self.session_id}: {e}")
            raise BrowserToolError(f"Failed to navigate to {url}: {str(e)}") from e
    
    async def click(self, selector: str, timeout_ms: int = DEFAULT_TIMEOUT_MS) -> None:
        """Click an element by CSS selector.
        
        Args:
            selector: CSS selector for the element
            timeout_ms: Operation timeout in milliseconds
            
        Raises:
            ElementNotFoundError: If selector does not match any elements
            BrowserTimeoutError: If operation times out
        """
        try:
            self.last_used_at = asyncio.get_event_loop().time()
            await self.page.click(selector, timeout=timeout_ms)
            logger.info(f"Session {self.session_id} clicked element: {selector}")
        except PlaywrightTimeoutError as e:
            logger.error(f"Click timeout for session {self.session_id}: {selector}")
            raise BrowserTimeoutError(f"Click on {selector} timed out after {timeout_ms}ms") from e
        except Exception as e:
            logger.error(f"Click error for session {self.session_id}: {e}")
            if "selector" in str(e).lower() or "not found" in str(e).lower():
                raise ElementNotFoundError(f"Element not found: {selector}") from e
            raise BrowserToolError(f"Failed to click {selector}: {str(e)}") from e
    
    async def fill_form(
        self,
        selector: str,
        value: str,
        timeout_ms: int = DEFAULT_TIMEOUT_MS,
    ) -> None:
        """Fill a form field by CSS selector.
        
        Args:
            selector: CSS selector for the form field
            value: Value to fill
            timeout_ms: Operation timeout in milliseconds
            
        Raises:
            ElementNotFoundError: If selector does not match any elements
            BrowserTimeoutError: If operation times out
        """
        try:
            self.last_used_at = asyncio.get_event_loop().time()
            await self.page.fill(selector, value, timeout=timeout_ms)
            logger.info(
                f"Session {self.session_id} filled form field: {selector} "
                f"(value length: {len(value)})"
            )
        except PlaywrightTimeoutError as e:
            logger.error(f"Fill timeout for session {self.session_id}: {selector}")
            raise BrowserTimeoutError(f"Fill on {selector} timed out after {timeout_ms}ms") from e
        except Exception as e:
            logger.error(f"Fill error for session {self.session_id}: {e}")
            if "selector" in str(e).lower() or "not found" in str(e).lower():
                raise ElementNotFoundError(f"Element not found: {selector}") from e
            raise BrowserToolError(f"Failed to fill {selector}: {str(e)}") from e
    
    async def screenshot(
        self,
        selector: Optional[str] = None,
        full_page: bool = False,
    ) -> bytes:
        """Capture a screenshot.
        
        Args:
            selector: Optional CSS selector to screenshot specific element
            full_page: Whether to capture full scrollable page
            
        Returns:
            Screenshot as PNG bytes
            
        Raises:
            ElementNotFoundError: If selector does not match any elements
        """
        try:
            self.last_used_at = asyncio.get_event_loop().time()
            
            if selector:
                element = await self.page.query_selector(selector)
                if not element:
                    raise ElementNotFoundError(f"Element not found: {selector}")
                screenshot_bytes = await element.screenshot()
                logger.info(f"Session {self.session_id} captured element screenshot: {selector}")
            else:
                screenshot_bytes = await self.page.screenshot(full_page=full_page)
                logger.info(
                    f"Session {self.session_id} captured "
                    f"{'full page' if full_page else 'viewport'} screenshot"
                )
            
            return screenshot_bytes
        except ElementNotFoundError:
            raise
        except Exception as e:
            logger.error(f"Screenshot error for session {self.session_id}: {e}")
            raise BrowserToolError(f"Failed to capture screenshot: {str(e)}") from e
    
    async def execute_js(
        self,
        script: str,
        timeout_ms: int = DEFAULT_TIMEOUT_MS,
    ) -> Any:
        """Execute JavaScript in the browser context.
        
        Args:
            script: JavaScript code to execute
            timeout_ms: Execution timeout in milliseconds
            
        Returns:
            Result of the JavaScript expression
            
        Raises:
            BrowserTimeoutError: If execution times out
        """
        try:
            self.last_used_at = asyncio.get_event_loop().time()
            
            # Wrap in async function with timeout
            result = await asyncio.wait_for(
                self.page.evaluate(script),
                timeout=timeout_ms / 1000.0,
            )
            
            logger.info(
                f"Session {self.session_id} executed JavaScript "
                f"(script length: {len(script)})"
            )
            return result
        except asyncio.TimeoutError as e:
            logger.error(f"JavaScript execution timeout for session {self.session_id}")
            raise BrowserTimeoutError(
                f"JavaScript execution timed out after {timeout_ms}ms"
            ) from e
        except Exception as e:
            logger.error(f"JavaScript execution error for session {self.session_id}: {e}")
            raise BrowserToolError(f"Failed to execute JavaScript: {str(e)}") from e
    
    async def close(self) -> None:
        """Close the browser context and page."""
        try:
            await self.context.close()
            logger.info(f"Closed browser instance for session {self.session_id}")
        except Exception as e:
            logger.error(f"Error closing browser instance for session {self.session_id}: {e}")


async def _ensure_browser_initialized() -> Browser:
    """Ensure the shared browser instance is initialized.
    
    Returns:
        Shared Browser instance
    """
    global _playwright_instance, _browser
    
    if _browser is not None:
        return _browser
    
    async with _lock:
        # Double-check after acquiring lock
        if _browser is not None:
            return _browser
        
        logger.info("Initializing shared Playwright browser")
        _playwright_instance = await async_playwright().start()
        _browser = await _playwright_instance.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
            ],
        )
        logger.info("Playwright browser initialized successfully")
        
        return _browser


async def get_session_browser(session_id: str) -> BrowserInstance:
    """Get or create a browser instance for a session.
    
    Args:
        session_id: Session identifier
        
    Returns:
        BrowserInstance for the session
        
    Raises:
        BrowserInstanceLimitError: If max instances limit is exceeded
    """
    async with _lock:
        # Return existing instance if available
        if session_id in _browser_instances:
            return _browser_instances[session_id]
        
        # Check instance limit
        if len(_browser_instances) >= MAX_BROWSER_INSTANCES:
            logger.error(
                f"Browser instance limit reached ({MAX_BROWSER_INSTANCES}). "
                f"Cannot create instance for session {session_id}"
            )
            raise BrowserInstanceLimitError(
                f"Maximum browser instances ({MAX_BROWSER_INSTANCES}) reached. "
                "Please close other browser sessions first."
            )
        
        # Initialize shared browser if needed
        browser = await _ensure_browser_initialized()
        
        # Create new context and page
        context = await browser.new_context(viewport=DEFAULT_VIEWPORT)
        page = await context.new_page()
        
        # Create and store instance
        instance = BrowserInstance(session_id, context, page)
        _browser_instances[session_id] = instance
        
        logger.info(
            f"Created browser instance for session {session_id} "
            f"({len(_browser_instances)}/{MAX_BROWSER_INSTANCES} instances active)"
        )
        
        return instance


async def close_session_browser(session_id: str) -> None:
    """Close and remove a browser instance for a session.
    
    Args:
        session_id: Session identifier
    """
    async with _lock:
        if session_id not in _browser_instances:
            logger.warning(f"No browser instance found for session {session_id}")
            return
        
        instance = _browser_instances.pop(session_id)
        await instance.close()
        
        logger.info(
            f"Removed browser instance for session {session_id} "
            f"({len(_browser_instances)}/{MAX_BROWSER_INSTANCES} instances remaining)"
        )


async def cleanup_all_browsers() -> None:
    """Close all browser instances and cleanup resources.
    
    This should be called during application shutdown.
    """
    global _playwright_instance, _browser, _browser_instances
    
    async with _lock:
        # Close all session instances
        for session_id in list(_browser_instances.keys()):
            instance = _browser_instances.pop(session_id)
            await instance.close()
        
        # Close shared browser
        if _browser is not None:
            await _browser.close()
            _browser = None
        
        # Stop playwright
        if _playwright_instance is not None:
            await _playwright_instance.stop()
            _playwright_instance = None
        
        logger.info("All browser instances cleaned up")


# Tool functions for Pydantic AI agent integration


async def browser_navigate(session_id: str, url: str) -> Dict[str, Any]:
    """Navigate browser to URL.
    
    Args:
        session_id: Session identifier
        url: URL to navigate to
        
    Returns:
        Dictionary with status and URL
    """
    browser = await get_session_browser(session_id)
    await browser.navigate(url)
    return {"status": "navigated", "url": url}


async def browser_click(session_id: str, selector: str) -> Dict[str, Any]:
    """Click element by CSS selector.
    
    Args:
        session_id: Session identifier
        selector: CSS selector for the element
        
    Returns:
        Dictionary with status and selector
    """
    browser = await get_session_browser(session_id)
    await browser.click(selector)
    return {"status": "clicked", "selector": selector}


async def browser_screenshot(
    session_id: str,
    selector: Optional[str] = None,
    full_page: bool = False,
) -> str:
    """Capture screenshot and return as base64-encoded PNG.
    
    Args:
        session_id: Session identifier
        selector: Optional CSS selector to screenshot specific element
        full_page: Whether to capture full scrollable page
        
    Returns:
        Base64-encoded PNG image
    """
    browser = await get_session_browser(session_id)
    screenshot_bytes = await browser.screenshot(selector=selector, full_page=full_page)
    return base64.b64encode(screenshot_bytes).decode("utf-8")


async def browser_fill_form(
    session_id: str,
    selector: str,
    value: str,
) -> Dict[str, Any]:
    """Fill form field by CSS selector.
    
    Args:
        session_id: Session identifier
        selector: CSS selector for the form field
        value: Value to fill
        
    Returns:
        Dictionary with status and selector
    """
    browser = await get_session_browser(session_id)
    await browser.fill_form(selector, value)
    return {"status": "filled", "selector": selector, "value_length": len(value)}


async def browser_execute_js(session_id: str, script: str) -> Any:
    """Execute JavaScript in browser context.
    
    Args:
        session_id: Session identifier
        script: JavaScript code to execute
        
    Returns:
        Result of the JavaScript expression
    """
    browser = await get_session_browser(session_id)
    result = await browser.execute_js(script)
    return result
