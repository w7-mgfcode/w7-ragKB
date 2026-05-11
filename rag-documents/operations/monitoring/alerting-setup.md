# Alerting Setup

## Overview

Effective alerting is critical for maintaining system reliability and ensuring rapid response to operational issues. This document provides comprehensive guidance on configuring, deploying, and managing alerts across your enterprise infrastructure. Proper alerting setup reduces mean time to detection (MTTD) and mean time to resolution (MTTR) by ensuring the right teams receive actionable notifications at the right time.

Alert systems act as the bridge between monitoring data collection and incident response. Rather than requiring operators to continuously watch dashboards, well-configured alerts proactively notify appropriate personnel when metrics exceed defined thresholds or anomalous conditions are detected.

## Alert Architecture and Components

### Alert Signal Pipeline

The alerting system processes metrics through a multi-stage pipeline:

1. **Data Collection** - Metrics are scraped or pushed to time-series databases
2. **Rule Evaluation** - Alert rules are evaluated at regular intervals against stored metrics
3. **State Management** - Alert state transitions are tracked (Pending → Firing → Resolved)
4. **Notification Routing** - Triggered alerts are routed to appropriate channels based on rules
5. **Escalation** - Unacknowledged alerts follow escalation policies

### Core Components

| Component | Purpose | Examples |
|-----------|---------|----------|
| Metrics Source | Application/infrastructure data | Prometheus, CloudWatch, Datadog |
| Alert Manager | Routes and deduplicates alerts | Alertmanager, PagerDuty, Opsgenie |
| Notification Channel | Delivery mechanism | Email, Slack, SMS, webhooks |
| On-Call System | Manages escalation policies | PagerDuty, Opsgenie, VictorOps |

## Configuring Alert Rules

### Rule Definition Best Practices

Alert rules should be specific, measurable, and actionable. Poorly defined rules create alert fatigue by generating excessive false positives.

**Rule Structure Components:**

- **Alert Name** - Descriptive identifier (e.g., `HighCPUUtilization`)
- **Condition** - Metric and threshold (e.g., `cpu_usage_percent > 85`)
- **Duration** - Time threshold must be exceeded (e.g., `for 5m`)
- **Labels** - Metadata for routing and grouping (e.g., `severity: critical`)
- **Annotations** - Human-readable context (e.g., runbook links, descriptions)

### Creating Alert Rules

Below is a Prometheus-style alert rule configuration example:

```yaml
groups:
  - name: application_alerts
    interval: 30s
    rules:
      - alert: HighMemoryUsage
        expr: |
          (1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) > 0.85
        for: 5m
        labels:
          severity: warning
          team: platform
        annotations:
          summary: "High memory usage detected on {{ $labels.instance }}"
          description: "Memory usage is {{ $value | humanizePercentage }} on {{ $labels.instance }}"
          runbook: "https://wiki.company.com/runbooks/high-memory-usage"

      - alert: ServiceDown
        expr: up{job="api-service"} == 0
        for: 2m
        labels:
          severity: critical
          team: backend
        annotations:
          summary: "API service is down on {{ $labels.instance }}"
          description: "The API service has been unreachable for more than 2 minutes"
          runbook: "https://wiki.company.com/runbooks/service-restart"

      - alert: DiskSpaceCritical
        expr: |
          (node_filesystem_avail_bytes / node_filesystem_size_bytes) < 0.1
        for: 10m
        labels:
          severity: critical
          team: infrastructure
        annotations:
          summary: "Critical disk space on {{ $labels.instance }}"
          description: "Disk {{ $labels.device }} is {{ $value | humanizePercentage }} full"
```

### Threshold Tuning Strategy

Thresholds should be established based on historical baselines and operational requirements:

1. **Analyze historical metrics** - Identify normal operating ranges
2. **Set warning threshold** - 70-80% of failure point
3. **Set critical threshold** - 85-95% of failure point
4. **Include duration window** - Prevent alerting on transient spikes (minimum 2-5 minutes)
5. **Document rationale** - Maintain change log for threshold adjustments

## Alert Routing and Notification Channels

### Configuring Notification Routes

Alert routing determines which teams receive notifications based on alert labels and severity:

