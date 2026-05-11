# REST API Design Guide

## Overview

Representational State Transfer (REST) is an architectural style for designing networked applications that leverage HTTP's existing capabilities. This guide provides enterprise-grade standards for designing, implementing, and maintaining REST APIs that are scalable, maintainable, and developer-friendly.

REST APIs form the backbone of modern distributed systems, enabling seamless communication between microservices, client applications, and third-party integrations. Following established design principles ensures consistency across your API portfolio and reduces integration friction for consuming applications.

## Resource-Oriented Architecture

### Designing Resource Models

REST APIs should be fundamentally resource-oriented rather than action-oriented. Resources are the nouns of your API—entities that clients interact with through standard HTTP methods.

**Core principles for resource design:**

- Identify distinct resources within your domain model
- Represent resources as collections and individual items
- Use hierarchical URIs to reflect resource relationships
- Keep resource representations consistent across endpoints
- Version resources independently when needed

**Resource URI structure:**

```
/api/v1/organizations/{org_id}/projects/{project_id}/tasks/{task_id}
```

This hierarchical structure clearly indicates the relationship between organizations, projects, and tasks, improving discoverability and intuitiveness.

### HTTP Method Mapping

Map CRUD operations to standard HTTP methods consistently across all endpoints:

| Operation | HTTP Method | Idempotent | Safe | Status Code |
|-----------|-------------|-----------|------|------------|
| Create | POST | No | No | 201 Created |
| Read | GET | Yes | Yes | 200 OK |
| Update | PUT | Yes | No | 200 OK |
| Partial Update | PATCH | No | No | 200 OK |
| Delete | DELETE | Yes | No | 204 No Content |
| List | GET | Yes | Yes | 200 OK |

**Example resource operations:**

```bash
# Create a new user
POST /api/v1/users
Content-Type: application/json

{
  "email": "user@example.com",
  "name": "John Doe",
  "department": "Engineering"
}

# Response: 201 Created
{
  "id": "usr_abc123",
  "email": "user@example.com",
  "name": "John Doe",
  "department": "Engineering",
  "created_at": "2024-01-15T10:30:00Z"
}
```

## Request and Response Design

### Standardized Request Format

All API requests should follow consistent conventions:

- Use JSON for request and response bodies
- Include `Content-Type: application/json` headers
- Validate input data against defined schemas
- Provide meaningful error messages with appropriate HTTP status codes

**Request validation example:**

```json
POST /api/v1/projects
Content-Type: application/json

{
  "name": "Mobile App Redesign",
  "description": "Complete UI/UX overhaul for iOS and Android",
  "status": "planning",
  "start_date": "2024-02-01",
  "end_date": "2024-06-30",
  "team_members": ["eng_001", "des_002", "pm_003"]
}
```

### Response Envelope Structure

Maintain consistent response formatting to simplify client-side parsing:

```json
{
  "success": true,
  "status": 200,
  "data": {
    "id": "proj_xyz789",
    "name": "Mobile App Redesign",
    "description": "Complete UI/UX overhaul for iOS and Android",
    "status": "planning",
    "created_at": "2024-01-15T14:22:00Z"
  },
  "timestamp": "2024-01-15T14:22:00Z"
}
```

For error responses:

```json
{
  "success": false,
  "status": 400,
  "error": {
    "code": "INVALID_REQUEST",
    "message": "Missing required field: name",
    "details": [
      {
        "field": "name",
        "issue": "Required field cannot be empty"
      }
    ]
  },
  "timestamp": "2024-01-15T14:25:00Z"
}
```

## Filtering, Pagination, and Sorting

### Query Parameter Standards

Implement standard query parameters for list endpoints to handle large datasets efficiently:

**Required parameters:**

- `limit`: Maximum number of results (default: 20, maximum: 100)
- `offset`: Number of results to skip (default: 0)
- `sort`: Sort field and direction (`field:asc` or `field:desc`)
- `filter`: Filter criteria using field-value pairs

**Example list request:**

```bash
GET /api/v1/tasks?offset=0&limit=25&sort=created_at:desc&filter[status]=in_progress&filter[assignee]=usr_abc123

# Response: 200 OK
{
  "success": true,
  "data": [
    {
      "id": "task_001",
      "title": "API Documentation",
      "status": "in_progress",
      "assignee": "usr_abc123"
    },
    {
      "id": "task_002",
      "title": "Code Review",
      "status": "in_progress",
      "assignee": "usr_abc123"
    }
  ],
  "pagination": {
    "limit": 25,
    "offset": 0,
    "total": 47,
    "has_more": true
  }
}
```

### Cursor-Based Pagination

