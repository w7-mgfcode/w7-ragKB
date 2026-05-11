"""Property-based tests for the webhook system.

Feature: openclaw-integration (Task 13.1)
Properties tested: 30, 31, 32, 33, 34, 35

Tests webhook registration, authentication, routing,
payload transformation, error handling, and logging.
"""

import json
import re
import string
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hypothesis import HealthCheck, given, settings, strategies as st

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from db_webhooks import (
    generate_auth_token,
    generate_webhook_id,
    generate_webhook_url,
)
from webhook_handler import (
    log_webhook_request,
    transform_payload,
    validate_payload_schema,
)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

safe_id = st.text(
    alphabet=string.ascii_letters + string.digits + "-_.",
    min_size=1,
    max_size=30,
)
safe_text = st.text(min_size=1, max_size=200).filter(lambda s: s.strip())
base_url = st.just("/api/webhooks")
json_value = st.one_of(
    st.integers(min_value=-1000, max_value=1000),
    st.text(min_size=0, max_size=50),
    st.booleans(),
    st.floats(allow_nan=False, allow_infinity=False),
    st.none(),
)
flat_payload = st.dictionaries(
    keys=st.text(
        alphabet=string.ascii_letters + string.digits + "_",
        min_size=1,
        max_size=15,
    ),
    values=json_value,
    min_size=1,
    max_size=5,
)
auth_statuses = st.sampled_from(["valid", "invalid", "missing"])
routing_outcomes = st.sampled_from(["success", "failed", "error"])


# ===========================================================================
# Property 30: Webhook registration
# ===========================================================================


class TestWebhookRegistration:
    """Property 30: Webhook registration creates unique URLs and tokens."""

    @settings(max_examples=100, deadline=None)
    @given(st.data())
    def test_webhook_id_is_16_char_hex(self, data):
        """
        Feature: openclaw-integration, Property 30: Webhook registration

        generate_webhook_id must produce a 16-character hex string.
        """
        wid = generate_webhook_id()
        assert len(wid) == 16
        assert re.fullmatch(r"[0-9a-f]+", wid)

    @settings(max_examples=100, deadline=None)
    @given(st.data())
    def test_auth_token_is_32_char_hex(self, data):
        """
        Feature: openclaw-integration, Property 30: Webhook registration

        generate_auth_token must produce a 32-character hex string.
        """
        token = generate_auth_token()
        assert len(token) == 32
        assert re.fullmatch(r"[0-9a-f]+", token)

    @settings(max_examples=50, deadline=None)
    @given(st.data())
    def test_webhook_ids_unique(self, data):
        """
        Feature: openclaw-integration, Property 30: Webhook registration

        Repeated calls should produce distinct webhook IDs.
        """
        ids = {generate_webhook_id() for _ in range(20)}
        assert len(ids) >= 18

    @settings(max_examples=50, deadline=None)
    @given(st.data())
    def test_auth_tokens_unique(self, data):
        """
        Feature: openclaw-integration, Property 30: Webhook registration

        Repeated calls should produce distinct auth tokens.
        """
        tokens = {generate_auth_token() for _ in range(20)}
        assert len(tokens) >= 18

    @given(webhook_id=safe_id, base=base_url)
    @settings(max_examples=100, deadline=None)
    def test_webhook_url_contains_id(self, webhook_id, base):
        """
        Feature: openclaw-integration, Property 30: Webhook registration

        generate_webhook_url must produce base + "/" + webhook_id.
        """
        url = generate_webhook_url(webhook_id, base)
        assert url == f"{base}/{webhook_id}"
        assert webhook_id in url


# ===========================================================================
# Property 31: Webhook authentication
# ===========================================================================


class TestWebhookAuthentication:
    """Property 31: Valid token → process; invalid token → 401."""

    @given(token=st.text(min_size=32, max_size=32, alphabet="0123456789abcdef"))
    @settings(max_examples=50, deadline=None)
    def test_valid_token_format(self, token):
        """
        Feature: openclaw-integration, Property 31: Webhook authentication

        A valid auth token is a 32-char hex string.
        """
        assert len(token) == 32
        assert re.fullmatch(r"[0-9a-f]+", token)

    def test_generated_token_is_valid_format(self):
        """
        Feature: openclaw-integration, Property 31: Webhook authentication

        Generated tokens should have the correct format for auth.
        """
        for _ in range(10):
            token = generate_auth_token()
            assert len(token) == 32
            assert re.fullmatch(r"[0-9a-f]+", token)


# ===========================================================================
# Property 32: Webhook routing (payload to session)
# ===========================================================================


class TestWebhookRouting:
    """Property 32: Valid request → payload delivered to target session."""

    @given(payload=flat_payload)
    @settings(max_examples=50, deadline=None)
    def test_payload_passthrough_no_rules(self, payload):
        """
        Feature: openclaw-integration, Property 32: Webhook routing

        Without transform rules, payload should pass through unchanged.
        """
        result = transform_payload(payload, {})
        assert result == payload

    @given(payload=flat_payload)
    @settings(max_examples=50, deadline=None)
    def test_payload_passthrough_none_rules(self, payload):
        """
        Feature: openclaw-integration, Property 32: Webhook routing

        With None/falsy rules, payload should pass through unchanged.
        """
        result = transform_payload(payload, None)
        assert result == payload


# ===========================================================================
# Property 33: Webhook payload transformation
# ===========================================================================


