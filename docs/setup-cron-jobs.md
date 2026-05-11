# Cron Jobs Setup Guide

## Overview

Cron jobs allow you to schedule recurring AI agent tasks — daily summaries, periodic checks, scheduled reports, and more. Each cron job sends a message template to a target session on a defined schedule.

## Prerequisites

- Access to the w7-ragKB admin dashboard
- At least one active session to target

## 1. Create a Cron Job

### Via Dashboard

1. Open the admin dashboard → **Gateway** → **Cron Jobs** tab
2. Click **Create Cron Job**
3. Fill in the form:
   - **Cron Job ID**: Auto-generated, or enter a custom identifier
   - **Schedule**: Use the **Common Presets** tab or write a **Custom Expression**
   - **Target Session**: Select the session to receive scheduled messages
   - **Message Template**: The message sent to the agent on each execution
   - **Timezone**: Select your timezone (default: UTC)
4. Enable and click **Create**

### Using the Visual Builder

The **Visual Builder** tab provides a point-and-click cron expression editor:

1. For each field (minute, hour, day, month, weekday), select a mode:
   - **Every**: Wildcard (`*`)
   - **Specific**: Exact values (e.g., `0,15,30,45`)
   - **Range**: From-to (e.g., `9-17`)
   - **Interval**: Every N (e.g., `*/5`)
2. The expression is built automatically
3. A human-readable description is shown below
4. The next 5 execution times are previewed

### Natural Language

Type natural language in the builder's text field:
- "every day at 9am" → `0 9 * * *`
- "every tuesday at 3pm" → `0 15 * * 2`
- "every 5 minutes" → `*/5 * * * *`
- "every hour" → `0 * * * *`

## 2. Cron Expression Reference

```
┌───────────── minute (0-59)
│ ┌───────────── hour (0-23)
│ │ ┌───────────── day of month (1-31)
│ │ │ ┌───────────── month (1-12)
│ │ │ │ ┌───────────── day of week (0-6, Sun=0)
│ │ │ │ │
* * * * *
```

| Expression | Description |
|-----------|-------------|
| `* * * * *` | Every minute |
| `*/5 * * * *` | Every 5 minutes |
| `0 * * * *` | Every hour |
| `0 9 * * *` | Daily at 9:00 AM |
| `0 9 * * 1-5` | Weekdays at 9:00 AM |
| `0 9 * * 1` | Every Monday at 9:00 AM |
| `0 0 1 * *` | First of each month at midnight |
| `0 */6 * * *` | Every 6 hours |

## 3. Message Templates

The message template is the exact text sent to the AI agent. Examples:

```
Generate a daily summary of all conversations from the past 24 hours.
```

```
Check the system health and report any issues.
```

```
Search for the latest news about our project and create a brief.
```

## 4. Managing Cron Jobs

### Pause / Resume

- Click **...** → **Pause** to temporarily stop executions
- Click **...** → **Resume** to re-enable

### Execute Now

- Click **...** → **Execute Now** to trigger an immediate execution outside the schedule

### View History

- Click **...** → **View History** to see past executions with outcomes (success/failure/skipped)

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Job not executing | Check if enabled, verify schedule is valid (use preview) |
| Wrong execution time | Verify timezone setting matches your expectation |
| Execution failed | Check execution history for error messages |
| Target session archived | Update to an active session |
| Too frequent executions | Minimum recommended interval is 1 minute |

## Best Practices

- Use descriptive cron job IDs (e.g., `daily-summary`, `weekly-report`)
- Set appropriate timezones — all times are relative to the configured timezone
- Monitor execution history regularly for failures
- Keep message templates focused — one task per cron job
- Use pause instead of delete when temporarily stopping a job
