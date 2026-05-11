import { test, expect, Page } from '@playwright/test';
import { setupAuthenticatedMocks, setupAgentAPIMocks } from './mocks';

// --- Mock data for the System Monitor ---

const adminUser = {
  id: 'test-user-123',
  email: 'test@example.com',
  full_name: 'Test User',
  avatar_url: null,
  is_admin: true,
};

const adminSession = {
  access_token: 'mock-access-token',
  user: adminUser,
};

const mockMonitorData = {
  health: {
    services: [
      { name: 'Slack Bot', status: 'healthy', details: null },
      { name: 'Database Pool', status: 'healthy', details: null },
      { name: 'HTTP Server', status: 'healthy', details: null },
      { name: 'RAG Pipeline', status: 'healthy', details: null },
    ],
    uptime_seconds: 3600,
  },
  models: {
    llm_model: 'gemini-2.0-flash',
    embedding_model: 'text-embedding-004',
    embedding_dimensions: 768,
    gcp_project: 'my-project',
    gcp_region: 'us-central1',
  },
  database: {
    pool_size: 10,
    pool_min: 2,
    pool_max: 10,
    pool_free: 8,
    pool_used: 2,
    db_version: 'PostgreSQL 16.1',
    total_conversations: 42,
    total_messages: 350,
    total_documents: 15,
    total_web_users: 5,
  },
  logs: {
    records: [
      { timestamp: '2024-01-15T10:30:00Z', logger: 'uvicorn', level: 'INFO', message: 'Server started' },
      { timestamp: '2024-01-15T10:31:00Z', logger: 'agent', level: 'WARNING', message: 'Slow response' },
    ],
    total_buffered: 2,
  },
  slack: {
    bot_token_configured: true,
    app_token_configured: true,
    socket_handlers_count: 3,
  },
  resources: {
    process_memory_mb: 256.5,
    system_memory_total_mb: 4096,
    system_memory_used_mb: 2048,
    system_memory_available_mb: 2048,
    cpu_percent: 25.0,
    disk_total_gb: 50.0,
    disk_used_gb: 20.0,
    disk_free_gb: 30.0,
  },
  rag: {
    total_documents: 15,
    total_chunks: 120,
    last_indexed_at: '2024-01-15T09:00:00Z',
  },
  api_metrics: {
    endpoints: [
      { path: '/api/admin/monitor/all', request_count: 10, avg_response_time_ms: 45.2 },
    ],
  },
  environment: {
    python_version: '3.11.6',
    dependencies: [
      { name: 'fastapi', version: '0.104.1' },
      { name: 'pydantic-ai', version: '0.1.0' },
    ],
    config: { LLM_CHOICE: 'gemini-2.0-flash' },
  },
};

/**
 * Set up mocks for an authenticated admin user with all System Monitor endpoints.
 */
async function setupAdminMonitorMocks(page: Page) {
  // Start with the standard authenticated mocks (refresh, me, logout, conversations, admin/status)
  await setupAuthenticatedMocks(page);
  await setupAgentAPIMocks(page);

  // Override: make the user an admin
  await page.route('**/api/auth/refresh', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(adminSession),
    });
  });

  await page.route('**/api/auth/me', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(adminUser),
    });
  });

  await page.route('**/api/admin/status', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ is_admin: true }),
    });
  });

  // Mock admin data endpoints
  await page.route('**/api/admin/users', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([]),
    });
  });

  await page.route('**/api/admin/conversations', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([]),
    });
  });

  // Mock the monitor/all endpoint
  await page.route('**/api/admin/monitor/all', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(mockMonitorData),
    });
  });

  // Mock the logs endpoint (used when log level changes)
  await page.route('**/api/admin/monitor/logs*', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(mockMonitorData.logs),
    });
  });
}

test.describe('System Monitor Tab', () => {
  test.beforeEach(async ({ page }) => {
    await setupAdminMonitorMocks(page);
  });

  // Req 10.1: System tab renders alongside Users and Conversations tabs
  test('should render System tab alongside Users and Conversations tabs', async ({ page }) => {
    await page.goto('/admin');

    const tabsList = page.locator('[role="tablist"]');
    await expect(tabsList).toBeVisible();
    await expect(tabsList.locator('[role="tab"]')).toHaveCount(3);
    await expect(tabsList.getByText('Users')).toBeVisible();
    await expect(tabsList.getByText('Conversations')).toBeVisible();
    await expect(tabsList.getByText('System')).toBeVisible();
  });

  // Req 10.2: Selecting System tab triggers API calls
  test('should trigger monitor API call when System tab is selected', async ({ page }) => {
    let monitorAllCalled = false;

    // Track calls to monitor/all
    await page.route('**/api/admin/monitor/all', async (route) => {
      monitorAllCalled = true;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockMonitorData),
      });
    });

    await page.goto('/admin');

    // Click the System tab
    await page.getByRole('tab', { name: 'System' }).click();

    // Wait for the monitor content to appear
    await expect(page.getByText('Slack Bot')).toBeVisible();
    expect(monitorAllCalled).toBe(true);
  });

  // Req 10.4: Log level dropdown defaults to INFO
  test('should default log level dropdown to INFO', async ({ page }) => {
    await page.goto('/admin');
    await page.getByRole('tab', { name: 'System' }).click();

    // Wait for the log viewer to render
    await expect(page.getByText('Application Logs')).toBeVisible();

    // The Select trigger should show "INFO" as the default value
    const selectTrigger = page.locator('[role="combobox"]');
    await expect(selectTrigger).toHaveText('INFO');
  });

  // Req 10.7: Refresh button triggers data re-fetch
  test('should re-fetch data when refresh button is clicked', async ({ page }) => {
    let monitorCallCount = 0;

    await page.route('**/api/admin/monitor/all', async (route) => {
      monitorCallCount++;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockMonitorData),
      });
    });

    await page.goto('/admin');
    await page.getByRole('tab', { name: 'System' }).click();

    // Wait for initial load
    await expect(page.getByText('Slack Bot')).toBeVisible();
    const initialCount = monitorCallCount;

    // Click the Refresh button
    await page.getByRole('button', { name: 'Refresh' }).click();

    // Wait for the data to re-render (the button re-enables after fetch)
    await expect(page.getByRole('button', { name: 'Refresh' })).toBeEnabled();

    expect(monitorCallCount).toBeGreaterThan(initialCount);
  });

  // Req 10.8: Last updated timestamp is displayed
  test('should display last updated timestamp', async ({ page }) => {
    await page.goto('/admin');
    await page.getByRole('tab', { name: 'System' }).click();

    // Wait for data to load
    await expect(page.getByText('Slack Bot')).toBeVisible();

    // Check for the "Last updated:" text
    await expect(page.getByText(/Last updated:/)).toBeVisible();
  });
});
