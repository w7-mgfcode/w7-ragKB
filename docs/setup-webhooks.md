# Webhook Setup Guide

## Overview

Webhooks allow external services to trigger AI agent actions via HTTP POST requests. Each webhook is linked to a target session and can transform incoming payloads before processing.

## Prerequisites

- Access to the w7-ragKB admin dashboard
- At least one active session to target
- The external service that will send webhook requests

## 1. Create a Webhook

### Via Dashboard

1. Open the admin dashboard → **Gateway** → **Webhooks** tab
2. Click **Create Webhook**
3. Fill in the form:
   - **Webhook ID**: Auto-generated, or enter a custom identifier
   - **Target Session**: Select the session that will receive messages
   - **Auth Token**: Auto-generated. Copy and save it securely.
   - **Payload Schema** (optional): JSON Schema to validate incoming payloads
   - **Transform Rules** (optional): Rules to transform the payload before processing
4. Enable the webhook and click **Create**

### Via API

```bash
curl -X POST http://your-server:8080/api/gateway/webhooks \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -d '{
    "webhook_id": "github-alerts",
    "target_session_id": "session-abc-123",
    "auth_token": "your-secret-token",
    "enabled": true
  }'
```

## 2. Configure the External Service

Point the external service to your webhook URL:

```
POST https://your-server:8080/api/gateway/webhooks/{webhook_id}/trigger
Authorization: Bearer {auth_token}
Content-Type: application/json

{
  "event": "push",
  "repository": "my-repo",
  "message": "New commit pushed"
}
```

## 3. Transform Rules

Transform rules map incoming payload fields to the message format expected by the agent.

### Visual Editor

Use the **Transform Editor** (click "Open Editor" next to the transform rules field):
1. **Input Panel**: Paste a sample payload
2. **Rules Panel**: Add field mappings:
   - Source path: JSONPath in the incoming payload (e.g., `event.message`)
   - Target path: Field in the output (e.g., `content`)
   - Type: `direct` (copy value) or `template` (string interpolation)
3. **Output Panel**: See the transformed result in real-time

### JSON Format

```json
{
  "rules": [
    { "source": "event.message", "target": "content", "type": "direct" },
    { "source": "event.user", "target": "metadata.sender", "type": "direct" }
  ]
}
```

## 4. Test the Webhook

1. In the Webhooks table, click **...** → **Test**
2. Enter a sample JSON payload
3. Check the response status and body

Or use curl:

```bash
curl -X POST http://your-server:8080/api/gateway/webhooks/{webhook_id}/test \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -d '{"payload": "{\"test\": true}", "auth_token": "your-webhook-token"}'
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| 401 Unauthorized | Check the auth_token matches what's configured |
| 404 Not Found | Verify the webhook_id in the URL |
| Payload rejected | Check payload against the configured JSON Schema |
| Messages not appearing | Verify the target session exists and is active |
| Transform errors | Test with the visual editor to debug field mappings |

## Security Notes

- Always use HTTPS in production
- Rotate auth tokens periodically (use the "Regenerate" button)
- Set a payload schema to reject unexpected data
- Monitor webhook activity in the Security Audit Log
