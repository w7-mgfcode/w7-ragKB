"""Unit tests for webhook handler endpoints.

Tests cover:
- Webhook registration and URL generation
- Authentication (valid/invalid tokens)
- Payload validation and transformation
- Routing to target sessions
- Error handling (404, 400, 401)
- Webhook management (list, update, delete)
"""

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from http_server import create_app
from webhook_handler import transform_payload, validate_payload_schema


@pytest.fixture
def client():
    """Create test client for FastAPI app."""
    app = create_app()
    return TestClient(app)


@pytest.fixture
def mock_pool():
    """Create mock database pool."""
    pool = AsyncMock()
    return pool


@pytest.fixture
def mock_session():
    """Create mock session."""
    session = AsyncMock()
    session.session_id = "test_session_id"
    session.add_message = AsyncMock()
    return session


@pytest.fixture
def mock_session_manager(mock_session):
    """Create mock session manager."""
    manager = MagicMock()
    manager.get_session = AsyncMock(return_value=mock_session)
    return manager


@pytest.fixture
def sample_webhook():
    """Create sample webhook data."""
    return {
        "webhook_id": "abc123",
        "webhook_url": "/api/webhooks/abc123",
        "auth_token": "secret_token_xyz",
        "target_session_id": "test_session_id",
        "enabled": True,
        "payload_schema": None,
        "transform_rules": {},
        "created_at": datetime.utcnow(),
        "last_triggered_at": None,
    }


class TestWebhookRegistration:
    """Tests for webhook registration endpoint."""
    
    @patch("webhook_handler.get_pool")
    @patch("webhook_handler.create_webhook")
    def test_register_webhook_success(self, mock_create, mock_get_pool, client, mock_pool, sample_webhook):
        """Test successful webhook registration."""
        mock_get_pool.return_value = mock_pool
        mock_create.return_value = sample_webhook
        
        response = client.post(
            "/api/webhooks/register",
            json={
                "target_session_id": "test_session_id",
                "enabled": True,
            },
        )
        
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["webhook_id"] == "abc123"
        assert data["webhook_url"] == "/api/webhooks/abc123"
        assert data["auth_token"] == "secret_token_xyz"
        assert data["target_session_id"] == "test_session_id"
        assert data["enabled"] is True
    
    @patch("webhook_handler.get_pool")
    @patch("webhook_handler.create_webhook")
    def test_register_webhook_with_schema(self, mock_create, mock_get_pool, client, mock_pool, sample_webhook):
        """Test webhook registration with payload schema."""
        schema = {
            "type": "object",
            "properties": {
                "event": {"type": "string"},
                "data": {"type": "object"},
            },
            "required": ["event"],
        }
        
        webhook_with_schema = sample_webhook.copy()
        webhook_with_schema["payload_schema"] = schema
        
        mock_get_pool.return_value = mock_pool
        mock_create.return_value = webhook_with_schema
        
        response = client.post(
            "/api/webhooks/register",
            json={
                "target_session_id": "test_session_id",
                "payload_schema": schema,
                "enabled": True,
            },
        )
        
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["webhook_id"] == "abc123"
    
    @patch("webhook_handler.get_pool")
    @patch("webhook_handler.create_webhook")
    def test_register_webhook_with_transform_rules(self, mock_create, mock_get_pool, client, mock_pool, sample_webhook):
        """Test webhook registration with transformation rules."""
        transform_rules = {
            "jsonpath": {
                "message": "$.data.message",
            },
            "static": {
                "source": "webhook",
            },
        }
        
        webhook_with_rules = sample_webhook.copy()
        webhook_with_rules["transform_rules"] = transform_rules
        
        mock_get_pool.return_value = mock_pool
        mock_create.return_value = webhook_with_rules
        
        response = client.post(
            "/api/webhooks/register",
            json={
                "target_session_id": "test_session_id",
                "transform_rules": transform_rules,
                "enabled": True,
            },
        )
        
        assert response.status_code == status.HTTP_201_CREATED


