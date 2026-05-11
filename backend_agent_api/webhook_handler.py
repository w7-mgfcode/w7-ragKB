"""Webhook handler with FastAPI endpoints for webhook registration and triggering.

This module implements the webhook system with:
- Webhook registration and URL generation
- Token-based authentication
- Payload schema validation using Pydantic
- Payload transformation using JSONPath and Jinja2
- Routing to target sessions
- Webhook logging and management

All webhook requests are logged with timestamp, source IP, auth status, and routing outcome.
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, Optional

import jsonschema
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field, ValidationError

from db import get_pool
from db_webhooks import (
    create_webhook,
    delete_webhook,
    get_webhook,
    list_webhooks,
    update_webhook_enabled,
    update_webhook_last_triggered,
    update_webhook_transform_rules,
    verify_webhook_auth,
)
from session_manager import get_session_manager

logger = logging.getLogger(__name__)

router = APIRouter()


# Pydantic models for request/response validation
class WebhookRegistrationRequest(BaseModel):
    """Request model for webhook registration."""
    
    target_session_id: str = Field(..., description="Session ID to route webhook messages to")
    payload_schema: Optional[Dict[str, Any]] = Field(None, description="JSON schema for payload validation")
    transform_rules: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Transformation rules for payload")
    enabled: bool = Field(True, description="Whether the webhook is enabled")


class WebhookRegistrationResponse(BaseModel):
    """Response model for webhook registration."""
    
    webhook_id: str
    webhook_url: str
    auth_token: str
    target_session_id: str
    enabled: bool
    created_at: datetime


class WebhookUpdateRequest(BaseModel):
    """Request model for webhook updates."""
    
    enabled: Optional[bool] = Field(None, description="Whether the webhook is enabled")
    transform_rules: Optional[Dict[str, Any]] = Field(None, description="Transformation rules for payload")


class WebhookListResponse(BaseModel):
    """Response model for webhook listing."""
    
    webhook_id: str
    webhook_url: str
    target_session_id: str
    enabled: bool
    created_at: datetime
    last_triggered_at: Optional[datetime]


class WebhookTriggerResponse(BaseModel):
    """Response model for webhook trigger."""
    
    status: str
    message: str
    session_id: Optional[str] = None


def validate_payload_schema(payload: Dict[str, Any], schema: Optional[Dict[str, Any]]) -> bool:
    """Validate payload against JSON schema.
    
    Args:
        payload: Payload to validate
        schema: JSON schema (optional)
        
    Returns:
        True if valid or no schema provided
        
    Raises:
        ValidationError: If payload doesn't match schema
    """
    if schema is None:
        return True
    
    try:
        jsonschema.validate(instance=payload, schema=schema)
        return True
    except jsonschema.ValidationError as e:
        logger.warning(f"Payload validation failed: {e.message}")
        raise ValidationError(f"Payload validation failed: {e.message}")
    except Exception as e:
        logger.error(f"Schema validation error: {e}", exc_info=True)
        raise ValidationError(f"Schema validation error: {str(e)}")


def transform_payload(payload: Dict[str, Any], rules: Dict[str, Any]) -> Dict[str, Any]:
    """Transform payload using JSONPath and Jinja2 templates.
    
    Transformation rules format:
    {
        "jsonpath": {
            "field_name": "$.path.to.value"
        },
        "jinja2": {
            "field_name": "{{ payload.field }}"
        },
        "static": {
            "field_name": "static_value"
        }
    }
    
    Args:
        payload: Original payload
        rules: Transformation rules
        
    Returns:
        Transformed payload
    """
    if not rules:
        return payload
    
    transformed = {}
    
    # Apply JSONPath transformations
    if "jsonpath" in rules:
        from jsonpath_ng import parse
        
        for field_name, path_expr in rules["jsonpath"].items():
            try:
                jsonpath_expr = parse(path_expr)
                matches = jsonpath_expr.find(payload)
                if matches:
                    transformed[field_name] = matches[0].value
                else:
                    logger.warning(f"JSONPath {path_expr} matched no values")
            except Exception as e:
                logger.error(f"JSONPath transformation error for {field_name}: {e}")
    
    # Apply Jinja2 transformations
    if "jinja2" in rules:
        from jinja2 import Template
        
        for field_name, template_str in rules["jinja2"].items():
            try:
                template = Template(template_str)
                transformed[field_name] = template.render(payload=payload)
            except Exception as e:
                logger.error(f"Jinja2 transformation error for {field_name}: {e}")
    
    # Apply static transformations
    if "static" in rules:
        transformed.update(rules["static"])
    
    # If no transformations applied, return original payload
    return transformed if transformed else payload


async def log_webhook_request(
    webhook_id: str,
    source_ip: str,
    auth_status: str,
    routing_outcome: str,
    error_message: Optional[str] = None,
) -> None:
    """Log webhook request with all required fields.
    
    Args:
        webhook_id: Webhook identifier
        source_ip: Source IP address
        auth_status: Authentication status (valid, invalid, missing)
        routing_outcome: Routing outcome (success, failed, error)
        error_message: Optional error message
    """
    log_entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "webhook_id": webhook_id,
        "source_ip": source_ip,
        "auth_status": auth_status,
        "routing_outcome": routing_outcome,
    }
    
    if error_message:
        log_entry["error"] = error_message
    
    logger.info(f"Webhook request: {json.dumps(log_entry)}")


@router.post("/api/webhooks/register", response_model=WebhookRegistrationResponse, status_code=status.HTTP_201_CREATED)
async def register_webhook(request: WebhookRegistrationRequest) -> WebhookRegistrationResponse:
    """Register a new webhook.
    
    Creates a new webhook with a unique URL and authentication token.
    The webhook can be configured with payload schema validation and transformation rules.
    
    Args:
        request: Webhook registration request
        
    Returns:
        Webhook registration response with URL and auth token
        
    Raises:
        HTTPException: If database operation fails
    """
    try:
        pool = await get_pool()
        
        # Create webhook in database
        webhook = await create_webhook(
            pool,
            target_session_id=request.target_session_id,
            payload_schema=request.payload_schema,
            transform_rules=request.transform_rules,
            enabled=request.enabled,
        )
        
        logger.info(
            f"Registered webhook {webhook['webhook_id']} "
            f"for session {request.target_session_id}"
        )
        
        return WebhookRegistrationResponse(
            webhook_id=webhook["webhook_id"],
            webhook_url=webhook["webhook_url"],
            auth_token=webhook["auth_token"],
            target_session_id=webhook["target_session_id"],
            enabled=webhook["enabled"],
            created_at=webhook["created_at"],
        )
    
    except Exception as e:
        logger.error(f"Failed to register webhook: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to register webhook: {str(e)}",
        )


@router.post("/api/webhooks/{webhook_id}", response_model=WebhookTriggerResponse)
async def trigger_webhook(webhook_id: str, request: Request) -> WebhookTriggerResponse:
    """Trigger a webhook by sending payload to target session.
    
    This is the public endpoint that external systems call to trigger webhooks.
    Authentication is done via X-Webhook-Token header.
    
    Args:
        webhook_id: Webhook identifier
        request: FastAPI request object
        
    Returns:
        Webhook trigger response
        
    Raises:
        HTTPException: If authentication fails, webhook not found, or routing fails
    """
    source_ip = request.client.host if request.client else "unknown"
    
    # Get authentication token from header
    auth_token = request.headers.get("X-Webhook-Token")
    
    if not auth_token:
        await log_webhook_request(
            webhook_id,
            source_ip,
            "missing",
            "failed",
            "Missing authentication token",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Webhook-Token header",
        )
    
    try:
        pool = await get_pool()
        
        # Verify authentication
        webhook_url = f"/api/webhooks/{webhook_id}"
        webhook = await verify_webhook_auth(pool, webhook_url, auth_token)
        
        if not webhook:
            await log_webhook_request(
                webhook_id,
                source_ip,
                "invalid",
                "failed",
                "Invalid authentication token or webhook disabled",
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication token or webhook disabled",
            )
        
        # Parse payload
        try:
            payload = await request.json()
        except Exception as e:
            await log_webhook_request(
                webhook_id,
                source_ip,
                "valid",
                "failed",
                f"Invalid JSON payload: {str(e)}",
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid JSON payload: {str(e)}",
            )
        
        # Validate payload schema
        try:
            validate_payload_schema(payload, webhook.get("payload_schema"))
        except ValidationError as e:
            await log_webhook_request(
                webhook_id,
                source_ip,
                "valid",
                "failed",
                f"Payload validation failed: {str(e)}",
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Payload validation failed: {str(e)}",
            )
        
        # Transform payload
        transform_rules = webhook.get("transform_rules", {})
        transformed_payload = transform_payload(payload, transform_rules)
        
        # Get target session
        session_manager = get_session_manager()
        if not session_manager:
            await log_webhook_request(
                webhook_id,
                source_ip,
                "valid",
                "error",
                "Session manager not initialized",
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Session manager not initialized",
            )
        
        target_session_id = webhook["target_session_id"]
        session = await session_manager.get_session(target_session_id)
        
        if not session:
            await log_webhook_request(
                webhook_id,
                source_ip,
                "valid",
                "failed",
                f"Target session {target_session_id} not found",
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Target session {target_session_id} not found",
            )
        
        # Send message to session
        message_content = json.dumps(transformed_payload, indent=2)
        await session.add_message(
            role="user",
            content=f"Webhook triggered:\n```json\n{message_content}\n```",
            metadata={
                "webhook_id": webhook_id,
                "source_ip": source_ip,
                "original_payload": payload,
                "transformed_payload": transformed_payload,
            },
        )
        
        # Update last_triggered_at
        await update_webhook_last_triggered(pool, webhook_id)
        
        await log_webhook_request(
            webhook_id,
            source_ip,
            "valid",
            "success",
        )
        
        logger.info(
            f"Webhook {webhook_id} triggered successfully, "
            f"routed to session {target_session_id}"
        )
        
        return WebhookTriggerResponse(
            status="success",
            message="Webhook triggered successfully",
            session_id=target_session_id,
        )
    
    except HTTPException:
        raise
    
    except Exception as e:
        await log_webhook_request(
            webhook_id,
            source_ip,
            "valid",
            "error",
            str(e),
        )
        logger.error(f"Failed to trigger webhook {webhook_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to trigger webhook: {str(e)}",
        )


@router.get("/api/webhooks", response_model=list[WebhookListResponse])
async def list_webhooks_endpoint(
    target_session_id: Optional[str] = None,
    enabled_only: bool = False,
) -> list[WebhookListResponse]:
    """List webhooks with optional filters.
    
    Args:
        target_session_id: Optional filter by target session
        enabled_only: If True, only return enabled webhooks
        
    Returns:
        List of webhooks
        
    Raises:
        HTTPException: If database operation fails
    """
    try:
        pool = await get_pool()
        
        webhooks = await list_webhooks(
            pool,
            target_session_id=target_session_id,
            enabled_only=enabled_only,
        )
        
        return [
            WebhookListResponse(
                webhook_id=webhook["webhook_id"],
                webhook_url=webhook["webhook_url"],
                target_session_id=webhook["target_session_id"],
                enabled=webhook["enabled"],
                created_at=webhook["created_at"],
                last_triggered_at=webhook.get("last_triggered_at"),
            )
            for webhook in webhooks
        ]
    
    except Exception as e:
        logger.error(f"Failed to list webhooks: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list webhooks: {str(e)}",
        )


@router.put("/api/webhooks/{webhook_id}", status_code=status.HTTP_204_NO_CONTENT)
async def update_webhook_endpoint(webhook_id: str, request: WebhookUpdateRequest) -> None:
    """Update a webhook's configuration.
    
    Args:
        webhook_id: Webhook identifier
        request: Webhook update request
        
    Raises:
        HTTPException: If webhook not found or database operation fails
    """
    try:
        pool = await get_pool()
        
        # Check if webhook exists
        webhook = await get_webhook(pool, webhook_id)
        if not webhook:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Webhook {webhook_id} not found",
            )
        
        # Update enabled status
        if request.enabled is not None:
            await update_webhook_enabled(pool, webhook_id, request.enabled)
            logger.info(f"Updated webhook {webhook_id} enabled status: {request.enabled}")
        
        # Update transform rules
        if request.transform_rules is not None:
            await update_webhook_transform_rules(pool, webhook_id, request.transform_rules)
            logger.info(f"Updated webhook {webhook_id} transform rules")
    
    except HTTPException:
        raise
    
    except Exception as e:
        logger.error(f"Failed to update webhook {webhook_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update webhook: {str(e)}",
        )


@router.delete("/api/webhooks/{webhook_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_webhook_endpoint(webhook_id: str) -> None:
    """Delete a webhook.
    
    Args:
        webhook_id: Webhook identifier
        
    Raises:
        HTTPException: If webhook not found or database operation fails
    """
    try:
        pool = await get_pool()
        
        # Check if webhook exists
        webhook = await get_webhook(pool, webhook_id)
        if not webhook:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Webhook {webhook_id} not found",
            )
        
        # Delete webhook
        await delete_webhook(pool, webhook_id)
        
        logger.info(f"Deleted webhook {webhook_id}")
    
    except HTTPException:
        raise
    
    except Exception as e:
        logger.error(f"Failed to delete webhook {webhook_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete webhook: {str(e)}",
        )
