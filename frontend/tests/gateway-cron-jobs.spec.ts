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

test.describe('Gateway Cron Jobs Tab', () => {
  test.beforeEach(async ({ page }) => {
    await setupAdminGatewayMocks(page);
  });

  test('should display cron jobs in table', async ({ page }) => {
    await page.goto('/admin');

    // Navigate to Gateway tab, then Cron Jobs sub-tab
    await page.getByRole('tab', { name: 'Gateway' }).click();
    await page.getByRole('tab', { name: 'Cron Jobs' }).click();

    // Verify cron job data is visible
    await expect(page.getByText('daily-summary')).toBeVisible();
  });

  test('should show cron schedule expression', async ({ page }) => {
    await page.goto('/admin');
    await page.getByRole('tab', { name: 'Gateway' }).click();
    await page.getByRole('tab', { name: 'Cron Jobs' }).click();

    // The mock cron job has schedule '0 9 * * *'
    await expect(page.getByText('0 9 * * *')).toBeVisible();
  });

  test('should show cron job target session', async ({ page }) => {
    await page.goto('/admin');
    await page.getByRole('tab', { name: 'Gateway' }).click();
    await page.getByRole('tab', { name: 'Cron Jobs' }).click();

    await expect(page.getByText('sess-001')).toBeVisible();
  });

  test('should show cron job count in footer', async ({ page }) => {
    await page.goto('/admin');
    await page.getByRole('tab', { name: 'Gateway' }).click();
    await page.getByRole('tab', { name: 'Cron Jobs' }).click();

    await expect(page.getByText('1 cron job(s) total')).toBeVisible();
  });

  test('should open create cron job dialog', async ({ page }) => {
    await page.goto('/admin');
    await page.getByRole('tab', { name: 'Gateway' }).click();
    await page.getByRole('tab', { name: 'Cron Jobs' }).click();

    await page.getByRole('button', { name: /Create Cron Job/i }).click();

    // Dialog should appear with form elements
    await expect(page.getByText(/Create Cron Job|New Cron Job|Schedule/i)).toBeVisible();
  });

  test('should have a search input for filtering cron jobs', async ({ page }) => {
    await page.goto('/admin');
    await page.getByRole('tab', { name: 'Gateway' }).click();
    await page.getByRole('tab', { name: 'Cron Jobs' }).click();

    const searchInput = page.getByPlaceholder(/Search by cron job ID/i);
    await expect(searchInput).toBeVisible();
  });
});
