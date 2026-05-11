import { test, expect, Page } from '@playwright/test';
import { setupAuthenticatedMocks, setupAgentAPIMocks, setupGatewayMocks } from './mocks';

// ---------------------------------------------------------------------------
// Shared admin setup — authenticates user, enables gateway mocks, makes admin
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

  // Override auth to make the user an admin
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

  // Mock admin data endpoints (used by other admin tabs)
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

test.describe('Gateway Channels Tab', () => {
  test.beforeEach(async ({ page }) => {
    await setupAdminGatewayMocks(page);
  });

  test('should display the Gateway tab in admin dashboard', async ({ page }) => {
    await page.goto('/admin');

    const tabsList = page.locator('[role="tablist"]').first();
    await expect(tabsList).toBeVisible();
    await expect(tabsList.getByText('Gateway')).toBeVisible();
  });

  test('should display channels in table', async ({ page }) => {
    await page.goto('/admin');

    // Navigate to Gateway tab
    await page.getByRole('tab', { name: 'Gateway' }).click();

    // Navigate to Channels sub-tab within Gateway
    await page.getByRole('tab', { name: 'Channels' }).click();

    // Verify channel data is visible
    await expect(page.getByText('slack-main')).toBeVisible();
    await expect(page.getByText('telegram-bot')).toBeVisible();
  });

  test('should show channel type labels', async ({ page }) => {
    await page.goto('/admin');
    await page.getByRole('tab', { name: 'Gateway' }).click();
    await page.getByRole('tab', { name: 'Channels' }).click();

    // Verify channel types are displayed
    await expect(page.getByText('slack', { exact: false })).toBeVisible();
    await expect(page.getByText('telegram', { exact: false })).toBeVisible();
  });

  test('should show channel count in footer', async ({ page }) => {
    await page.goto('/admin');
    await page.getByRole('tab', { name: 'Gateway' }).click();
    await page.getByRole('tab', { name: 'Channels' }).click();

    // Verify total count
    await expect(page.getByText('2 channel(s) total')).toBeVisible();
  });

  test('should open add channel dialog', async ({ page }) => {
    await page.goto('/admin');
    await page.getByRole('tab', { name: 'Gateway' }).click();
    await page.getByRole('tab', { name: 'Channels' }).click();

    await page.getByRole('button', { name: /Add Channel/i }).click();

    // Dialog should appear
    await expect(page.getByText(/Create New Channel|Add Channel|Channel ID/i)).toBeVisible();
  });

  test('should have a search input for filtering channels', async ({ page }) => {
    await page.goto('/admin');
    await page.getByRole('tab', { name: 'Gateway' }).click();
    await page.getByRole('tab', { name: 'Channels' }).click();

    const searchInput = page.getByPlaceholder(/Search by channel ID/i);
    await expect(searchInput).toBeVisible();
  });
});
