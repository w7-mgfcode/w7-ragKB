"""Regression tests for timezone handling in LocalFileWatcher."""

import os
import sys
from datetime import datetime, timedelta, timezone

# Add parent directory so package imports resolve
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from Local_Files.file_watcher import LocalFileWatcher


def test_scan_directory_handles_aware_last_check_time(tmp_path):
    watch_dir = tmp_path / "watch"
    watch_dir.mkdir()

    sample_file = watch_dir / "sample.txt"
    sample_file.write_text("hello")

    watcher = LocalFileWatcher(pool=None, watch_directory=str(watch_dir))
    watcher.known_files = {str(sample_file): datetime.now(timezone.utc).isoformat()}
    watcher.last_check_time = datetime.now(timezone.utc) - timedelta(seconds=1)

    # Regression: this raised TypeError when mtimes were naive and last_check_time aware.
    changed = watcher._scan_directory()

    assert isinstance(changed, list)
