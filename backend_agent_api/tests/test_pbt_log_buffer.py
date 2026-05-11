"""Property-based tests for LogBufferHandler capacity and FIFO ordering.

# Feature: admin-system-monitor, Property 4: Log buffer maintains capacity and FIFO ordering
# Validates: Requirements 4.1, 4.2

Property 4: For any sequence of N log records emitted to the Log_Buffer,
the buffer SHALL contain exactly min(N, 500) records, and those records
SHALL be the N most recently emitted ones in chronological order.
"""

import logging

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from log_buffer import LogBufferHandler

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Realistic logger names
logger_names = st.from_regex(r"[a-z][a-z0-9_.]{0,20}", fullmatch=True)

# Log levels that Python's logging module recognizes
log_levels = st.sampled_from([logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR, logging.CRITICAL])

# Log message text — printable strings of reasonable length
log_messages = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z"), whitelist_characters=" "),
    min_size=1,
    max_size=100,
)

# A single log record as a tuple of (logger_name, level, message)
log_record_tuples = st.tuples(logger_names, log_levels, log_messages)

# Sequences of log records: 0 to 1000 entries
log_record_sequences = st.lists(log_record_tuples, min_size=0, max_size=1000)


def _make_logging_record(name: str, level: int, message: str) -> logging.LogRecord:
    """Create a stdlib logging.LogRecord for emission into the handler."""
    return logging.LogRecord(
        name=name,
        level=level,
        pathname="test.py",
        lineno=1,
        msg=message,
        args=None,
        exc_info=None,
    )


# ---------------------------------------------------------------------------
# Property 4: Log buffer maintains capacity and FIFO ordering
# ---------------------------------------------------------------------------

class TestLogBufferCapacityAndFIFO:
    """Property 4: Log buffer maintains capacity and FIFO ordering.

    **Validates: Requirements 4.1, 4.2**
    """

    @given(records=log_record_sequences)
    @settings(max_examples=30, deadline=None)
    def test_buffer_size_is_min_n_capacity(self, records: list[tuple[str, int, str]]):
        """For any sequence of N log records, the buffer contains exactly
        min(N, max_size) records."""
        # Feature: admin-system-monitor, Property 4: Log buffer maintains capacity and FIFO ordering
        # Validates: Requirements 4.1, 4.2

        handler = LogBufferHandler(max_size=500)

        for name, level, message in records:
            handler.emit(_make_logging_record(name, level, message))

        all_records = handler.get_records(min_level="DEBUG")
        expected_count = min(len(records), 500)

        assert len(all_records) == expected_count, (
            f"Expected {expected_count} records, got {len(all_records)} "
            f"after emitting {len(records)} records"
        )

    @given(records=log_record_sequences)
    @settings(max_examples=30, deadline=None)
    def test_buffer_contains_most_recent_records(self, records: list[tuple[str, int, str]]):
        """After emitting N records, the buffer contains the N most recently
        emitted ones (the tail of the input sequence)."""
        # Feature: admin-system-monitor, Property 4: Log buffer maintains capacity and FIFO ordering
        # Validates: Requirements 4.1, 4.2

        handler = LogBufferHandler(max_size=500)

        for name, level, message in records:
            handler.emit(_make_logging_record(name, level, message))

        all_records = handler.get_records(min_level="DEBUG")

        # The buffer should contain the last min(N, 500) records
        expected_tail = records[-500:] if len(records) > 500 else records

        assert len(all_records) == len(expected_tail)

        for buffered, (name, level, message) in zip(all_records, expected_tail):
            assert buffered["logger"] == name
            assert buffered["level"] == logging.getLevelName(level)
            assert buffered["message"] == message

    @given(records=log_record_sequences)
    @settings(max_examples=30, deadline=None)
    def test_fifo_chronological_ordering(self, records: list[tuple[str, int, str]]):
        """Records in the buffer are in the same chronological order as they
        were emitted — first emitted appears first in the output."""
        # Feature: admin-system-monitor, Property 4: Log buffer maintains capacity and FIFO ordering
        # Validates: Requirements 4.1, 4.2

        handler = LogBufferHandler(max_size=500)

        for name, level, message in records:
            handler.emit(_make_logging_record(name, level, message))

        all_records = handler.get_records(min_level="DEBUG")

        # Verify ordering: timestamps should be non-decreasing
        timestamps = [r["timestamp"] for r in all_records]
        assert timestamps == sorted(timestamps), (
            "Log records are not in chronological order"
        )

    @given(
        capacity=st.integers(min_value=1, max_value=50),
        records=st.lists(log_record_tuples, min_size=0, max_size=200),
    )
    @settings(max_examples=30, deadline=None)
    def test_custom_capacity_respected(self, capacity: int, records: list[tuple[str, int, str]]):
        """For any custom max_size, the buffer never exceeds that capacity
        and retains the most recent records."""
        # Feature: admin-system-monitor, Property 4: Log buffer maintains capacity and FIFO ordering
        # Validates: Requirements 4.1, 4.2

        handler = LogBufferHandler(max_size=capacity)

        for name, level, message in records:
            handler.emit(_make_logging_record(name, level, message))

        all_records = handler.get_records(min_level="DEBUG")
        expected_count = min(len(records), capacity)

        assert len(all_records) == expected_count

        # Verify these are the most recent records
        expected_tail = records[-capacity:] if len(records) > capacity else records
        for buffered, (name, level, message) in zip(all_records, expected_tail):
            assert buffered["logger"] == name
            assert buffered["level"] == logging.getLevelName(level)
            assert buffered["message"] == message


