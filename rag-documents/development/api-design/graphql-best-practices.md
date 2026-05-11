# GraphQL Best Practices

GraphQL has emerged as a powerful alternative to traditional REST APIs, enabling clients to request precisely the data they need. This document provides enterprise development teams with standardized practices for designing, implementing, and maintaining secure, performant GraphQL APIs.

## Schema Design and Architecture

### Naming Conventions and Structure

Establishing consistent naming conventions is fundamental to maintainable GraphQL APIs. Type names should use PascalCase, while field names and arguments should use camelCase. Query root types should describe specific resources or collections, and mutations should use verb-noun combinations.

```graphql
type User {
  id: ID!
  firstName: String!
  lastName: String!
  emailAddress: String!
  createdAt: DateTime!
}

type Query {
  user(id: ID!): User
  users(limit: Int = 10, offset: Int = 0): [User!]!
}

type Mutation {
  createUser(input: CreateUserInput!): UserPayload!
  updateUserEmail(userId: ID!, newEmail: String!): UserPayload!
}
```

Organize types logically by domain boundaries. Related types should be grouped together, with clear relationships defined through interfaces and connections. Avoid exposing internal database structures directly; instead, create domain-specific types that represent business entities.

### Schema Versioning Strategy

Rather than creating API versions (v1, v2), GraphQL recommends evolving your schema through additive changes. Deprecate fields and types instead of removing them, allowing clients time to migrate.

```graphql
type User {
  id: ID!
  name: String! @deprecated(reason: "Use firstName and lastName fields instead")
  firstName: String!
  lastName: String!
}
```

Maintain backward compatibility by:
- Adding new fields without removing existing ones
- Making new arguments optional with sensible defaults
- Creating new query/mutation roots rather than changing existing ones
- Using deprecation notices for 6+ months before removal

## Query Optimization and Performance

### Implementing Pagination Correctly

Offset-based pagination becomes inefficient with large datasets. Implement cursor-based pagination using the Relay connection pattern for scalability.

```graphql
type UserConnection {
  edges: [UserEdge!]!
  pageInfo: PageInfo!
  totalCount: Int!
}

type UserEdge {
  cursor: String!
  node: User!
}

type PageInfo {
  hasNextPage: Boolean!
  hasPreviousPage: Boolean!
  startCursor: String
  endCursor: String
}

type Query {
  users(first: Int, after: String, last: Int, before: String): UserConnection!
}
```

Use opaque cursors encoded in base64, typically containing the record ID and offset metadata. Limit the `first` and `last` parameters with reasonable maximums (typically 100-1000 items) to prevent resource exhaustion.

### N+1 Query Prevention

The most common performance pitfall in GraphQL is the N+1 query problem. When resolving nested fields, implement DataLoader for batching database queries.

```javascript
const DataLoader = require('dataloader');

const userLoader = new DataLoader(async (userIds) => {
  const users = await db.users.findByIds(userIds);
  return userIds.map(id => users.find(user => user.id === id));
});

const resolvers = {
  Post: {
    author: (post) => userLoader.load(post.authorId)
  }
};
```

Key optimization strategies include:
- Batch database queries using DataLoader
- Cache expensive computations at the resolver level
- Implement query complexity analysis to reject overly expensive queries
- Use connection pooling for database connections
- Monitor resolver execution times in production

## Security and Authorization

### Authentication and Authorization Patterns

Implement authorization checks at the field level, not just at the query level. This provides granular control and prevents information leakage through partial responses.

```javascript
const resolvers = {
  User: {
    emailAddress: (user, args, context) => {
      if (context.user?.id !== user.id && !context.user?.isAdmin) {
        throw new Error('Unauthorized');
      }
      return user.emailAddress;
    },
    ssn: (user, args, context) => {
      if (!context.user?.hasPermission('VIEW_SENSITIVE_DATA')) {
        return null;
      }
      return user.ssn;
    }
  }
};
```

Use JWT tokens in the Authorization header for stateless authentication:

