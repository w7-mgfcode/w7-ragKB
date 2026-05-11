# Deployment Checklist

## Pre-Deployment Verification

Before initiating any deployment to production or staging environments, verify that all systems and prerequisites are in place. This phase is critical for preventing deployment failures and minimizing rollback scenarios.

### Environment Prerequisites

Ensure the target environment meets the following requirements:

- **Compute Resources**: Verify CPU, memory, and disk space allocation matches application requirements. Minimum recommended resources should be 25% above peak usage projections.
- **Network Connectivity**: Confirm all required ports are open and firewall rules are configured. Test connectivity to dependent services including databases, message queues, and external APIs.
- **Package Dependencies**: Validate that all required system libraries, runtime versions, and language packages are installed.

Run the environment validation script:

```bash
#!/bin/bash
# Environment validation script

echo "Checking system requirements..."
CPU_CORES=$(nproc)
MEMORY_GB=$(free -g | awk '/^Mem:/{print $2}')
DISK_GB=$(df / | awk 'NR==2{print $4/1024/1024}')

echo "Available CPU cores: $CPU_CORES"
echo "Available memory: ${MEMORY_GB}GB"
echo "Available disk space: ${DISK_GB}GB"

# Check required services
for service in postgresql redis nginx; do
    if systemctl is-active --quiet $service; then
        echo "✓ $service is running"
    else
        echo "✗ $service is not running"
        exit 1
    fi
done

echo "Environment validation completed successfully"
```

### CI/CD Pipeline Verification

| Pipeline Stage | Status Check | Success Criteria |
|---|---|---|
| Source Control | Branch protection enabled | Required reviewers: 2 |
| Unit Tests | Code coverage threshold | Minimum 80% coverage |
| Integration Tests | Database migration tests | All migrations succeed |
| Security Scanning | SAST and dependency checks | Zero critical vulnerabilities |
| Build Artifacts | Container image validation | Image signed and scanned |

Confirm the following pipeline components before deployment:

- All commits are merged to the main branch through approved pull requests
- Automated test suites pass with no failures
- Code coverage metrics meet the organization's minimum threshold (typically 80%)
- Security scanning has completed with no critical or high-severity vulnerabilities
- Build artifacts are properly tagged and stored in the container registry

## Pre-Deployment Testing

Comprehensive testing must be completed in a staging environment that mirrors production configurations as closely as possible.

### Smoke Testing Procedures

Execute smoke tests immediately after deployment to verify core functionality:

```bash
#!/bin/bash
# Smoke test script

DEPLOYMENT_URL="https://staging.example.com"
TEST_TIMEOUT=30

# Test application health endpoint
echo "Testing health endpoint..."
HEALTH_RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" \
  --connect-timeout 5 \
  --max-time $TEST_TIMEOUT \
  "$DEPLOYMENT_URL/health")

if [ "$HEALTH_RESPONSE" != "200" ]; then
    echo "✗ Health check failed with status: $HEALTH_RESPONSE"
    exit 1
fi

# Test critical API endpoints
ENDPOINTS=(
    "/api/v1/users"
    "/api/v1/services"
    "/api/v1/config"
)

for endpoint in "${ENDPOINTS[@]}"; do
    RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" \
      "$DEPLOYMENT_URL$endpoint")
    echo "Endpoint $endpoint: $RESPONSE"
done

echo "Smoke tests completed successfully"
```

### Load Testing Requirements

Before deploying to production, validate the application's performance under expected load:

- Establish baseline performance metrics from the previous production deployment
- Simulate user load at 150% of average daily traffic
- Monitor response times, error rates, and resource utilization
- Identify any performance regressions or bottlenecks

Example load testing configuration:

```yaml
# Load test configuration (k6 script)
import http from 'k6/http';
import { check, sleep } from 'k6';

export let options = {
  vus: 100,
  duration: '5m',
  thresholds: {
    http_req_duration: ['p(95)<500', 'p(99)<1000'],
    http_req_failed: ['rate<0.05'],
  },
};

export default function() {
  let response = http.get('https://staging.example.com/api/v1/users');
  check(response, {
    'status is 200': (r) => r.status === 200,
    'response time < 500ms': (r) => r.timings.duration < 500,
  });
  sleep(1);
}
```

