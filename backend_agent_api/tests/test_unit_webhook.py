"""Unit tests for the webhook handler system.

Feature: openclaw-integration (Task 13.2)
Tests: HTTP endpoint responses, payload transformation rules,
webhook URL generation, authentication, schema validation.
"""

import json
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from db_webhooks import (
    generate_auth_token,
    generate_webhook_id,
    generate_webhook_url,
)
from webhook_handler import (
    WebhookRegistrationRequest,
    WebhookTriggerResponse,
    WebhookUpdateRequest,
    WebhookListResponse,
    log_webhook_request,
    transform_payload,
    validate_payload_schema,
)


# ===========================================================================
# Pydantic model validation
# ===========================================================================


class TestWebhookModels:
    """Unit tests for webhook Pydantic models."""

    def test_registration_request_required_fields(self):
        """Registration request requires target_session_id."""
        req = WebhookRegistrationRequest(target_session_id="s1")
        assert req.target_session_id == "s1"
        assert req.enabled is True
        assert req.payload_schema is None
        assert req.transform_rules == {}

    def test_registration_request_with_schema(self):
        """Registration request with optional schema and transform rules."""
        schema = {"type": "object", "required": ["name"]}
        rules = {"static": {"source": "github"}}
        req = WebhookRegistrationRequest(
            target_session_id="s1",
            payload_schema=schema,
            transform_rules=rules,
            enabled=False,
        )
        assert req.payload_schema == schema
        assert req.transform_rules == rules
        assert req.enabled is False

    def test_trigger_response_model(self):
        """Trigger response model should accept valid data."""
        resp = WebhookTriggerResponse(
            status="success",
            message="Webhook triggered",
            session_id="s1",
        )
        assert resp.status == "success"
        assert resp.session_id == "s1"

    def test_trigger_response_without_session(self):
        """Trigger response model with session_id=None."""
        resp = WebhookTriggerResponse(
            status="failed",
            message="Auth failed",
        )
        assert resp.session_id is None

    def test_update_request_optional_fields(self):
        """Update request with optional fields."""
        req = WebhookUpdateRequest()
        assert req.enabled is None
        assert req.transform_rules is None

    def test_update_request_with_values(self):
        """Update request with explicit values."""
        req = WebhookUpdateRequest(enabled=False, transform_rules={"static": {"a": 1}})
        assert req.enabled is False
        assert req.transform_rules == {"static": {"a": 1}}


# ===========================================================================
# Webhook URL generation
# ===========================================================================


class TestWebhookUrlGeneration:
    """Unit tests for webhook URL generation."""

    def test_default_base_url(self):
        """Default base URL should be /api/webhooks."""
        url = generate_webhook_url("abc123")
        assert url == "/api/webhooks/abc123"

    def test_custom_base_url(self):
        """Custom base URL should be respected."""
        url = generate_webhook_url("abc123", "/custom/path")
        assert url == "/custom/path/abc123"

    def test_url_contains_webhook_id(self):
        """URL should contain the webhook ID."""
        wid = generate_webhook_id()
        url = generate_webhook_url(wid)
        assert wid in url


# ===========================================================================
# Payload schema validation
# ===========================================================================


class TestPayloadSchemaValidation:
    """Unit tests for validate_payload_schema."""

    def test_no_schema_always_valid(self):
        """No schema should always return True."""
        assert validate_payload_schema({"any": "thing"}, None) is True

    def test_valid_string_type(self):
        """String type validation."""
        schema = {"type": "object", "properties": {"name": {"type": "string"}}}
        assert validate_payload_schema({"name": "Alice"}, schema) is True

    def test_invalid_type_raises(self):
        """Wrong type should raise ValidationError."""
        schema = {"type": "object", "properties": {"age": {"type": "integer"}}, "required": ["age"]}
        with pytest.raises(Exception):
            validate_payload_schema({"age": "not_a_number"}, schema)

    def test_missing_required_field_raises(self):
        """Missing required field should raise ValidationError."""
        schema = {"type": "object", "required": ["name"]}
        with pytest.raises(Exception):
            validate_payload_schema({}, schema)

    def test_additional_properties_allowed(self):
        """Extra properties should be allowed by default."""
        schema = {"type": "object", "properties": {"name": {"type": "string"}}}
        assert validate_payload_schema({"name": "Alice", "extra": 42}, schema) is True

    def test_nested_object_validation(self):
        """Nested object validation."""
        schema = {
            "type": "object",
            "properties": {
                "user": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                    "required": ["name"],
                }
            },
            "required": ["user"],
        }
        assert validate_payload_schema({"user": {"name": "Bob"}}, schema) is True

    def test_array_validation(self):
        """Array type validation."""
        schema = {
            "type": "object",
            "properties": {
                "tags": {"type": "array", "items": {"type": "string"}},
            },
        }
        assert validate_payload_schema({"tags": ["a", "b"]}, schema) is True


# ===========================================================================
# Payload transformation
# ===========================================================================