class TestWebhookTrigger:
    """Tests for webhook trigger endpoint."""
    
    @patch("webhook_handler.get_pool")
    @patch("webhook_handler.verify_webhook_auth")
    @patch("webhook_handler.get_session_manager")
    @patch("webhook_handler.update_webhook_last_triggered")
    def test_trigger_webhook_success(
        self,
        mock_update,
        mock_get_manager,
        mock_verify,
        mock_get_pool,
        client,
        mock_pool,
        mock_session_manager,
        sample_webhook,
    ):
        """Test successful webhook trigger."""
        mock_get_pool.return_value = mock_pool
        mock_verify.return_value = sample_webhook
        mock_get_manager.return_value = mock_session_manager
        mock_update.return_value = None
        
        response = client.post(
            "/api/webhooks/abc123",
            json={"event": "test", "data": {"message": "Hello"}},
            headers={"X-Webhook-Token": "secret_token_xyz"},
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "success"
        assert data["session_id"] == "test_session_id"
        
        # Verify message was added to session
        mock_session_manager.get_session.assert_called_once_with("test_session_id")
    
    @patch("webhook_handler.get_pool")
    def test_trigger_webhook_missing_token(self, mock_get_pool, client, mock_pool):
        """Test webhook trigger with missing authentication token."""
        mock_get_pool.return_value = mock_pool
        
        response = client.post(
            "/api/webhooks/abc123",
            json={"event": "test"},
        )
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "Missing X-Webhook-Token header" in response.json()["detail"]
    
    @patch("webhook_handler.get_pool")
    @patch("webhook_handler.verify_webhook_auth")
    def test_trigger_webhook_invalid_token(self, mock_verify, mock_get_pool, client, mock_pool):
        """Test webhook trigger with invalid authentication token."""
        mock_get_pool.return_value = mock_pool
        mock_verify.return_value = None  # Invalid token
        
        response = client.post(
            "/api/webhooks/abc123",
            json={"event": "test"},
            headers={"X-Webhook-Token": "invalid_token"},
        )
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "Invalid authentication token" in response.json()["detail"]
    
    @patch("webhook_handler.get_pool")
    @patch("webhook_handler.verify_webhook_auth")
    def test_trigger_webhook_invalid_json(self, mock_verify, mock_get_pool, client, mock_pool, sample_webhook):
        """Test webhook trigger with invalid JSON payload."""
        mock_get_pool.return_value = mock_pool
        mock_verify.return_value = sample_webhook
        
        response = client.post(
            "/api/webhooks/abc123",
            data="not valid json",
            headers={
                "X-Webhook-Token": "secret_token_xyz",
                "Content-Type": "application/json",
            },
        )
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Invalid JSON payload" in response.json()["detail"]
    
    @patch("webhook_handler.get_pool")
    @patch("webhook_handler.verify_webhook_auth")
    @patch("webhook_handler.get_session_manager")
    def test_trigger_webhook_session_not_found(
        self,
        mock_get_manager,
        mock_verify,
        mock_get_pool,
        client,
        mock_pool,
        sample_webhook,
    ):
        """Test webhook trigger with non-existent target session."""
        mock_get_pool.return_value = mock_pool
        mock_verify.return_value = sample_webhook
        
        manager = MagicMock()
        manager.get_session = AsyncMock(return_value=None)  # Session not found
        mock_get_manager.return_value = manager
        
        response = client.post(
            "/api/webhooks/abc123",
            json={"event": "test"},
            headers={"X-Webhook-Token": "secret_token_xyz"},
        )
        
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "not found" in response.json()["detail"]
    
    @patch("webhook_handler.get_pool")
    @patch("webhook_handler.verify_webhook_auth")
    def test_trigger_webhook_schema_validation_failure(
        self,
        mock_verify,
        mock_get_pool,
        client,
        mock_pool,
        sample_webhook,
    ):
        """Test webhook trigger with payload that fails schema validation."""
        schema = {
            "type": "object",
            "properties": {
                "event": {"type": "string"},
            },
            "required": ["event"],
        }
        
        webhook_with_schema = sample_webhook.copy()
        webhook_with_schema["payload_schema"] = schema
        
        mock_get_pool.return_value = mock_pool
        mock_verify.return_value = webhook_with_schema
        
        # Payload missing required "event" field
        response = client.post(
            "/api/webhooks/abc123",
            json={"data": "test"},
            headers={"X-Webhook-Token": "secret_token_xyz"},
        )
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "validation failed" in response.json()["detail"].lower()


class TestWebhookManagement:
    """Tests for webhook management endpoints."""
    
    @patch("webhook_handler.get_pool")
    @patch("webhook_handler.list_webhooks")
    def test_list_webhooks(self, mock_list, mock_get_pool, client, mock_pool, sample_webhook):
        """Test listing webhooks."""
        mock_get_pool.return_value = mock_pool
        mock_list.return_value = [sample_webhook]
        
        response = client.get("/api/webhooks")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data) == 1
        assert data[0]["webhook_id"] == "abc123"
    
    @patch("webhook_handler.get_pool")
    @patch("webhook_handler.list_webhooks")
    def test_list_webhooks_with_filters(self, mock_list, mock_get_pool, client, mock_pool, sample_webhook):
        """Test listing webhooks with filters."""
        mock_get_pool.return_value = mock_pool
        mock_list.return_value = [sample_webhook]
        
        response = client.get(
            "/api/webhooks",
            params={
                "target_session_id": "test_session_id",
                "enabled_only": True,
            },
        )
        
        assert response.status_code == status.HTTP_200_OK
        mock_list.assert_called_once_with(
            mock_pool,
            target_session_id="test_session_id",
            enabled_only=True,
        )
    
    @patch("webhook_handler.get_pool")
    @patch("webhook_handler.get_webhook")
    @patch("webhook_handler.update_webhook_enabled")
    def test_update_webhook_enabled(
        self,
        mock_update,
        mock_get,
        mock_get_pool,
        client,
        mock_pool,
        sample_webhook,
    ):
        """Test updating webhook enabled status."""
        mock_get_pool.return_value = mock_pool
        mock_get.return_value = sample_webhook
        mock_update.return_value = None
        
        response = client.put(
            "/api/webhooks/abc123",
            json={"enabled": False},
        )
        
        assert response.status_code == status.HTTP_204_NO_CONTENT
        mock_update.assert_called_once_with(mock_pool, "abc123", False)
    
    @patch("webhook_handler.get_pool")
    @patch("webhook_handler.get_webhook")
    @patch("webhook_handler.update_webhook_transform_rules")
    def test_update_webhook_transform_rules(
        self,
        mock_update,
        mock_get,
        mock_get_pool,
        client,
        mock_pool,
        sample_webhook,
    ):
        """Test updating webhook transformation rules."""
        new_rules = {
            "jsonpath": {
                "text": "$.message",
            },
        }
        
        mock_get_pool.return_value = mock_pool
        mock_get.return_value = sample_webhook
        mock_update.return_value = None
        
        response = client.put(
            "/api/webhooks/abc123",
            json={"transform_rules": new_rules},
        )
        
        assert response.status_code == status.HTTP_204_NO_CONTENT
        mock_update.assert_called_once_with(mock_pool, "abc123", new_rules)
    
    @patch("webhook_handler.get_pool")
    @patch("webhook_handler.get_webhook")
    def test_update_webhook_not_found(self, mock_get, mock_get_pool, client, mock_pool):
        """Test updating non-existent webhook."""
        mock_get_pool.return_value = mock_pool
        mock_get.return_value = None
        
        response = client.put(
            "/api/webhooks/nonexistent",
            json={"enabled": False},
        )
        
        assert response.status_code == status.HTTP_404_NOT_FOUND
    
    @patch("webhook_handler.get_pool")
    @patch("webhook_handler.get_webhook")
    @patch("webhook_handler.delete_webhook")
    def test_delete_webhook(
        self,
        mock_delete,
        mock_get,
        mock_get_pool,
        client,
        mock_pool,
        sample_webhook,
    ):
        """Test deleting webhook."""
        mock_get_pool.return_value = mock_pool
        mock_get.return_value = sample_webhook
        mock_delete.return_value = None
        
        response = client.delete("/api/webhooks/abc123")
        
        assert response.status_code == status.HTTP_204_NO_CONTENT
        mock_delete.assert_called_once_with(mock_pool, "abc123")
    
    @patch("webhook_handler.get_pool")
    @patch("webhook_handler.get_webhook")
    def test_delete_webhook_not_found(self, mock_get, mock_get_pool, client, mock_pool):
        """Test deleting non-existent webhook."""
        mock_get_pool.return_value = mock_pool
        mock_get.return_value = None
        
        response = client.delete("/api/webhooks/nonexistent")
        
        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestPayloadTransformation:
    """Tests for payload transformation functions."""
    
    def test_transform_payload_no_rules(self):
        """Test transformation with no rules returns original payload."""
        payload = {"event": "test", "data": {"message": "Hello"}}
        result = transform_payload(payload, {})
        assert result == payload
    
    def test_transform_payload_jsonpath(self):
        """Test JSONPath transformation."""
        payload = {
            "event": "user.created",
            "data": {
                "user": {
                    "id": 123,
                    "name": "Alice",
                },
            },
        }
        
        rules = {
            "jsonpath": {
                "user_id": "$.data.user.id",
                "user_name": "$.data.user.name",
            },
        }
        
        result = transform_payload(payload, rules)
        assert result["user_id"] == 123
        assert result["user_name"] == "Alice"
    
    def test_transform_payload_jinja2(self):
        """Test Jinja2 template transformation."""
        payload = {
            "first_name": "Alice",
            "last_name": "Smith",
        }
        
        rules = {
            "jinja2": {
                "full_name": "{{ payload.first_name }} {{ payload.last_name }}",
                "greeting": "Hello, {{ payload.first_name }}!",
            },
        }
        
        result = transform_payload(payload, rules)
        assert result["full_name"] == "Alice Smith"
        assert result["greeting"] == "Hello, Alice!"
    
    def test_transform_payload_static(self):
        """Test static field transformation."""
        payload = {"event": "test"}
        
        rules = {
            "static": {
                "source": "webhook",
                "version": "1.0",
            },
        }
        
        result = transform_payload(payload, rules)
        assert result["source"] == "webhook"
        assert result["version"] == "1.0"
    
    def test_transform_payload_combined(self):
        """Test combined transformation rules."""
        payload = {
            "data": {
                "message": "Hello World",
            },
        }
        
        rules = {
            "jsonpath": {
                "text": "$.data.message",
            },
            "jinja2": {
                "formatted": "Message: {{ payload.data.message }}",
            },
            "static": {
                "type": "notification",
            },
        }
        
        result = transform_payload(payload, rules)
        assert result["text"] == "Hello World"
        assert result["formatted"] == "Message: Hello World"
        assert result["type"] == "notification"
    
    def test_transform_payload_jsonpath_no_match(self):
        """Test JSONPath with no matching values."""
        payload = {"event": "test"}
        
        rules = {
            "jsonpath": {
                "missing": "$.data.nonexistent",
            },
        }
        
        result = transform_payload(payload, rules)
        # Should not include the field if no match
        assert "missing" not in result


