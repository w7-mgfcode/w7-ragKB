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

test.describe('Gateway Sessions Tab', () => {
  test.beforeEach(async ({ page }) => {
    await setupAdminGatewayMocks(page);
  });

  test('should display sessions in table', async ({ page }) => {
    await page.goto('/admin');

    // Navigate to Gateway tab, then Sessions sub-tab
    await page.getByRole('tab', { name: 'Gateway' }).click();
    await page.getByRole('tab', { name: 'Sessions' }).click();

    // Verify session data is visible
    await expect(page.getByText('sess-001')).toBeVisible();
    await expect(page.getByText('slack-main')).toBeVisible();
    await expect(page.getByText('user-1')).toBeVisible();
  });

  test('should show session count in footer', async ({ page }) => {
    await page.goto('/admin');
    await page.getByRole('tab', { name: 'Gateway' }).click();
    await page.getByRole('tab', { name: 'Sessions' }).click();

    await expect(page.getByText('1 session(s) total')).toBeVisible();
  });

  test('should have a search input for filtering sessions', async ({ page }) => {
    await page.goto('/admin');
    await page.getByRole('tab', { name: 'Gateway' }).click();
    await page.getByRole('tab', { name: 'Sessions' }).click();

    const searchInput = page.getByPlaceholder(/Search by session ID/i);
    await expect(searchInput).toBeVisible();
  });

  test('should show message count for session', async ({ page }) => {
    await page.goto('/admin');
    await page.getByRole('tab', { name: 'Gateway' }).click();
    await page.getByRole('tab', { name: 'Sessions' }).click();

    // The mock session has message_count: 25
    await expect(page.getByText('25')).toBeVisible();
  });
});
