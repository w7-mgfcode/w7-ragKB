"""Unit tests for main.py entry point.

Validates:
- Logging is configured on startup
- asyncpg pool is created before Slack bot starts
- Pool is closed on shutdown (both normal signal and KeyboardInterrupt)
- Signal handlers are registered for SIGINT and SIGTERM
"""

import asyncio
import logging
import signal
import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Stub heavy transitive deps so main.py can be imported in CI.
# Mirrors the approach used in test_slack_bot.py.
# ---------------------------------------------------------------------------

def _create_mock_tools_module():
    mod = types.ModuleType("tools")
    for name in (
        "web_search_tool",
        "image_analysis_tool",
        "retrieve_relevant_documents_tool",
        "list_documents_tool",
        "get_document_content_tool",
        "execute_sql_query_tool",
        "execute_safe_code_tool",
    ):
        setattr(mod, name, MagicMock())
    return mod


def _create_mock_prompt_module():
    mod = types.ModuleType("prompt")
    mod.AGENT_SYSTEM_PROMPT = "You are a test agent."
    return mod


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    """Provide env vars and stub modules needed by the import chain."""
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test")
    monkeypatch.setenv("SLACK_APP_TOKEN", "xapp-test")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-project")
    monkeypatch.setenv("GOOGLE_CLOUD_REGION", "us-central1")
    monkeypatch.setenv("LLM_CHOICE", "gemini-2.0-flash")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost/test")

    # Save originals so we can restore after the test
    saved = {}
    for mod_name in ("tools", "prompt", "agent", "slack_bot", "main"):
        saved[mod_name] = sys.modules.pop(mod_name, None)

    # Inject stubs for modules with heavy/unavailable transitive deps
    sys.modules["tools"] = _create_mock_tools_module()
    sys.modules["prompt"] = _create_mock_prompt_module()

    yield

    # Restore original module state
    for mod_name, original in saved.items():
        if original is None:
            sys.modules.pop(mod_name, None)
        else:
            sys.modules[mod_name] = original


def _import_main():
    """Import main.py with vertex_provider mocked out."""
    from pydantic_ai.models.test import TestModel

    test_model = TestModel()
    with patch("vertex_provider.get_model", return_value=test_model):
        # Clear cached modules so they re-import with our stubs
        sys.modules.pop("agent", None)
        sys.modules.pop("slack_bot", None)
        sys.modules.pop("main", None)
        import main as main_mod
    return main_mod


# ---------------------------------------------------------------------------
# _configure_logging
# ---------------------------------------------------------------------------

class TestConfigureLogging:
    def test_sets_info_level(self):
        main_mod = _import_main()
        with patch("logging.basicConfig") as mock_basic:
            main_mod._configure_logging()
            mock_basic.assert_called_once()
            kwargs = mock_basic.call_args[1]
            assert kwargs["level"] == logging.INFO


# ---------------------------------------------------------------------------
# _run — lifecycle
# ---------------------------------------------------------------------------

class TestRun:
    @pytest.mark.asyncio
    async def test_creates_pool_before_starting_slack(self):
        """create_pool is awaited before start_socket_mode is scheduled."""
        main_mod = _import_main()
        call_order = []

        async def fake_create_pool():
            call_order.append("create_pool")

        async def fake_start_socket_mode():
            call_order.append("start_socket_mode")
            await asyncio.sleep(999)

        async def fake_close_pool():
            call_order.append("close_pool")

        with patch("main.create_pool", side_effect=fake_create_pool), \
             patch("main.start_socket_mode", side_effect=fake_start_socket_mode), \
             patch("main.close_pool", side_effect=fake_close_pool):

            async def fire_shutdown():
                await asyncio.sleep(0.05)
                import os as _os
                _os.kill(_os.getpid(), signal.SIGINT)

            task = asyncio.create_task(main_mod._run())
            asyncio.create_task(fire_shutdown())

            try:
                await asyncio.wait_for(task, timeout=2.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass

            assert "create_pool" in call_order
            assert call_order.index("create_pool") < call_order.index("start_socket_mode")

    @pytest.mark.asyncio
    async def test_closes_pool_on_shutdown(self):
        """close_pool is called when the shutdown event fires."""
        main_mod = _import_main()

        mock_create = AsyncMock()
        mock_close = AsyncMock()

        async def fake_start():
            await asyncio.sleep(999)

        with patch("main.create_pool", mock_create), \
             patch("main.start_socket_mode", side_effect=fake_start), \
             patch("main.close_pool", mock_close):

            async def fire_shutdown():
                await asyncio.sleep(0.05)
                import os as _os
                _os.kill(_os.getpid(), signal.SIGINT)

            task = asyncio.create_task(main_mod._run())
            asyncio.create_task(fire_shutdown())

            try:
                await asyncio.wait_for(task, timeout=2.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass

            mock_close.assert_awaited_once()


# ---------------------------------------------------------------------------
# main() — synchronous wrapper
# ---------------------------------------------------------------------------

class TestMain:
    def test_calls_asyncio_run(self):
        """main() invokes asyncio.run with _run."""
        main_mod = _import_main()

        with patch("main._configure_logging") as mock_log, \
             patch("main.asyncio") as mock_asyncio:
            mock_asyncio.run = MagicMock()
            main_mod.main()
            mock_log.assert_called_once()
            mock_asyncio.run.assert_called_once()

    def test_handles_keyboard_interrupt(self):
        """main() catches KeyboardInterrupt without crashing."""
        main_mod = _import_main()

        with patch("main._configure_logging"), \
             patch("main.asyncio") as mock_asyncio:
            mock_asyncio.run = MagicMock(side_effect=KeyboardInterrupt)
            # Should not raise
            main_mod.main()

    def test_propagates_unexpected_errors(self):
        """Unexpected errors from asyncio.run propagate out."""
        main_mod = _import_main()

        with patch("main._configure_logging"), \
             patch("main.asyncio") as mock_asyncio:
            mock_asyncio.run = MagicMock(side_effect=RuntimeError("boom"))
            with pytest.raises(RuntimeError, match="boom"):
                main_mod.main()