```yaml
alerting:
  alertmanagers:
    - static_configs:
        - targets:
            - alertmanager:9093

route:
  receiver: 'default'
  group_by: ['alertname', 'cluster', 'service']
  group_wait: 10s
  group_interval: 10s
  repeat_interval: 4h

  routes:
    - match:
        severity: critical
      receiver: 'pagerduty-critical'
      continue: true
      repeat_interval: 1h

    - match:
        team: backend
        severity: warning
      receiver: 'backend-team-slack'
      group_wait: 30s

    - match:
        team: infrastructure
      receiver: 'infrastructure-email'
      repeat_interval: 2h
```

### Supported Notification Channels

**Email Notifications:**
- Suitable for non-urgent warnings and informational alerts
- Allows detailed context but may be missed during off-hours
- Configure with appropriate rate-limiting to prevent inbox flooding

**Slack Integration:**
- Ideal for team communication and awareness
- Enables quick acknowledgment and discussion
- Use thread replies to prevent channel clutter

**PagerDuty/On-Call Systems:**
- Mandatory for critical severity alerts
- Integrates with escalation policies and on-call schedules
- Automatically routes to current responder

**SMS/Phone Calls:**
- Reserve for highest severity incidents only
- Configure escalation for critical unacknowledged alerts
- Implement 15-30 minute escalation intervals

## Alert Suppression and Maintenance Windows

### Preventing Alert Storms

Maintenance windows suppress alerts during planned activities to prevent false positives and alert fatigue:

```yaml
silences:
  - matcher_name: alertname
    matcher_value: ServiceDown
    start_time: 2024-03-15T02:00:00Z
    end_time: 2024-03-15T03:00:00Z
    comment: "Database maintenance window - planned downtime"
    created_by: "ops-automation"

  - matcher_name: instance
    matcher_value: db-replica-03
    start_time: 2024-03-15T01:30:00Z
    end_time: 2024-03-15T02:30:00Z
    comment: "Hardware replacement - replica temporary removal"
    created_by: "infrastructure-team"
```

### Inhibition Rules

Inhibit lower-priority alerts when a higher-priority alert is already firing to reduce noise:

```yaml
inhibit_rules:
  - source_match:
      severity: 'critical'
    target_match:
      severity: 'warning'
    equal: ['alertname', 'dev', 'instance']

  - source_match:
      alertname: 'ServiceDown'
    target_match:
      alertname: 'HighLatency'
    equal: ['instance']
```

## Monitoring Alert Quality

### Key Metrics for Alert Health

Continuously monitor your alerting system itself:

- **Alert Volume** - Total number of alerts firing
- **Alert Duration** - How long alerts remain active
- **False Positive Rate** - Alerts that resolve within 5 minutes
- **Mean Time to Acknowledge (MTAA)** - Time from alert to first response
- **Mean Time to Resolve (MTTR)** - Time from alert to recovery

### Common Pitfalls and Solutions

| Problem | Cause | Solution |
|---------|-------|----------|
| Alert Fatigue | Too many non-critical alerts | Adjust thresholds; use inhibition rules |
| Missed Alerts | Inadequate notification redundancy | Configure multi-channel routing |
| Delayed Response | Poor alert context | Add detailed annotations and runbook links |
| False Positives | Insufficient duration windows | Increase `for` duration; account for volatility |

## Testing and Validation

### Alert Rule Testing

```bash
# Validate alert rules syntax
promtool check rules alert-rules.yaml

# Test alert rules against metrics
promtool test rules test-cases.yaml

# Dry-run alert evaluation
curl 'http://prometheus:9090/api/v1/query?query=up'
```

### Incident Simulation

Conduct regular "disaster recovery" drills to validate alerting:

1. Simulate service degradation in non-production environment
2. Verify alerts fire and route to correct teams
3. Test escalation workflow if not acknowledged
4. Document response time and feedback
5. Update runbooks based on findings

## Best Practices and Recommendations

- **Establish Alert Ownership** - Assign each alert to a specific team responsible for runbook maintenance
- **Document All Alerts** - Maintain runbook for every critical and warning alert
- **Use Severity Labels Consistently** - Enforce standard severity levels across all alert rules
- **Implement Alert Review Process** - Quarterly review of alert performance metrics and adjustments
- **Set Realistic Thresholds** - Based on SLA requirements, not arbitrary percentages
- **Avoid Alert Cascade** - Parent alerts should suppress dependent alerts to prevent storms
- **Version Control** - Store all alert configurations in Git with change tracking
- **Monitor the Monitors** - Actively track alert generation metrics and adjust accordingly

---

**Document Version:** 2.1  
**Last Updated:** 2024-03-15  
**Maintainer:** Platform Operations Team