```
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

| Authorization Pattern | Use Case | Pros | Cons |
|---|---|---|---|
| Field-level directives | Role-based access | Declarative, reusable | Can be verbose |
| Resolver guards | Complex rules | Flexible, testable | Logic scattered |
| Middleware | Global checks | Centralized, efficient | Limited field context |
| Schema stitching | Multi-service | Modular | Complex to maintain |

### Input Validation and Rate Limiting

Validate all input at the schema level and in resolvers. Implement rate limiting per user, IP, or API key to prevent abuse.

```graphql
input CreateUserInput {
  firstName: String!
  lastName: String!
  emailAddress: String!
  age: Int!
}

type Mutation {
  createUser(input: CreateUserInput!): UserPayload!
}
```

Validation rules:
- Enforce string length limits (minLength, maxLength directives)
- Validate email and URL formats
- Restrict numeric ranges
- Implement query complexity limits to prevent resource exhaustion
- Apply rate limiting: 100 requests/minute for standard users, 1000/minute for premium

## Error Handling and Resilience

### Structured Error Responses

Return consistent, detailed error information that aids debugging without exposing sensitive infrastructure details.

```json
{
  "errors": [
    {
      "message": "Invalid email format",
      "extensions": {
        "code": "BAD_USER_INPUT",
        "fieldName": "emailAddress",
        "validationRule": "EMAIL_FORMAT",
        "timestamp": "2024-01-15T10:30:00Z"
      }
    }
  ]
}
```

Implement custom error codes for different failure scenarios:
- `AUTHENTICATION_REQUIRED` - User not authenticated
- `FORBIDDEN` - User lacks permissions
- `BAD_USER_INPUT` - Client-side validation failure
- `INTERNAL_SERVER_ERROR` - Unexpected server error (never expose stack traces)
- `SERVICE_UNAVAILABLE` - Dependency failure

### Timeout and Fallback Strategies

Configure appropriate timeouts for resolver execution and implement fallback mechanisms for non-critical fields.

```javascript
const resolvers = {
  User: {
    recommendations: async (user, args, context) => {
      try {
        return await Promise.race([
          fetchRecommendations(user.id),
          timeout(5000)
        ]);
      } catch (error) {
        return []; // Return empty recommendations on timeout
      }
    }
  }
};

function timeout(ms) {
  return new Promise((_, reject) => 
    setTimeout(() => reject(new Error('Resolver timeout')), ms)
  );
}
```

## Testing and Documentation

### Query Testing Best Practices

Implement comprehensive test coverage for resolvers, including happy paths, error cases, and authorization scenarios.

```javascript
describe('User resolver', () => {
  it('should return user by ID', async () => {
    const query = `
      query GetUser($id: ID!) {
        user(id: $id) {
          id
          firstName
          lastName
        }
      }
    `;
    const result = await execute(query, { id: '123' });
    expect(result.data.user.id).toBe('123');
  });

  it('should deny access to sensitive fields without permission', async () => {
    const context = { user: { id: 'user1' } };
    const result = await resolveWithContext(query, context);
    expect(result.data.user.ssn).toBeNull();
  });
});
```

### API Documentation

Use tools like GraphQL Playground or Apollo Studio to expose interactive documentation. Add comprehensive descriptions to all types and fields.

```graphql
"""
Represents a user account in the system.
Users can create posts, follow other users, and manage their profile.
"""
type User {
  """
  Unique identifier for the user. Never changes after account creation.
  """
  id: ID!
  
  """
  The user's email address. Only visible to the user and administrators.
  """
  emailAddress: String!
}
```

## Monitoring and Operations

Set up comprehensive monitoring to track API performance and reliability:

- Query execution time percentiles (p50, p95, p99)
- Resolver-level performance metrics
- Error rates by error code
- Cache hit rates and DataLoader batching efficiency
- Authentication failure rates
- Rate limiting rejection counts

Establish alerting thresholds for degraded performance or unusual error patterns, enabling rapid incident response.