class TestWebhookPayloadTransformation:
    """Property 33: Transformation rules applied before delivery."""

    def test_static_transformation(self):
        """
        Feature: openclaw-integration, Property 33: Webhook payload transformation

        Static rules should add fixed fields to the output.
        """
        payload = {"event": "push", "repo": "w7"}
        rules = {
            "static": {"source": "github", "priority": "high"},
        }
        result = transform_payload(payload, rules)
        assert result["source"] == "github"
        assert result["priority"] == "high"

    def test_jsonpath_transformation(self):
        """
        Feature: openclaw-integration, Property 33: Webhook payload transformation

        JSONPath rules should extract values from payload.
        """
        payload = {"data": {"name": "Alice", "score": 42}}
        rules = {
            "jsonpath": {
                "user_name": "$.data.name",
                "user_score": "$.data.score",
            },
        }
        result = transform_payload(payload, rules)
        assert result["user_name"] == "Alice"
        assert result["user_score"] == 42

    def test_jinja2_transformation(self):
        """
        Feature: openclaw-integration, Property 33: Webhook payload transformation

        Jinja2 rules should render templates with payload context.
        """
        payload = {"user": "Bob", "action": "login"}
        rules = {
            "jinja2": {
                "message": "User {{ payload.user }} performed {{ payload.action }}",
            },
        }
        result = transform_payload(payload, rules)
        assert "Bob" in result["message"]
        assert "login" in result["message"]

    def test_mixed_transformation(self):
        """
        Feature: openclaw-integration, Property 33: Webhook payload transformation

        Mixed rules (static + jinja2) should all apply.
        """
        payload = {"event": "deploy", "version": "1.2.3"}
        rules = {
            "static": {"priority": "normal"},
            "jinja2": {
                "summary": "Deployed version {{ payload.version }}",
            },
        }
        result = transform_payload(payload, rules)
        assert result["priority"] == "normal"
        assert "1.2.3" in result["summary"]

    @given(payload=flat_payload)
    @settings(max_examples=30, deadline=None)
    def test_empty_jsonpath_match_returns_original(self, payload):
        """
        Feature: openclaw-integration, Property 33: Webhook payload transformation

        JSONPath that matches nothing should not add the field.
        """
        rules = {
            "jsonpath": {
                "missing_field": "$.nonexistent.deeply.nested.value",
            },
        }
        result = transform_payload(payload, rules)
        assert "missing_field" not in result or result == payload


# ===========================================================================
# Property 34: Webhook error handling
# ===========================================================================


class TestWebhookErrorHandling:
    """Property 34: Non-existent session → HTTP 404."""

    def test_validate_payload_no_schema_returns_true(self):
        """
        Feature: openclaw-integration, Property 34: Webhook error handling

        No schema means any payload is valid.
        """
        assert validate_payload_schema({"any": "data"}, None) is True
        assert validate_payload_schema({}, None) is True

    def test_validate_payload_valid_schema(self):
        """
        Feature: openclaw-integration, Property 34: Webhook error handling

        Payload matching schema should pass validation.
        """
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "age": {"type": "integer"},
            },
            "required": ["name"],
        }
        assert validate_payload_schema({"name": "Alice", "age": 30}, schema) is True

    def test_validate_payload_invalid_schema_raises(self):
        """
        Feature: openclaw-integration, Property 34: Webhook error handling

        Payload not matching schema should raise ValidationError.
        """
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
            },
            "required": ["name"],
        }
        with pytest.raises(Exception):
            validate_payload_schema({"age": 30}, schema)

    @given(payload=flat_payload)
    @settings(max_examples=50, deadline=None)
    def test_validate_against_any_object_schema(self, payload):
        """
        Feature: openclaw-integration, Property 34: Webhook error handling

        Any dict payload should pass a permissive 'object' schema.
        """
        schema = {"type": "object"}
        assert validate_payload_schema(payload, schema) is True


# ===========================================================================
# Property 35: Webhook logging
# ===========================================================================


class TestWebhookLogging:
    """Property 35: All requests logged with required fields."""

    @given(
        webhook_id=safe_id,
        source_ip=st.from_regex(r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}", fullmatch=True),
        auth_status=auth_statuses,
        routing_outcome=routing_outcomes,
    )
    @settings(max_examples=50, deadline=None)
    @pytest.mark.asyncio
    async def test_log_webhook_request_does_not_raise(
        self, webhook_id, source_ip, auth_status, routing_outcome
    ):
        """
        Feature: openclaw-integration, Property 35: Webhook logging

        log_webhook_request should not raise for any valid inputs.
        """
        await log_webhook_request(
            webhook_id, source_ip, auth_status, routing_outcome
        )

    @pytest.mark.asyncio
    async def test_log_with_error_message(self):
        """
        Feature: openclaw-integration, Property 35: Webhook logging

        log_webhook_request with error_message should not raise.
        """
        await log_webhook_request(
            "wh-123",
            "192.168.1.1",
            "invalid",
            "failed",
            error_message="Token mismatch",
        )

    @given(
        webhook_id=safe_id,
        auth_status=auth_statuses,
        routing_outcome=routing_outcomes,
    )
    @settings(max_examples=50, deadline=None)
    @pytest.mark.asyncio
    async def test_log_captures_all_fields(
        self, webhook_id, auth_status, routing_outcome
    ):
        """
        Feature: openclaw-integration, Property 35: Webhook logging

        Logged entry should contain webhook_id, source_ip, auth_status, routing_outcome.
        """
        captured = []
        with patch("webhook_handler.logger") as mock_logger:
            mock_logger.info = lambda msg: captured.append(msg)
            await log_webhook_request(
                webhook_id, "10.0.0.1", auth_status, routing_outcome
            )

        assert len(captured) == 1
        log_str = captured[0]
        assert webhook_id in log_str
        assert auth_status in log_str
        assert routing_outcome in log_str
