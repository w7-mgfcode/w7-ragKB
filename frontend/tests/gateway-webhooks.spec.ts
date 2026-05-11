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

test.describe('Gateway Webhooks Tab', () => {
  test.beforeEach(async ({ page }) => {
    await setupAdminGatewayMocks(page);
  });

  test('should display webhooks in table', async ({ page }) => {
    await page.goto('/admin');

    // Navigate to Gateway tab, then Webhooks sub-tab
    await page.getByRole('tab', { name: 'Gateway' }).click();
    await page.getByRole('tab', { name: 'Webhooks' }).click();

    // Verify webhook data is visible
    await expect(page.getByText('github-alerts')).toBeVisible();
  });

  test('should show webhook target session', async ({ page }) => {
    await page.goto('/admin');
    await page.getByRole('tab', { name: 'Gateway' }).click();
    await page.getByRole('tab', { name: 'Webhooks' }).click();

    // The mock webhook targets sess-001
    await expect(page.getByText('sess-001')).toBeVisible();
  });

  test('should show webhook count in footer', async ({ page }) => {
    await page.goto('/admin');
    await page.getByRole('tab', { name: 'Gateway' }).click();
    await page.getByRole('tab', { name: 'Webhooks' }).click();

    await expect(page.getByText('1 webhook(s) total')).toBeVisible();
  });

  test('should open create webhook dialog', async ({ page }) => {
    await page.goto('/admin');
    await page.getByRole('tab', { name: 'Gateway' }).click();
    await page.getByRole('tab', { name: 'Webhooks' }).click();

    await page.getByRole('button', { name: /Create Webhook/i }).click();

    // Dialog should appear with form elements
    await expect(page.getByText(/Create Webhook|New Webhook|Webhook ID/i)).toBeVisible();
  });

  test('should have a search input for filtering webhooks', async ({ page }) => {
    await page.goto('/admin');
    await page.getByRole('tab', { name: 'Gateway' }).click();
    await page.getByRole('tab', { name: 'Webhooks' }).click();

    const searchInput = page.getByPlaceholder(/Search by webhook ID/i);
    await expect(searchInput).toBeVisible();
  });
});
