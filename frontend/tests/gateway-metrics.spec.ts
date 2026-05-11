import { test, expect, Page } from '@playwright/test';
import { setupAuthenticatedMocks, setupAgentAPIMocks, setupGatewayMocks } from './mocks';

// ---------------------------------------------------------------------------
// Shared admin setup
// ---------------------------------------------------------------------------

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

async function setupAdminGatewayMocks(page: Page) {
  await setupAuthenticatedMocks(page);
  await setupAgentAPIMocks(page);
  await setupGatewayMocks(page);

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
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test.describe('Gateway Metrics Tab', () => {
  test.beforeEach(async ({ page }) => {
    await setupAdminGatewayMocks(page);
  });

  test('should display metric summary cards when Gateway tab is selected', async ({ page }) => {
    await page.goto('/admin');

    // Click the Gateway tab — metrics are shown at the top by default
    await page.getByRole('tab', { name: 'Gateway' }).click();

    // The GatewayManagement component shows summary cards at the top
    await expect(page.getByText('Active Sessions')).toBeVisible();
    await expect(page.getByText('Queue Depth')).toBeVisible();
    await expect(page.getByText('Total Messages')).toBeVisible();
    await expect(page.getByText('Channel Health')).toBeVisible();
  });

  test('should show active sessions count from mock data', async ({ page }) => {
    await page.goto('/admin');
    await page.getByRole('tab', { name: 'Gateway' }).click();

    // The mock /api/admin/monitor/gateway returns active_sessions: 5
    await expect(page.getByText('5')).toBeVisible();
  });

  test('should display the Metrics sub-tab as default', async ({ page }) => {
    await page.goto('/admin');
    await page.getByRole('tab', { name: 'Gateway' }).click();

    // The Metrics sub-tab should be active by default within GatewayManagement
    const metricsTab = page.getByRole('tab', { name: 'Metrics' });
    await expect(metricsTab).toBeVisible();
  });

  test('should display metrics dashboard with Overview sub-tab', async ({ page }) => {
    await page.goto('/admin');
    await page.getByRole('tab', { name: 'Gateway' }).click();
    await page.getByRole('tab', { name: 'Metrics' }).click();

    // The GatewayMetrics component has its own sub-tabs: Overview, Channels, Performance
    await expect(page.getByText('Gateway Metrics Dashboard')).toBeVisible();
    await expect(page.getByRole('tab', { name: 'Overview' })).toBeVisible();
    await expect(page.getByRole('tab', { name: 'Channels' })).toBeVisible();
    await expect(page.getByRole('tab', { name: 'Performance' })).toBeVisible();
  });

  test('should show channel health badges in metrics overview', async ({ page }) => {
    await page.goto('/admin');
    await page.getByRole('tab', { name: 'Gateway' }).click();
    await page.getByRole('tab', { name: 'Metrics' }).click();

    // Channel health section should show channel names
    await expect(page.getByText('slack-main')).toBeVisible();
    await expect(page.getByText('telegram-bot')).toBeVisible();
  });

  test('should have auto-refresh toggle in metrics dashboard', async ({ page }) => {
    await page.goto('/admin');
    await page.getByRole('tab', { name: 'Gateway' }).click();
    await page.getByRole('tab', { name: 'Metrics' }).click();

    await expect(page.getByText('Auto-refresh')).toBeVisible();
  });

  test('should have export CSV button in metrics dashboard', async ({ page }) => {
    await page.goto('/admin');
    await page.getByRole('tab', { name: 'Gateway' }).click();
    await page.getByRole('tab', { name: 'Metrics' }).click();

    await expect(page.getByRole('button', { name: /Export CSV/i })).toBeVisible();
  });

  test('should navigate to Performance sub-tab', async ({ page }) => {
    await page.goto('/admin');
    await page.getByRole('tab', { name: 'Gateway' }).click();
    await page.getByRole('tab', { name: 'Metrics' }).click();

    // Click the Performance sub-tab inside the metrics dashboard
    await page.getByRole('tab', { name: 'Performance' }).click();

    // Performance tab shows Total Messages, Connected Channels, and Last Updated
    await expect(page.getByText('Connected Channels')).toBeVisible();
  });
});