For high-performance scenarios, implement cursor-based pagination instead of offset:

```bash
GET /api/v1/events?cursor=eyJpZCI6ICJldnRfMDAxIn0=&limit=50

# Response includes a cursor for the next batch
{
  "success": true,
  "data": [...],
  "pagination": {
    "next_cursor": "eyJpZCI6ICJldnRfMDUwIn0="
  }
}
```

## Error Handling and Status Codes

### HTTP Status Code Usage

Adopt standard HTTP status codes to communicate operation outcomes:

| Code Range | Category | Common Uses |
|-----------|----------|------------|
| 2xx | Success | Request succeeded as expected |
| 400 | Bad Request | Client-side validation errors |
| 401 | Unauthorized | Missing or invalid authentication |
| 403 | Forbidden | Authenticated but lacks permission |
| 404 | Not Found | Resource does not exist |
| 409 | Conflict | Request conflicts with current state |
| 429 | Rate Limited | Too many requests in time window |
| 500 | Server Error | Unexpected server-side failure |
| 503 | Service Unavailable | Temporary service degradation |

### Error Response Format

**Consistent error handling:**

```bash
GET /api/v1/users/invalid_id

# Response: 404 Not Found
{
  "success": false,
  "status": 404,
  "error": {
    "code": "RESOURCE_NOT_FOUND",
    "message": "User with ID 'invalid_id' does not exist",
    "request_id": "req_abc123def456"
  },
  "timestamp": "2024-01-15T15:00:00Z"
}
```

## Security and Authentication

### Authentication Implementation

Implement industry-standard authentication mechanisms:

**OAuth 2.0 with Bearer tokens:**

```bash
POST /api/v1/auth/token
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&client_id=CLIENT_ID&client_secret=CLIENT_SECRET

# Response: 200 OK
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "Bearer",
  "expires_in": 3600
}
```

**Authenticated request:**

```bash
GET /api/v1/secure-resource
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

### Security Headers

Include essential security headers in all responses:

```bash
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
X-XSS-Protection: 1; mode=block
Strict-Transport-Security: max-age=31536000; includeSubDomains
Content-Security-Policy: default-src 'self'
```

## Versioning and Backward Compatibility

### API Versioning Strategy

Implement URL-based versioning for clear separation of API versions:

```
/api/v1/resources  # Version 1
/api/v2/resources  # Version 2
```

**Version lifecycle:**

- Maintain current version for active development
- Support previous version for 12-18 months
- Provide deprecation notices 6 months before sunset
- Document breaking changes in release notes

**Deprecation warning headers:**

```
Deprecation: true
Sunset: Sun, 31 Dec 2024 23:59:59 GMT
Link: <https://docs.example.com/migration-guide>; rel="deprecation"
```

## Common Pitfalls and Best Practices

### Pitfalls to Avoid

**1. Mixing resource and action-based endpoints:**
```bash
# ❌ Avoid: Action-oriented
POST /api/v1/users/send-email
POST /api/v1/projects/calculate-budget

# ✅ Preferred: Resource-oriented
POST /api/v1/notifications
POST /api/v1/budgets/forecasts
```

**2. Inconsistent naming conventions:**
```bash
# ❌ Avoid: Mixed case styles
/api/v1/UserProfiles
/api/v1/team-members
/api/v1/organizationRoles

# ✅ Preferred: Consistent kebab-case
/api/v1/user-profiles
/api/v1/team-members
/api/v1/organization-roles
```

**3. Returning too much data:**
```bash
# ❌ Avoid: Bloated responses
{
  "user": {
    "id": "usr_001",
    "email": "...",
    "all_related_projects": [...],  # 1000+ items
    "all_tasks": [...],              # 5000+ items
    "historical_activity": [...]     # Complete history
  }
}

# ✅ Preferred: Include links for additional resources
{
  "user": {
    "id": "usr_001",
    "email": "..."
  },
  "_links": {
    "projects": "/api/v1/users/usr_001/projects",
    "tasks": "/api/v1/users/usr_001/tasks"
  }
}
```

### Implementation Best Practices

- **Document thoroughly:** Provide OpenAPI/Swagger specifications for all endpoints
- **Test comprehensively:** Include integration tests for all CRUD operations
- **Monitor performance:** Track response times and implement caching strategies
- **Rate limit appropriately:** Prevent abuse while allowing legitimate usage
- **Maintain backward compatibility:** Avoid breaking changes in existing versions
- **Use HATEOAS where appropriate:** Include hypermedia links for resource navigation

By following these standards, enterprise APIs become more maintainable, scalable, and developer-friendly, reducing integration costs and accelerating time-to-market for dependent applications.