class TestPayloadTransformation:
    """Unit tests for transform_payload."""

    def test_empty_rules_passthrough(self):
        """Empty rules should return original payload."""
        payload = {"key": "value"}
        assert transform_payload(payload, {}) == payload

    def test_none_rules_passthrough(self):
        """None rules should return original payload."""
        payload = {"key": "value"}
        assert transform_payload(payload, None) == payload

    def test_static_only(self):
        """Static rules should produce static output."""
        result = transform_payload(
            {"original": True},
            {"static": {"type": "webhook", "version": 2}},
        )
        assert result["type"] == "webhook"
        assert result["version"] == 2

    def test_jsonpath_nested_extraction(self):
        """JSONPath should extract nested values."""
        payload = {"level1": {"level2": {"target": "found"}}}
        rules = {"jsonpath": {"extracted": "$.level1.level2.target"}}
        result = transform_payload(payload, rules)
        assert result["extracted"] == "found"

    def test_jsonpath_no_match_falls_through(self):
        """JSONPath with no match should not add the field."""
        payload = {"a": 1}
        rules = {"jsonpath": {"missing": "$.b.c.d"}}
        result = transform_payload(payload, rules)
        # Either returns original or result without "missing"
        assert "missing" not in result or result == payload

    def test_jinja2_template_rendering(self):
        """Jinja2 should render templates."""
        payload = {"name": "Alice", "count": 5}
        rules = {"jinja2": {"greeting": "Hello {{ payload.name }}, you have {{ payload.count }} items"}}
        result = transform_payload(payload, rules)
        assert "Alice" in result["greeting"]
        assert "5" in result["greeting"]

    def test_combined_static_and_jinja2(self):
        """Combined static and jinja2 rules."""
        payload = {"env": "production"}
        rules = {
            "static": {"source": "ci"},
            "jinja2": {"env_msg": "Deploying to {{ payload.env }}"},
        }
        result = transform_payload(payload, rules)
        assert result["source"] == "ci"
        assert "production" in result["env_msg"]

    def test_combined_all_three(self):
        """All three transform types combined."""
        payload = {"data": {"value": 42}, "label": "test"}
        rules = {
            "jsonpath": {"extracted_value": "$.data.value"},
            "jinja2": {"summary": "Label is {{ payload.label }}"},
            "static": {"processed": True},
        }
        result = transform_payload(payload, rules)
        assert result["extracted_value"] == 42
        assert "test" in result["summary"]
        assert result["processed"] is True


# ===========================================================================
# Webhook logging
# ===========================================================================


class TestWebhookLogging:
    """Unit tests for log_webhook_request."""

    @pytest.mark.asyncio
    async def test_log_success(self):
        """Successful webhook should be logged."""
        with patch("webhook_handler.logger") as mock_logger:
            mock_logger.info = MagicMock()
            await log_webhook_request("wh1", "10.0.0.1", "valid", "success")
            mock_logger.info.assert_called_once()
            log_msg = mock_logger.info.call_args[0][0]
            assert "wh1" in log_msg
            assert "valid" in log_msg
            assert "success" in log_msg

    @pytest.mark.asyncio
    async def test_log_failure_with_error(self):
        """Failed webhook with error should include error message."""
        with patch("webhook_handler.logger") as mock_logger:
            mock_logger.info = MagicMock()
            await log_webhook_request(
                "wh2", "192.168.1.1", "invalid", "failed", "Token mismatch"
            )
            log_msg = mock_logger.info.call_args[0][0]
            assert "Token mismatch" in log_msg

    @pytest.mark.asyncio
    async def test_log_contains_timestamp(self):
        """Log entry should contain a timestamp."""
        with patch("webhook_handler.logger") as mock_logger:
            mock_logger.info = MagicMock()
            await log_webhook_request("wh3", "1.2.3.4", "valid", "success")
            log_msg = mock_logger.info.call_args[0][0]
            # The log contains a JSON with "timestamp" key
            assert "timestamp" in log_msg

    @pytest.mark.asyncio
    async def test_log_contains_source_ip(self):
        """Log entry should contain source IP."""
        with patch("webhook_handler.logger") as mock_logger:
            mock_logger.info = MagicMock()
            await log_webhook_request("wh4", "203.0.113.42", "valid", "success")
            log_msg = mock_logger.info.call_args[0][0]
            assert "203.0.113.42" in log_msg


# ===========================================================================
# Token and ID generation edge cases
# ===========================================================================


class TestGenerationEdgeCases:
    """Unit tests for edge cases in ID and token generation."""

    def test_webhook_id_length_consistent(self):
        """All generated webhook IDs should have consistent length."""
        lengths = {len(generate_webhook_id()) for _ in range(50)}
        assert lengths == {16}

    def test_auth_token_length_consistent(self):
        """All generated auth tokens should have consistent length."""
        lengths = {len(generate_auth_token()) for _ in range(50)}
        assert lengths == {32}

    def test_no_collisions_in_batch(self):
        """100 IDs generated in a batch should all be unique."""
        ids = [generate_webhook_id() for _ in range(100)]
        assert len(set(ids)) == 100

    def test_no_token_collisions_in_batch(self):
        """100 tokens generated in a batch should all be unique."""
        tokens = [generate_auth_token() for _ in range(100)]
        assert len(set(tokens)) == 100
