import { test, expect, Page } from '@playwright/test';
import { setupAuthenticatedMocks, setupAgentAPIMocks, setupDocumentMocks } from './mocks';

async function setupDocumentPageMocks(page: Page) {
  await setupAuthenticatedMocks(page);
  await setupAgentAPIMocks(page);
  await setupDocumentMocks(page);
}

test.describe('Document Bulk Operations', () => {
  test.beforeEach(async ({ page }) => {
    await setupDocumentPageMocks(page);
  });

  test('should show bulk actions toolbar when documents are selected', async ({ page }) => {
    await page.goto('/documents');
    // Expand security directory to see checkboxes
    await page.getByText('security').click();
    // Click checkbox for auth-guide.md
    const authItem = page.getByText('auth-guide.md').locator('..');
    await authItem.locator('button[role="checkbox"]').click();
    // Toolbar should appear
    await expect(page.getByText('1 selected')).toBeVisible();
    await expect(page.getByRole('button', { name: /Delete/i })).toBeVisible();
    await expect(page.getByRole('button', { name: /Move/i })).toBeVisible();
  });

  test('should show Clear button in toolbar when documents are selected', async ({ page }) => {
    await page.goto('/documents');
    await page.getByText('security').click();
    const authItem = page.getByText('auth-guide.md').locator('..');
    await authItem.locator('button[role="checkbox"]').click();
    await expect(page.getByText('1 selected')).toBeVisible();
    // Clear button should be visible in toolbar
    await expect(page.getByRole('toolbar').getByRole('button', { name: /Clear/i })).toBeVisible();
  });

  test('should open delete confirmation for bulk delete', async ({ page }) => {
    await page.goto('/documents');
    await page.getByText('security').click();
    const authItem = page.getByText('auth-guide.md').locator('..');
    await authItem.locator('button[role="checkbox"]').click();
    // Click Delete in toolbar
    await page.getByRole('toolbar').getByRole('button', { name: /Delete/i }).click();
    // Confirmation dialog should appear
    await expect(page.getByText('Delete 1 documents?')).toBeVisible();
  });
});
