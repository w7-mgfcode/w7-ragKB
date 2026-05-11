import { test, expect, Page } from '@playwright/test';
import { setupAuthenticatedMocks, setupAgentAPIMocks, setupDocumentMocks } from './mocks';

async function setupDocumentPageMocks(page: Page) {
  await setupAuthenticatedMocks(page);
  await setupAgentAPIMocks(page);
  await setupDocumentMocks(page);
}

test.describe('Document Search', () => {
  test.beforeEach(async ({ page }) => {
    await setupDocumentPageMocks(page);
  });

  test('should display search input with placeholder', async ({ page }) => {
    await page.goto('/documents');
    await expect(page.getByPlaceholder('Search documents...')).toBeVisible();
  });

  test('should filter tree when searching', async ({ page }) => {
    await page.goto('/documents');
    const searchInput = page.getByPlaceholder('Search documents...');
    await searchInput.fill('readme');
    // readme.md should be visible, directories without matches may hide
    await expect(page.getByText('readme.md')).toBeVisible();
  });

  test('should show no results when query matches nothing', async ({ page }) => {
    await page.goto('/documents');
    const searchInput = page.getByPlaceholder('Search documents...');
    await searchInput.fill('xyznonexistent');
    await expect(page.getByText('No documents match your search')).toBeVisible();
  });

  test('should clear search and restore full tree', async ({ page }) => {
    await page.goto('/documents');
    const searchInput = page.getByPlaceholder('Search documents...');
    await searchInput.fill('readme');
    // Clear via Escape or clear button
    await page.getByLabel('Clear search').click();
    // Full tree restored
    await expect(page.getByText('security')).toBeVisible();
    await expect(page.getByText('operations')).toBeVisible();
    await expect(page.getByText('readme.md')).toBeVisible();
  });
});
