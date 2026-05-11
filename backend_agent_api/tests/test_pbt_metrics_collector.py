"""Property-based tests for MetricsCollector API metrics.

# Feature: admin-system-monitor, Property 9: API metrics counting and averaging are mathematically correct
# Validates: Requirements 8.1, 8.2

Property 9: For any sequence of recorded requests to a given endpoint path
with known elapsed times [t1, t2, ..., tn], the API metrics endpoint SHALL
report request_count = n and avg_response_time_ms = sum(t1..tn) / n (within
floating-point tolerance).
"""

import math

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from metrics_collector import MetricsCollector

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Realistic API endpoint paths
endpoint_paths = st.from_regex(
    r"/api/[a-z]{1,10}(/[a-z]{1,10}){0,3}", fullmatch=True
)

# Elapsed times in ms: positive floats, bounded to avoid overflow
elapsed_times_ms = st.floats(min_value=0.01, max_value=60_000.0, allow_nan=False, allow_infinity=False)

# A non-empty list of elapsed times for a single endpoint
request_sequences = st.lists(elapsed_times_ms, min_size=1, max_size=200)

# Multiple endpoints: dict of path -> list of elapsed times
multi_endpoint_sequences = st.dictionaries(
    keys=endpoint_paths,
    values=request_sequences,
    min_size=1,
    max_size=10,
)


# ---------------------------------------------------------------------------
# Property 9: API metrics counting and averaging are mathematically correct
# ---------------------------------------------------------------------------

class TestApiMetricsCountingAndAveraging:
    """Property 9: API metrics counting and averaging are mathematically correct.

    **Validates: Requirements 8.1, 8.2**
    """

    @given(path=endpoint_paths, times=request_sequences)
    @settings(max_examples=30, deadline=None)
    def test_single_endpoint_count_and_average(self, path: str, times: list[float]):
        """For any single endpoint with n requests, request_count = n and
        avg_response_time_ms = sum(times) / n within floating-point tolerance."""
        # Feature: admin-system-monitor, Property 9: API metrics counting and averaging are mathematically correct
        # Validates: Requirements 8.1, 8.2

        collector = MetricsCollector()

        for t in times:
            collector.record_request(path, t)

        metrics = collector.get_endpoint_metrics()

        assert path in metrics
        endpoint = metrics[path]

        expected_count = len(times)
        expected_avg = sum(times) / len(times)

        assert endpoint["request_count"] == expected_count
        # avg_response_time_ms is rounded to 2 decimal places by the collector
        assert math.isclose(endpoint["avg_response_time_ms"], round(expected_avg, 2), abs_tol=0.01)

    @given(sequences=multi_endpoint_sequences)
    @settings(max_examples=30, deadline=None)
    def test_multiple_endpoints_independent_tracking(self, sequences: dict[str, list[float]]):
        """For any set of endpoints each with their own request sequences,
        each endpoint's metrics are tracked independently with correct counts
        and averages."""
        # Feature: admin-system-monitor, Property 9: API metrics counting and averaging are mathematically correct
        # Validates: Requirements 8.1, 8.2

        collector = MetricsCollector()

        for path, times in sequences.items():
            for t in times:
                collector.record_request(path, t)

        metrics = collector.get_endpoint_metrics()

        assert len(metrics) == len(sequences)

        for path, times in sequences.items():
            assert path in metrics
            endpoint = metrics[path]

            expected_count = len(times)
            expected_avg = sum(times) / len(times)

            assert endpoint["request_count"] == expected_count
            assert endpoint["path"] == path
            assert math.isclose(endpoint["avg_response_time_ms"], round(expected_avg, 2), abs_tol=0.01)

    @given(path=endpoint_paths, times=request_sequences)
    @settings(max_examples=30, deadline=None)
    def test_cumulative_total_response_time(self, path: str, times: list[float]):
        """The total response time tracked internally equals the sum of all
        recorded elapsed times, ensuring no data loss in accumulation."""
        # Feature: admin-system-monitor, Property 9: API metrics counting and averaging are mathematically correct
        # Validates: Requirements 8.1, 8.2

        collector = MetricsCollector()

        for t in times:
            collector.record_request(path, t)

        # Access internal state to verify cumulative total
        internal = collector._endpoint_metrics[path]
        expected_total = sum(times)

        assert math.isclose(internal.total_response_time_ms, expected_total, rel_tol=1e-9)
        assert internal.request_count == len(times)

    def test_fresh_collector_has_no_metrics(self):
        """A freshly created MetricsCollector has zero tracked endpoints."""
        # Feature: admin-system-monitor, Property 9: API metrics counting and averaging are mathematically correct
        # Validates: Requirements 8.1, 8.2

        collector = MetricsCollector()
        metrics = collector.get_endpoint_metrics()
        assert metrics == {}

    def test_endpoint_metrics_avg_zero_when_no_requests(self):
        """EndpointMetrics.avg_response_time_ms returns 0.0 when request_count is 0."""
        # Feature: admin-system-monitor, Property 9: API metrics counting and averaging are mathematically correct
        # Validates: Requirements 8.1, 8.2

        from metrics_collector import EndpointMetrics
        em = EndpointMetrics()
        assert em.avg_response_time_ms == 0.0