# ---------------------------------------------------------------------------
# Strategies for Property 5
# ---------------------------------------------------------------------------

# Log level names as strings (matching what LogBufferHandler uses for filtering)
log_level_names = st.sampled_from(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])

# Map level names to numeric values for assertions
LEVEL_VALUES = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}


# ---------------------------------------------------------------------------
# Property 5: Log level filtering returns only records at or above threshold
# ---------------------------------------------------------------------------

class TestLogBufferLevelFiltering:
    """Property 5: Log level filtering returns only records at or above threshold.

    **Validates: Requirements 4.4, 4.5, 4.6**
    """

    @given(records=log_record_sequences, filter_level=log_level_names)
    @settings(max_examples=30, deadline=None)
    def test_filtered_records_only_at_or_above_threshold(
        self, records: list[tuple[str, int, str]], filter_level: str
    ):
        """For any filter level L, every returned record has severity >= L."""
        # Feature: admin-system-monitor, Property 5: Log level filtering returns only records at or above threshold
        # Validates: Requirements 4.4, 4.5, 4.6

        handler = LogBufferHandler(max_size=500)
        for name, level, message in records:
            handler.emit(_make_logging_record(name, level, message))

        filtered = handler.get_records(min_level=filter_level)
        threshold = LEVEL_VALUES[filter_level]

        for rec in filtered:
            rec_level_num = LEVEL_VALUES[rec["level"]]
            assert rec_level_num >= threshold, (
                f"Record with level {rec['level']} ({rec_level_num}) "
                f"should not appear when filtering at {filter_level} ({threshold})"
            )

    @given(records=log_record_sequences, filter_level=log_level_names)
    @settings(max_examples=30, deadline=None)
    def test_all_qualifying_records_included(
        self, records: list[tuple[str, int, str]], filter_level: str
    ):
        """For any filter level L, every record in the buffer with severity >= L
        appears in the filtered result (no false negatives)."""
        # Feature: admin-system-monitor, Property 5: Log level filtering returns only records at or above threshold
        # Validates: Requirements 4.4, 4.5, 4.6

        handler = LogBufferHandler(max_size=500)
        for name, level, message in records:
            handler.emit(_make_logging_record(name, level, message))

        filtered = handler.get_records(min_level=filter_level)
        all_records = handler.get_records(min_level="DEBUG")
        threshold = LEVEL_VALUES[filter_level]

        # Count how many records in the full buffer are at or above threshold
        expected_count = sum(
            1 for r in all_records if LEVEL_VALUES[r["level"]] >= threshold
        )

        assert len(filtered) == expected_count, (
            f"Expected {expected_count} records at or above {filter_level}, "
            f"got {len(filtered)}"
        )

    @given(records=log_record_sequences, filter_level=log_level_names)
    @settings(max_examples=30, deadline=None)
    def test_filtered_records_have_required_fields(
        self, records: list[tuple[str, int, str]], filter_level: str
    ):
        """Each filtered record contains all required fields: timestamp, logger,
        level, and message (Requirements 4.5, 4.6)."""
        # Feature: admin-system-monitor, Property 5: Log level filtering returns only records at or above threshold
        # Validates: Requirements 4.4, 4.5, 4.6

        handler = LogBufferHandler(max_size=500)
        for name, level, message in records:
            handler.emit(_make_logging_record(name, level, message))

        filtered = handler.get_records(min_level=filter_level)
        required_fields = {"timestamp", "logger", "level", "message"}

        for rec in filtered:
            assert set(rec.keys()) == required_fields, (
                f"Record missing fields: expected {required_fields}, got {set(rec.keys())}"
            )
            # Verify timestamp is ISO 8601 (contains 'T' separator and timezone info)
            assert "T" in rec["timestamp"], (
                f"Timestamp '{rec['timestamp']}' is not ISO 8601 format"
            )
            # Verify level is a valid Python log level name
            assert rec["level"] in LEVEL_VALUES, (
                f"Level '{rec['level']}' is not a valid log level"
            )

    @given(records=log_record_sequences)
    @settings(max_examples=30, deadline=None)
    def test_debug_filter_returns_all_records(
        self, records: list[tuple[str, int, str]]
    ):
        """Filtering at DEBUG (lowest level) returns all buffered records."""
        # Feature: admin-system-monitor, Property 5: Log level filtering returns only records at or above threshold
        # Validates: Requirements 4.4, 4.5, 4.6

        handler = LogBufferHandler(max_size=500)
        for name, level, message in records:
            handler.emit(_make_logging_record(name, level, message))

        filtered = handler.get_records(min_level="DEBUG")
        expected_count = min(len(records), 500)

        assert len(filtered) == expected_count, (
            f"DEBUG filter should return all {expected_count} records, got {len(filtered)}"
        )