## Deployment Execution

### Database Migration Strategy

Perform database migrations according to your selected strategy:

```sql
-- Migration file: 20240115_add_user_preferences.sql

-- Step 1: Create new table in backward-compatible manner
CREATE TABLE IF NOT EXISTS user_preferences (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    theme VARCHAR(50) DEFAULT 'light',
    notification_enabled BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_user_preferences_user_id ON user_preferences(user_id);

-- Step 2: Backfill existing data (run separately if large volume)
INSERT INTO user_preferences (user_id)
SELECT id FROM users
WHERE id NOT IN (SELECT DISTINCT user_id FROM user_preferences);

-- Step 3: Add constraints after data validation
ALTER TABLE user_preferences 
ADD CONSTRAINT uk_user_preferences_user_id UNIQUE(user_id);
```

Key migration best practices:

- Deploy database schema changes in advance of application code
- Use zero-downtime migration techniques for production systems
- Test rollback procedures for every migration
- Maintain separate up and down migration scripts

### Rolling Deployment Configuration

Configure your deployment orchestration platform for gradual traffic shifting:

```yaml
# Kubernetes rolling update configuration
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api-service
spec:
  replicas: 3
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      app: api-service
  template:
    metadata:
      labels:
        app: api-service
    spec:
      containers:
      - name: api-service
        image: registry.example.com/api-service:v2.1.0
        ports:
        - containerPort: 8080
        livenessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /ready
            port: 8080
          initialDelaySeconds: 10
          periodSeconds: 5
```

## Post-Deployment Validation

### Monitoring and Alerting Setup

Immediately after deployment, activate enhanced monitoring:

- Increase log aggregation verbosity for the first 24 hours
- Set alert thresholds at 75% of critical limits to catch issues early
- Monitor error rates, latency percentiles (p95, p99), and resource utilization
- Track business-critical metrics specific to your application

### Health Check Procedures

Validate system health with the following comprehensive checks:

- **Application Level**: Verify all service endpoints respond with correct data
- **Infrastructure Level**: Confirm CPU usage remains below 60%, memory below 70%, disk I/O within normal ranges
- **Database Level**: Verify query performance hasn't degraded; check connection pool utilization
- **External Dependencies**: Validate connectivity and response times for third-party services

## Rollback Procedures

If deployment issues are identified, execute rollback immediately:

```bash
#!/bin/bash
# Rollback script

PREVIOUS_VERSION=$(git describe --tags --abbrev=0 HEAD^)
DEPLOYMENT_NAME="api-service"

echo "Initiating rollback to version: $PREVIOUS_VERSION"

# Update deployment to previous image
kubectl set image deployment/$DEPLOYMENT_NAME \
  $DEPLOYMENT_NAME=registry.example.com/$DEPLOYMENT_NAME:$PREVIOUS_VERSION \
  --namespace=production

# Wait for rollout to complete
kubectl rollout status deployment/$DEPLOYMENT_NAME \
  --namespace=production \
  --timeout=5m

# Verify rollback success
CURRENT_IMAGE=$(kubectl get deployment $DEPLOYMENT_NAME \
  --namespace=production \
  -o jsonpath='{.spec.template.spec.containers[0].image}')

echo "Rollback completed. Current image: $CURRENT_IMAGE"
```

## Common Pitfalls and Troubleshooting

**Pitfall**: Deploying without verifying backward compatibility
- **Solution**: Run integration tests against both new and previous API versions

**Pitfall**: Insufficient database connection pooling after scaling
- **Solution**: Monitor connection pool metrics and increase pool size by 25% per additional pod replica

**Pitfall**: Missing environment variable configuration in target environment
- **Solution**: Use configuration validation scripts to compare staging and production secrets before deployment

Always maintain a deployment runbook with contact information for on-call engineers and escalation procedures for critical issues.