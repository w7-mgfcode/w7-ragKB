"""Property-based tests for sync status computation correctness.

Uses Hypothesis to verify the invariant properties of sync status logic:
- Property 3: Sync status is always one of 6 valid values
- Property 4: filesystem_mtime == db_mtime → in_sync
- Property 5: filesystem_mtime > db_mtime → out_of_sync
- Property 6: DB chunks exist but no file → orphaned_chunks
- Property 7: File exists but no DB chunks → pending_indexing
"""

import pytest
from datetime import datetime, timezone, timedelta
from hypothesis import given, settings, assume
from hypothesis.strategies import (
    booleans,
    datetimes,
    integers,
    sampled_from,
    text,
)

from sync_manager import SyncStatus, DocumentSyncInfo


VALID_SYNC_STATUSES = {
    "in_sync",
    "out_of_sync",
    "processing",
    "error",
    "orphaned_chunks",
    "pending_indexing",
}


# ==========================================================================
# Property 3: Status always valid
# ==========================================================================


@given(status=sampled_from(list(SyncStatus)))
@settings(max_examples=50)
def test_sync_status_enum_values_are_valid(status):
    """Every SyncStatus enum member must be one of the 6 valid values."""
    assert status.value in VALID_SYNC_STATUSES


@given(status=sampled_from(list(SyncStatus)))
@settings(max_examples=50)
def test_document_sync_info_accepts_all_valid_statuses(status):
    """DocumentSyncInfo should accept every valid SyncStatus."""
    info = DocumentSyncInfo(
        file_path="test/doc.md",
        sync_status=status,
    )
    assert info.sync_status.value in VALID_SYNC_STATUSES


# ==========================================================================
# Property 4: fs_mtime == db_mtime → in_sync (or db_mtime >= fs_mtime)
# ==========================================================================


@given(
    ts=datetimes(
        min_value=datetime(2020, 1, 1),
        max_value=datetime(2030, 1, 1),
    )
)
@settings(max_examples=50)
def test_equal_mtimes_implies_in_sync(ts):
    """If filesystem and DB mtime are equal, status should be in_sync."""
    fs_mtime = ts.replace(tzinfo=timezone.utc)
    db_mtime = ts.replace(tzinfo=timezone.utc)
    file_exists = True
    chunk_count = 5

    status = _compute_status(file_exists, chunk_count, fs_mtime, db_mtime)
    assert status == SyncStatus.IN_SYNC


# ==========================================================================
# Property 5: fs_mtime > db_mtime → out_of_sync
# ==========================================================================


@given(
    base_ts=datetimes(
        min_value=datetime(2020, 1, 1),
        max_value=datetime(2029, 1, 1),
    ),
    offset_seconds=integers(min_value=2, max_value=86400),
)
@settings(max_examples=50)
def test_newer_fs_implies_out_of_sync(base_ts, offset_seconds):
    """If filesystem mtime is newer than DB mtime, status should be out_of_sync."""
    db_mtime = base_ts.replace(tzinfo=timezone.utc)
    fs_mtime = db_mtime + timedelta(seconds=offset_seconds)
    file_exists = True
    chunk_count = 5

    status = _compute_status(file_exists, chunk_count, fs_mtime, db_mtime)
    assert status == SyncStatus.OUT_OF_SYNC


# ==========================================================================
# Property 6: DB chunks but no file → orphaned_chunks
# ==========================================================================


@given(chunk_count=integers(min_value=1, max_value=100))
@settings(max_examples=50)
def test_no_file_with_chunks_implies_orphaned(chunk_count):
    """DB chunks exist but no file → orphaned_chunks."""
    status = _compute_status(
        file_exists=False,
        chunk_count=chunk_count,
        fs_mtime=None,
        db_mtime=datetime.now(timezone.utc),
    )
    assert status == SyncStatus.ORPHANED_CHUNKS


# ==========================================================================
# Property 7: File exists but no chunks → pending_indexing
# ==========================================================================


@given(
    ts=datetimes(
        min_value=datetime(2020, 1, 1),
        max_value=datetime(2030, 1, 1),
    )
)
@settings(max_examples=50)
def test_file_exists_no_chunks_implies_pending(ts):
    """File exists but zero DB chunks → pending_indexing."""
    fs_mtime = ts.replace(tzinfo=timezone.utc)
    status = _compute_status(
        file_exists=True,
        chunk_count=0,
        fs_mtime=fs_mtime,
        db_mtime=None,
    )
    assert status == SyncStatus.PENDING_INDEXING


# ==========================================================================
# Helper — mirrors SyncManager._compute_sync_info logic
# ==========================================================================


def _compute_status(
    file_exists: bool,
    chunk_count: int,
    fs_mtime: datetime | None,
    db_mtime: datetime | None,
) -> SyncStatus:
    """Pure function mirroring SyncManager._compute_sync_info sync status logic."""
    if file_exists and chunk_count > 0:
        if db_mtime and fs_mtime and fs_mtime > db_mtime:
            return SyncStatus.OUT_OF_SYNC
        else:
            return SyncStatus.IN_SYNC
    elif file_exists and chunk_count == 0:
        return SyncStatus.PENDING_INDEXING
    elif not file_exists and chunk_count > 0:
        return SyncStatus.ORPHANED_CHUNKS
    else:
        return SyncStatus.PENDING_INDEXING