# ---------------------------------------------------------------------------
# Property 7: System resource metrics satisfy physical invariants
# ---------------------------------------------------------------------------

class TestSystemResourceMetricsInvariants:
    """Property 7: System resource metrics satisfy physical invariants.

    **Validates: Requirements 6.1, 6.2, 6.3, 6.4**

    For any call to get_system_resources(), the response SHALL satisfy:
    - process_memory_mb > 0
    - system_memory_used_mb + system_memory_available_mb <= system_memory_total_mb * 1.01
    - 0 <= cpu_percent <= 100
    - disk_used_gb + disk_free_gb <= disk_total_gb * 1.01
    """

    @given(data=st.data())
    @settings(max_examples=30, deadline=None)
    def test_resource_metrics_physical_invariants(self, data):
        """For any call to get_system_resources(), all physical invariants hold.

        We use hypothesis to drive repeated sampling — each example is a fresh
        call to psutil via the MetricsCollector, verifying that real system
        readings always satisfy the physical constraints.
        """
        # Feature: admin-system-monitor, Property 7: System resource metrics satisfy physical invariants
        # Validates: Requirements 6.1, 6.2, 6.3, 6.4

        collector = MetricsCollector()
        resources = collector.get_system_resources()

        # Req 6.1: process memory must be positive (a running process always uses memory)
        assert resources["process_memory_mb"] > 0, (
            f"process_memory_mb should be > 0, got {resources['process_memory_mb']}"
        )

        # Req 6.2: used + available <= total (with 1% tolerance for measurement timing)
        mem_sum = resources["system_memory_used_mb"] + resources["system_memory_available_mb"]
        mem_total = resources["system_memory_total_mb"]
        assert mem_sum <= mem_total * 1.01, (
            f"Memory invariant violated: used ({resources['system_memory_used_mb']}) + "
            f"available ({resources['system_memory_available_mb']}) = {mem_sum} > "
            f"total ({mem_total}) * 1.01 = {mem_total * 1.01}"
        )

        # Req 6.3: CPU percentage must be in [0, 100]
        assert 0 <= resources["cpu_percent"] <= 100, (
            f"cpu_percent should be in [0, 100], got {resources['cpu_percent']}"
        )

        # Req 6.4: disk used + free <= total (with 1% tolerance)
        disk_sum = resources["disk_used_gb"] + resources["disk_free_gb"]
        disk_total = resources["disk_total_gb"]
        assert disk_sum <= disk_total * 1.01, (
            f"Disk invariant violated: used ({resources['disk_used_gb']}) + "
            f"free ({resources['disk_free_gb']}) = {disk_sum} > "
            f"total ({disk_total}) * 1.01 = {disk_total * 1.01}"
        )

        # Additional structural checks: all values are non-negative
        assert resources["system_memory_total_mb"] > 0
        assert resources["system_memory_used_mb"] >= 0
        assert resources["system_memory_available_mb"] >= 0
        assert resources["disk_total_gb"] > 0
        assert resources["disk_used_gb"] >= 0
        assert resources["disk_free_gb"] >= 0

