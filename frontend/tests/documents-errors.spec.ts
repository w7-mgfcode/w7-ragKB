import { test, expect, Page } from '@playwright/test';
import { setupAuthenticatedMocks, setupAgentAPIMocks } from './mocks';

async function setupDocumentErrorMocks(page: Page) {
  await setupAuthenticatedMocks(page);
  await setupAgentAPIMocks(page);

  // Tree returns 500
  await page.route('**/api/documents/tree', async (route) => {
    await route.fulfill({
      status: 500,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'Internal Server Error' }),
    });
  });

  // Stats returns 500
  await page.route('**/api/documents/stats', async (route) => {
    await route.fulfill({
      status: 500,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'Internal Server Error' }),
    });
  });
}

test.describe('Document Error Handling', () => {
  test('should show empty tree on network error', async ({ page }) => {
    await setupDocumentErrorMocks(page);
    await page.goto('/documents');
    // Tree should show empty state or error
    await expect(page.getByText('No documents found')).toBeVisible();
  });

  test('should redirect to login on 401', async ({ page }) => {
    // Override auth refresh to fail
    await page.route('**/api/auth/refresh', async (route) => {
      await route.fulfill({
        status: 401,
        contentType: 'application/json',
        body: '{"detail":"Invalid or expired refresh token"}',
      });
    });
    await page.route('**/api/auth/me', async (route) => {
      await route.fulfill({
        status: 401,
        contentType: 'application/json',
        body: '{"detail":"Not authenticated"}',
      });
    });
    await page.goto('/documents');
    // Should redirect to login page
    await expect(page).toHaveURL(/\/login/);
  });

  test('should show Documents heading even with API errors', async ({ page }) => {
    await setupDocumentErrorMocks(page);
    await page.goto('/documents');
    await expect(page.getByText('Documents').first()).toBeVisible();
  });
});