class TestPayloadValidation:
    """Tests for payload schema validation."""
    
    def test_validate_payload_no_schema(self):
        """Test validation with no schema always passes."""
        payload = {"anything": "goes"}
        assert validate_payload_schema(payload, None) is True
    
    def test_validate_payload_valid(self):
        """Test validation with valid payload."""
        payload = {
            "event": "test",
            "data": {"message": "Hello"},
        }
        
        schema = {
            "type": "object",
            "properties": {
                "event": {"type": "string"},
                "data": {"type": "object"},
            },
            "required": ["event"],
        }
        
        assert validate_payload_schema(payload, schema) is True
    
    def test_validate_payload_missing_required(self):
        """Test validation with missing required field."""
        payload = {"data": {"message": "Hello"}}
        
        schema = {
            "type": "object",
            "properties": {
                "event": {"type": "string"},
            },
            "required": ["event"],
        }
        
        with pytest.raises(Exception):  # ValidationError
            validate_payload_schema(payload, schema)
    
    def test_validate_payload_wrong_type(self):
        """Test validation with wrong field type."""
        payload = {"event": 123}  # Should be string
        
        schema = {
            "type": "object",
            "properties": {
                "event": {"type": "string"},
            },
        }
        
        with pytest.raises(Exception):  # ValidationError
            validate_payload_schema(payload, schema)
