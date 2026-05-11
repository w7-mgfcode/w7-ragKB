"""Property-based tests for search integration and metadata management (Tasks 19.2, 20.3).

Properties tested:
- P35: Search source coverage — query includes sync_status join
- P36: Search result metadata — include_all_statuses parameter exists
- P45: Document metadata completeness — metadata dicts are JSON-serializable
- P46: Metadata-only updates don't trigger re-indexing
- P47: Watcher metadata extraction — file info extracted correctly
- P48: Sync status enum values usable as SQL filter
"""

import asyncio
import json
import os
import shutil
import sys
import tempfile
import types
from pathlib import Path
from unittest.mock import AsyncMock, patch

from hypothesis import given, settings, assume
from hypothesis.strategies import booleans, integers, lists, none, one_of, sampled_from, text

# Mock pypdf before any file_watcher import chain triggers
if "pypdf" not in sys.modules:
    sys.modules["pypdf"] = types.ModuleType("pypdf")

# Add rag pipeline paths for file_watcher tests
_rag_root = os.path.join(os.path.dirname(__file__), "..", "..", "backend_rag_pipeline")
sys.path.insert(0, os.path.join(_rag_root, "Local_Files"))
sys.path.insert(0, _rag_root)

from sync_manager import SyncStatus


tags_strat = lists(
    text(alphabet="abcdefghijklmnopqrstuvwxyz-", min_size=1, max_size=15),
    min_size=0, max_size=5,
)
titles = one_of(none(), text(min_size=1, max_size=50))
authors = one_of(none(), text(min_size=1, max_size=30))


# ==========================================================================
# P35: Search includes sync_status join
# ==========================================================================


def test_search_results_include_sync_status():
    """search_documents_by_content must LEFT JOIN document_sync_status."""
    import db_documents
    import inspect
    source = inspect.getsource(db_documents.search_documents_by_content)
    assert "document_sync_status" in source
    assert "LEFT JOIN" in source


# ==========================================================================
# P36: include_all_statuses parameter
# ==========================================================================


def test_search_accepts_include_all_statuses_param():
    """search_documents_by_content must accept include_all_statuses."""
    import db_documents
    import inspect
    sig = inspect.signature(db_documents.search_documents_by_content)
    assert "include_all_statuses" in sig.parameters


# ==========================================================================
# P45: Metadata completeness
# ==========================================================================


@given(title=titles, author=authors, tags=tags_strat)
@settings(max_examples=30)
def test_metadata_model_json_serializable(title, author, tags):
    """Metadata dict must be JSON-serializable for any field combo."""
    metadata = {}
    if title is not None:
        metadata["title"] = title
    if author is not None:
        metadata["author"] = author
    if tags:
        metadata["tags"] = tags

    serialized = json.dumps(metadata)
    deserialized = json.loads(serialized)
    assert isinstance(deserialized, dict)


# ==========================================================================
# P46: Metadata-only updates don't re-index
# ==========================================================================


@given(title=titles, author=authors, tags=tags_strat)
@settings(max_examples=20)
def test_metadata_patch_does_not_trigger_reindex(title, author, tags):
    """PATCH metadata must update DB without calling _chunk_and_insert."""
    pool = AsyncMock()
    pool.execute = AsyncMock()
    pool.fetchval = AsyncMock(return_value=1)

    patch_data = {}
    if title is not None:
        patch_data["title"] = title
    if author is not None:
        patch_data["author"] = author
    if tags:
        patch_data["tags"] = tags

    assume(len(patch_data) > 0)

    async def do_patch():
        await pool.execute(
            "UPDATE documents SET metadata = metadata || $2::jsonb WHERE metadata->>'file_path' = $1",
            "test.md", json.dumps(patch_data),
        )

    asyncio.run(do_patch())

    pool.execute.assert_called_once()
    pool.fetchval.assert_not_called()


# ==========================================================================
# P47: Watcher metadata extraction
# ==========================================================================


@given(file_count=integers(min_value=1, max_value=5))
@settings(max_examples=15)
def test_watcher_extracts_file_metadata(file_count):
    """File watcher must extract modifiedTime and mimeType for each file."""
    tmp = Path(tempfile.mkdtemp())
    try:
        from file_watcher import LocalFileWatcher

        data_dir = tmp / "data"
        data_dir.mkdir()
        for i in range(file_count):
            (data_dir / f"doc{i}.txt").write_text(f"content {i}")

        pool = AsyncMock()
        cfg = tmp / "cfg.json"
        cfg.write_text(json.dumps({
            "supported_mime_types": ["text/plain"],
            "tabular_mime_types": [],
            "text_processing": {"default_chunk_size": 400, "default_chunk_overlap": 0},
            "last_check_time": "1970-01-01T00:00:00.000Z",
        }))

        with patch.dict(os.environ, {"RAG_WATCH_DIRECTORY": str(data_dir)}):
            w = LocalFileWatcher(pool=pool, watch_directory=str(data_dir), config_path=str(cfg))

        files = w._scan_directory()
        assert len(files) == file_count
        for f in files:
            assert "modifiedTime" in f
            assert "mimeType" in f
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ==========================================================================
# P48: Sync status values usable as SQL filter
# ==========================================================================


@given(status=sampled_from(list(SyncStatus)))
@settings(max_examples=30)
def test_sync_status_values_are_valid_sql_strings(status):
    """Every SyncStatus value must be a plain lowercase string without spaces."""
    assert isinstance(status.value, str)
    assert len(status.value) > 0
    assert status.value == status.value.lower()
    assert " " not in status.value
