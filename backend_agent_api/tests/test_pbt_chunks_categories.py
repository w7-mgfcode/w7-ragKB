"""Property-based tests for chunk integrity and category tree (Tasks 12.2, 13.2).

Properties tested:
- P24: Hierarchical chunk parent references — all parent_ids valid
- P25: Cascading chunk deletion — section/leaf without parent flagged
- P30: Category tree directory addition
- P31: Category tree empty dirs
- P32: Category tree filesystem consistency
- P33: Category query routing — sync filter respects in-sync docs
"""

import asyncio
import shutil
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock

from hypothesis import given, settings
from hypothesis.strategies import integers, sampled_from

from sync_manager import SyncManager


# ==========================================================================
# P24: Valid hierarchy — no issues
# ==========================================================================


@given(
    section_count=integers(min_value=0, max_value=5),
    leaf_count=integers(min_value=0, max_value=8),
)
@settings(max_examples=30)
def test_validate_chunk_hierarchy_valid(section_count, leaf_count):
    """A well-formed hierarchy must produce zero issues."""
    pool = AsyncMock()

    rows = []
    doc_id = 100
    rows.append({"id": doc_id, "chunk_level": "document", "parent_chunk_id": None})

    section_ids = []
    for i in range(section_count):
        sid = 200 + i
        rows.append({"id": sid, "chunk_level": "section", "parent_chunk_id": doc_id})
        section_ids.append(sid)

    for i in range(leaf_count):
        parent = section_ids[i % len(section_ids)] if section_ids else doc_id
        rows.append({"id": 300 + i, "chunk_level": "leaf", "parent_chunk_id": parent})

    pool.fetch = AsyncMock(return_value=rows)
    sm = SyncManager(pool, "/tmp/test")

    issues = asyncio.run(sm.validate_chunk_hierarchy("test.md"))
    assert issues == []


# ==========================================================================
# P24: Broken parent references detected
# ==========================================================================


@given(orphan_count=integers(min_value=1, max_value=5))
@settings(max_examples=20)
def test_validate_chunk_hierarchy_finds_broken_refs(orphan_count):
    """Chunks with nonexistent parent_chunk_id must be flagged."""
    pool = AsyncMock()

    rows = [{"id": 1, "chunk_level": "document", "parent_chunk_id": None}]
    for i in range(orphan_count):
        rows.append({
            "id": 10 + i, "chunk_level": "leaf",
            "parent_chunk_id": 9999 + i,  # nonexistent
        })

    pool.fetch = AsyncMock(return_value=rows)
    sm = SyncManager(pool, "/tmp/test")

    issues = asyncio.run(sm.validate_chunk_hierarchy("test.md"))
    assert len(issues) == orphan_count


# ==========================================================================
# P24: Document-level chunk must not have parent
# ==========================================================================


def test_document_chunk_with_parent_is_flagged():
    """A document-level chunk with a parent_chunk_id is an error."""
    pool = AsyncMock()
    pool.fetch = AsyncMock(return_value=[
        {"id": 1, "chunk_level": "document", "parent_chunk_id": 99},
    ])
    sm = SyncManager(pool, "/tmp/test")

    issues = asyncio.run(sm.validate_chunk_hierarchy("test.md"))
    assert any("document-level has parent_chunk_id" in i for i in issues)


# ==========================================================================
# P25: Section/leaf without parent flagged
# ==========================================================================


@given(level=sampled_from(["section", "leaf"]))
@settings(max_examples=10)
def test_child_chunk_without_parent_flagged(level):
    """Section and leaf chunks missing parent_chunk_id are integrity errors."""
    pool = AsyncMock()
    pool.fetch = AsyncMock(return_value=[
        {"id": 1, "chunk_level": "document", "parent_chunk_id": None},
        {"id": 2, "chunk_level": level, "parent_chunk_id": None},
    ])
    sm = SyncManager(pool, "/tmp/test")

    issues = asyncio.run(sm.validate_chunk_hierarchy("test.md"))
    assert any("missing parent_chunk_id" in i for i in issues)


# ==========================================================================
# P30-32: Category tree from filesystem
# ==========================================================================


@given(dir_count=integers(min_value=1, max_value=6))
@settings(max_examples=15)
def test_category_tree_reflects_filesystem_dirs(dir_count):
    """Category tree must contain one node per top-level directory."""
    tmp = Path(tempfile.mkdtemp())
    try:
        from query_router import build_category_tree

        for i in range(dir_count):
            d = tmp / f"category_{i}"
            d.mkdir()
            (d / "page.md").write_text(f"# Page {i}")

        tree = build_category_tree(str(tmp))
        assert len(tree) == dir_count
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@given(dir_count=integers(min_value=1, max_value=5))
@settings(max_examples=15)
def test_empty_dirs_have_zero_document_count(dir_count):
    """Empty directories should have document_count=0."""
    tmp = Path(tempfile.mkdtemp())
    try:
        from query_router import build_category_tree

        for i in range(dir_count):
            (tmp / f"empty_{i}").mkdir()

        tree = build_category_tree(str(tmp))
        for node in tree:
            assert node.document_count == 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ==========================================================================
# P33: Sync-filtered category tree
# ==========================================================================


@given(
    in_sync_count=integers(min_value=0, max_value=3),
    out_of_sync_count=integers(min_value=0, max_value=3),
)
@settings(max_examples=20)
def test_sync_filtered_tree_only_counts_in_sync(in_sync_count, out_of_sync_count):
    """Sync-filtered tree must only count in-sync documents."""
    tmp = Path(tempfile.mkdtemp())
    try:
        pool = AsyncMock()
        cat_dir = tmp / "infra"
        cat_dir.mkdir()

        in_sync_paths = []
        for i in range(in_sync_count):
            fp = f"infra/synced_{i}.md"
            (tmp / fp).write_text(f"# Synced {i}")
            in_sync_paths.append(fp)

        for i in range(out_of_sync_count):
            fp = f"infra/unsynced_{i}.md"
            (tmp / fp).write_text(f"# Unsynced {i}")

        pool.fetch = AsyncMock(return_value=[{"file_path": p} for p in in_sync_paths])

        from query_router import build_category_tree_sync_filtered

        tree = asyncio.run(build_category_tree_sync_filtered(str(tmp), pool))

        if in_sync_count > 0:
            infra = next((n for n in tree if n.name == "infra"), None)
            assert infra is not None
            assert infra.document_count == in_sync_count
        elif out_of_sync_count > 0:
            infra = next((n for n in tree if n.name == "infra"), None)
            if infra:
                assert infra.document_count == 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
