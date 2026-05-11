"""Property-based tests for database schema modules.

Feature: openclaw-integration
Properties tested: 6, 71, 72, 73

Tests pure functions in db_sessions, db_channels, db_webhooks, and db_cron
for round-trip consistency, ID generation invariants, and serialization.
"""

import re
import string

import pytest
from hypothesis import HealthCheck, given, settings, strategies as st

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from db_sessions import generate_session_id, parse_session_id
from db_webhooks import generate_auth_token, generate_webhook_id, generate_webhook_url
from db_cron import generate_cron_job_id


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Safe text without the ":" separator used in session IDs
safe_id_text = st.text(
    alphabet=string.ascii_letters + string.digits + "-_.",
    min_size=1,
    max_size=50,
)

optional_thread_id = st.one_of(st.none(), safe_id_text)

hex_chars = st.text(alphabet="0123456789abcdef", min_size=16, max_size=16)

base_url_strategy = st.text(
    alphabet=string.ascii_letters + string.digits + "/-_",
    min_size=1,
    max_size=100,
).filter(lambda s: not s.endswith("/"))


# ===========================================================================
# Property 6: Channel configuration persistence (round-trip via session ID)
# ===========================================================================


class TestSessionIdRoundTrip:
    """Property 6 / 73: Round-trip consistency for session ID generation."""

    @given(
        channel_id=safe_id_text,
        user_id=safe_id_text,
        chat_id=safe_id_text,
    )
    @settings(max_examples=100, deadline=None)
    def test_roundtrip_without_thread(self, channel_id, user_id, chat_id):
        """
        Feature: openclaw-integration, Property 6: Channel configuration persistence

        generate_session_id -> parse_session_id should reconstruct original inputs
        when thread_id is None.
        """
        session_id = generate_session_id(channel_id, user_id, chat_id)
        parsed = parse_session_id(session_id)

        assert parsed["channel_id"] == channel_id
        assert parsed["user_id"] == user_id
        assert parsed["chat_id"] == chat_id
        assert parsed["thread_id"] is None

    @given(
        channel_id=safe_id_text,
        user_id=safe_id_text,
        chat_id=safe_id_text,
        thread_id=safe_id_text,
    )
    @settings(max_examples=100, deadline=None)
    def test_roundtrip_with_thread(self, channel_id, user_id, chat_id, thread_id):
        """
        Feature: openclaw-integration, Property 6: Channel configuration persistence

        generate_session_id -> parse_session_id should reconstruct original inputs
        including thread_id.
        """
        session_id = generate_session_id(channel_id, user_id, chat_id, thread_id)
        parsed = parse_session_id(session_id)

        assert parsed["channel_id"] == channel_id
        assert parsed["user_id"] == user_id
        assert parsed["chat_id"] == chat_id
        assert parsed["thread_id"] == thread_id

    @given(
        channel_id=safe_id_text,
        user_id=safe_id_text,
        chat_id=safe_id_text,
        thread_id=optional_thread_id,
    )
    @settings(max_examples=100, deadline=None)
    def test_determinism(self, channel_id, user_id, chat_id, thread_id):
        """
        Feature: openclaw-integration, Property 1: Message routing correctness

        Same inputs must always produce the same session_id.
        """
        id_a = generate_session_id(channel_id, user_id, chat_id, thread_id)
        id_b = generate_session_id(channel_id, user_id, chat_id, thread_id)
        assert id_a == id_b

    @given(
        channel_id=safe_id_text,
        user_id=safe_id_text,
        chat_id=safe_id_text,
    )
    @settings(max_examples=100, deadline=None)
    def test_contains_all_components(self, channel_id, user_id, chat_id):
        """
        Feature: openclaw-integration, Property 1: Message routing correctness

        The session_id must contain all routing components.
        """
        session_id = generate_session_id(channel_id, user_id, chat_id)
        assert channel_id in session_id
        assert user_id in session_id
        assert chat_id in session_id


# ===========================================================================
# Property 71 / 72: Webhook ID and auth token generation invariants
# ===========================================================================


class TestWebhookIdGeneration:
    """Property 71: Channel configuration serialization (ID format invariants)."""

    @settings(max_examples=100, deadline=None)
    @given(st.data())
    def test_webhook_id_is_16_char_hex(self, data):
        """
        Feature: openclaw-integration, Property 71: Channel config serialization

        generate_webhook_id() must always produce a 16-character hex string.
        """
        wid = generate_webhook_id()
        assert len(wid) == 16
        assert re.fullmatch(r"[0-9a-f]+", wid)

    @settings(max_examples=100, deadline=None)
    @given(st.data())
    def test_auth_token_is_32_char_hex(self, data):
        """
        Feature: openclaw-integration, Property 71: Channel config serialization

        generate_auth_token() must always produce a 32-character hex string.
        """
        token = generate_auth_token()
        assert len(token) == 32
        assert re.fullmatch(r"[0-9a-f]+", token)

    @settings(max_examples=50, deadline=None)
    @given(st.data())
    def test_webhook_ids_are_unique(self, data):
        """
        Feature: openclaw-integration, Property 71: Channel config serialization

        Repeated calls should produce distinct IDs (statistical property).
        """
        ids = {generate_webhook_id() for _ in range(20)}
        # At minimum, with 20 random 16-char hex strings, collisions are
        # astronomically unlikely. Require at least 18 unique.
        assert len(ids) >= 18

    @given(webhook_id=hex_chars, base_url=base_url_strategy)
    @settings(max_examples=100, deadline=None)
    def test_webhook_url_format(self, webhook_id, base_url):
        """
        Feature: openclaw-integration, Property 72: Channel config deserialization

        generate_webhook_url(id, base) must produce base + "/" + id.
        """
        url = generate_webhook_url(webhook_id, base_url)
        assert url == f"{base_url}/{webhook_id}"


# ===========================================================================
# Property 73: Cron job ID generation
# ===========================================================================


class TestCronJobIdGeneration:
    """Property 73: Configuration round-trip consistency (ID invariants)."""

    @settings(max_examples=100, deadline=None)
    @given(st.data())
    def test_cron_job_id_is_16_char_hex(self, data):
        """
        Feature: openclaw-integration, Property 73: Configuration round-trip

        generate_cron_job_id() must always produce a 16-character hex string.
        """
        cid = generate_cron_job_id()
        assert len(cid) == 16
        assert re.fullmatch(r"[0-9a-f]+", cid)

    @settings(max_examples=50, deadline=None)
    @given(st.data())
    def test_cron_job_ids_are_unique(self, data):
        """
        Feature: openclaw-integration, Property 73: Configuration round-trip

        Repeated calls should produce distinct IDs.
        """
        ids = {generate_cron_job_id() for _ in range(20)}
        assert len(ids) >= 18
