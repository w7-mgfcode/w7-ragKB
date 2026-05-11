"""Tests for the asyncpg-based RAG pipeline docker_entrypoint.

Validates single-run and continuous modes, error handling, and exit codes.
"""

import json
import os
import sys
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from docker_entrypoint import run_single_check, _exit_from_stats


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_pool() -> AsyncMock:
    """Return a mock asyncpg.Pool."""
    pool = AsyncMock()
    pool.close = AsyncMock()
    return pool


def _make_watcher_class(stats: dict = None) -> MagicMock:
    """Return a mock watcher class whose instances have async methods."""
    if stats is None:
        stats = {
            "files_processed": 2,
            "files_deleted": 0,
            "errors": 0,
            "duration": 1.0,
            "initialized": True,
        }
    instance = AsyncMock()
    instance.initialize_state = AsyncMock()
    instance.check_for_changes = AsyncMock(return_value=stats)
    instance.watch_for_changes = AsyncMock()

    cls = MagicMock(return_value=instance)
    return cls, instance


# ---------------------------------------------------------------------------
# run_single_check
# ---------------------------------------------------------------------------

class TestRunSingleCheck:
    @pytest.mark.asyncio
    async def test_local_pipeline_success(self):
        pool = _make_pool()
        watcher_cls, watcher = _make_watcher_class()

        with patch.dict(sys.modules, {}), \
             patch("docker_entrypoint.LocalFileWatcher", watcher_cls, create=True):
            # Patch the import inside run_single_check
            with patch(
                "docker_entrypoint.run_single_check",
                wraps=run_single_check,
            ):
                # We need to mock the dynamic import
                mock_module = MagicMock()
                mock_module.LocalFileWatcher = watcher_cls

                with patch.dict("sys.modules", {"Local_Files.file_watcher": mock_module}):
                    result = await run_single_check(
                        pool, "local", directory="/test", config="test.json"
                    )

        assert result["pipeline_type"] == "local"
        assert result["run_mode"] == "single"
        assert result["files_processed"] == 2
        assert "total_duration" in result

    @pytest.mark.asyncio
    async def test_invalid_pipeline_type(self):
        pool = _make_pool()
        result = await run_single_check(pool, "invalid_type")

        assert result["pipeline_type"] == "invalid_type"
        assert result["errors"] == 1
        assert "Unknown pipeline type" in result["error_message"]

    @pytest.mark.asyncio
    async def test_error_handling(self):
        pool = _make_pool()
        watcher_cls, watcher = _make_watcher_class()
        watcher.initialize_state.side_effect = Exception("Init failed")

        mock_module = MagicMock()
        mock_module.LocalFileWatcher = watcher_cls

        with patch.dict("sys.modules", {"Local_Files.file_watcher": mock_module}):
            result = await run_single_check(pool, "local")

        assert result["errors"] == 1
        assert "Init failed" in result["error_message"]


# ---------------------------------------------------------------------------
# _exit_from_stats
# ---------------------------------------------------------------------------

class TestExitFromStats:
    def test_success_exit(self):
        with pytest.raises(SystemExit) as exc_info:
            _exit_from_stats({"errors": 0})
        assert exc_info.value.code == 0

    def test_auth_error_exit(self):
        with pytest.raises(SystemExit) as exc_info:
            _exit_from_stats({"errors": 1, "error_message": "Authentication failed"})
        assert exc_info.value.code == 3

    def test_config_error_exit(self):
        with pytest.raises(SystemExit) as exc_info:
            _exit_from_stats({"errors": 1, "error_message": "Invalid config file"})
        assert exc_info.value.code == 2

    def test_runtime_error_exit(self):
        with pytest.raises(SystemExit) as exc_info:
            _exit_from_stats({"errors": 1, "error_message": "Database connection failed"})
        assert exc_info.value.code == 1

    @pytest.mark.parametrize(
        "error_msg,expected_code",
        [
            ("credential error", 3),
            ("auth token expired", 3),
            ("config parse error", 2),
            ("network timeout", 1),
            ("", 1),
        ],
    )
    def test_exit_code_mapping(self, error_msg, expected_code):
        with pytest.raises(SystemExit) as exc_info:
            _exit_from_stats({"errors": 1, "error_message": error_msg})
        assert exc_info.value.code == expected_code
