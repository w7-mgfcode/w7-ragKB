"""Property-based tests for file watcher state management (Task 11.2).

Properties tested:
- P12: File watcher state updates — sync status updated on process
- P37: File watcher state persistence — state saved after check
- P38: File watcher state cleanup — deleted files remove sync status
- P39: File watcher state addition — new files get sync status
"""

import asyncio
import json
import os
import shutil
import sys
import tempfile
import types
import pytest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from hypothesis import given, settings
from hypothesis.strategies import integers

# file_watcher lives in backend_rag_pipeline and imports pypdf + google.genai
# which aren't installed in the backend_agent_api test env. Mock them.
_rag_root = os.path.join(os.path.dirname(__file__), "..", "..", "backend_rag_pipeline")
sys.path.insert(0, os.path.join(_rag_root, "Local_Files"))
sys.path.insert(0, _rag_root)

if "pypdf" not in sys.modules:
    sys.modules["pypdf"] = types.ModuleType("pypdf")


def _make_watcher(pool, data_dir, config_path):
    """Create a LocalFileWatcher with given pool and dirs."""
    with patch.dict(os.environ, {"RAG_WATCH_DIRECTORY": str(data_dir)}):
        from file_watcher import LocalFileWatcher
        return LocalFileWatcher(pool=pool, watch_directory=str(data_dir), config_path=str(config_path))


def _write_config(path):
    Path(path).write_text(json.dumps({
        "supported_mime_types": ["text/plain"],
        "tabular_mime_types": [],
        "text_processing": {"default_chunk_size": 400, "default_chunk_overlap": 0},
        "last_check_time": "1970-01-01T00:00:00.000Z",
    }))


# ==========================================================================
# P12: File watcher state updates — sync status set on process
# ==========================================================================


def test_process_file_sets_processing_then_final_status(tmp_path):
    """process_file must set status to processing then in_sync or error."""
    pool = AsyncMock()
    pool.execute = AsyncMock()

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    test_file = data_dir / "test.txt"
    test_file.write_text("hello world")

    cfg = tmp_path / "cfg.json"
    _write_config(cfg)
    w = _make_watcher(pool, data_dir, cfg)

    status_calls = []
    original = w._update_sync_status

    async def capture(rel, status, **kw):
        status_calls.append(status)
        await original(rel, status, **kw)

    file_info = {
        "id": str(test_file), "name": "test.txt", "mimeType": "text/plain",
        "webViewLink": f"file://{test_file}",
        "modifiedTime": datetime.now(timezone.utc).isoformat(),
        "createdTime": datetime.now(timezone.utc).isoformat(),
        "trashed": False,
    }

    with patch.object(w, "_update_sync_status", side_effect=capture), \
         patch("file_watcher.extract_text_from_file", return_value="hello"), \
         patch("file_watcher.process_file_for_rag", new_callable=AsyncMock, return_value=True):
        asyncio.run(w.process_file(file_info))

    assert status_calls[0] == w.SYNC_PROCESSING
    assert w.SYNC_IN_SYNC in status_calls or w.SYNC_ERROR in status_calls


# ==========================================================================
# P37: File watcher state persistence
# ==========================================================================


def test_check_for_changes_saves_state(tmp_path):
    """After check_for_changes, state must be persisted."""
    pool = AsyncMock()
    pool.execute = AsyncMock()

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    cfg = tmp_path / "cfg.json"
    _write_config(cfg)
    w = _make_watcher(pool, data_dir, cfg)

    w.initialized = True
    save_called = False

    async def track_save():
        nonlocal save_called
        save_called = True

    with patch.object(w, "save_state", side_effect=track_save), \
         patch.object(w, "_scan_directory", return_value=[]), \
         patch.object(w, "_check_deleted", return_value=[]):
        asyncio.run(w.check_for_changes())

    assert save_called


# ==========================================================================
# P38: Deleted files remove sync status
# ==========================================================================


@given(file_count=integers(min_value=1, max_value=5))
@settings(max_examples=15)
def test_deleted_files_remove_sync_status(file_count):
    """When files are deleted, their sync status rows must be removed."""
    tmp = Path(tempfile.mkdtemp())
    try:
        pool = AsyncMock()
        pool.execute = AsyncMock()

        data_dir = tmp / "data"
        data_dir.mkdir()
        cfg = tmp / "cfg.json"
        _write_config(cfg)
        w = _make_watcher(pool, data_dir, cfg)

        for i in range(file_count):
            w.known_files[str(data_dir / f"gone{i}.txt")] = datetime.now(timezone.utc).isoformat()

        w.initialized = True

        with patch.object(w, "_scan_directory", return_value=[]), \
             patch("file_watcher.delete_document_by_file_id", new_callable=AsyncMock):
            asyncio.run(w.check_for_changes())

        delete_calls = [
            c for c in pool.execute.call_args_list
            if len(c[0]) > 0 and "DELETE FROM document_sync_status" in c[0][0]
        ]
        assert len(delete_calls) == file_count
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ==========================================================================
# P39: New files tracked in known_files
# ==========================================================================


@given(file_count=integers(min_value=1, max_value=5))
@settings(max_examples=15)
def test_new_files_added_to_known_files(file_count):
    """New files detected by scanner must be added to known_files."""
    tmp = Path(tempfile.mkdtemp())
    try:
        pool = AsyncMock()
        pool.execute = AsyncMock()

        data_dir = tmp / "data"
        data_dir.mkdir()
        cfg = tmp / "cfg2.json"
        _write_config(cfg)
        w = _make_watcher(pool, data_dir, cfg)

        for i in range(file_count):
            (data_dir / f"new{i}.txt").write_text(f"content {i}")

        w.initialized = True

        with patch("file_watcher.extract_text_from_file", return_value="text"), \
             patch("file_watcher.process_file_for_rag", new_callable=AsyncMock, return_value=True):
            asyncio.run(w.check_for_changes())

        for i in range(file_count):
            assert str(data_dir / f"new{i}.txt") in w.known_files
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
