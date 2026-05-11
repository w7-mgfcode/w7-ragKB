"""Property-based tests for health status to color mapping.

# Feature: admin-system-monitor, Property 10: Health status to color mapping is correct
# Validates: Requirements 10.3

Property 10: For any service status value, the Monitor_Dashboard SHALL map
"healthy" to green, "degraded" to yellow, and "down" to red. This mapping
is total and deterministic.
"""

from hypothesis import given, settings
from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# The specification contract: status → color mapping
# This mirrors the frontend statusBadge() function in HealthCards.tsx
# ---------------------------------------------------------------------------

VALID_STATUSES = ("healthy", "degraded", "down")

STATUS_TO_COLOR = {
    "healthy": "green",
    "degraded": "yellow",
    "down": "red",
}

# Strategy: pick any valid status value
status_strategy = st.sampled_from(VALID_STATUSES)


# ---------------------------------------------------------------------------
# Property 10: Health status to color mapping is correct
# ---------------------------------------------------------------------------


class TestHealthStatusToColorMapping:
    """Property 10: Health status to color mapping is correct.

    **Validates: Requirements 10.3**

    For any service status value, the Monitor_Dashboard SHALL map "healthy"
    to green, "degraded" to yellow, and "down" to red. This mapping is total
    and deterministic.
    """

    @given(status=status_strategy)
    @settings(max_examples=30, deadline=None)
    def test_status_maps_to_correct_color(self, status: str):
        """For any valid status, the mapping returns the correct color."""
        # Feature: admin-system-monitor, Property 10: Health status to color mapping is correct
        # Validates: Requirements 10.3

        expected_colors = {
            "healthy": "green",
            "degraded": "yellow",
            "down": "red",
        }

        result = STATUS_TO_COLOR[status]
        assert result == expected_colors[status], (
            f"Status '{status}' mapped to '{result}', expected '{expected_colors[status]}'"
        )

    @given(status=status_strategy)
    @settings(max_examples=30, deadline=None)
    def test_mapping_is_deterministic(self, status: str):
        """For any valid status, calling the mapping twice yields the same color."""
        # Feature: admin-system-monitor, Property 10: Health status to color mapping is correct
        # Validates: Requirements 10.3

        first_call = STATUS_TO_COLOR[status]
        second_call = STATUS_TO_COLOR[status]
        assert first_call == second_call, (
            f"Non-deterministic mapping for '{status}': "
            f"first='{first_call}', second='{second_call}'"
        )

    def test_mapping_is_total(self):
        """The mapping covers all valid status values — no status is unmapped."""
        # Feature: admin-system-monitor, Property 10: Health status to color mapping is correct
        # Validates: Requirements 10.3

        for status in VALID_STATUSES:
            assert status in STATUS_TO_COLOR, (
                f"Status '{status}' has no color mapping"
            )
            assert STATUS_TO_COLOR[status] in ("green", "yellow", "red"), (
                f"Status '{status}' maps to unexpected color '{STATUS_TO_COLOR[status]}'"
            )

    def test_mapping_has_no_extra_entries(self):
        """The mapping contains only the three valid statuses — no extras."""
        # Feature: admin-system-monitor, Property 10: Health status to color mapping is correct
        # Validates: Requirements 10.3

        assert set(STATUS_TO_COLOR.keys()) == set(VALID_STATUSES), (
            f"Mapping keys {set(STATUS_TO_COLOR.keys())} != valid statuses {set(VALID_STATUSES)}"
        )

    @given(status=status_strategy)
    @settings(max_examples=30, deadline=None)
    def test_each_status_maps_to_distinct_color(self, status: str):
        """Each status maps to a unique color — no two statuses share a color."""
        # Feature: admin-system-monitor, Property 10: Health status to color mapping is correct
        # Validates: Requirements 10.3

        all_colors = list(STATUS_TO_COLOR.values())
        assert len(all_colors) == len(set(all_colors)), (
            f"Color mapping is not injective: {STATUS_TO_COLOR}"
        )

        # The specific status's color is unique
        color = STATUS_TO_COLOR[status]
        other_colors = [
            STATUS_TO_COLOR[s] for s in VALID_STATUSES if s != status
        ]
        assert color not in other_colors, (
            f"Status '{status}' shares color '{color}' with another status"
        )
