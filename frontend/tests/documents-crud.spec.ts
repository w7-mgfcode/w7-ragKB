import { test, expect, Page } from '@playwright/test';
import { setupAuthenticatedMocks, setupAgentAPIMocks, setupDocumentMocks } from './mocks';

async function setupDocumentPageMocks(page: Page) {
  await setupAuthenticatedMocks(page);
  await setupAgentAPIMocks(page);
  await setupDocumentMocks(page);
}

test.describe('Document CRUD Operations', () => {
  test.beforeEach(async ({ page }) => {
    await setupDocumentPageMocks(page);
  });

  test('should open create document dialog', async ({ page }) => {
    await page.goto('/documents');
    await page.getByRole('button', { name: /New Document/i }).click();
    await expect(page.getByText('Create Document')).toBeVisible();
  });

  test('should view document content when clicked', async ({ page }) => {
    await page.goto('/documents');
    await page.getByText('readme.md').click();
    // Viewer should show the document path and content
    await expect(page.getByText('readme.md').first()).toBeVisible();
    await expect(page.getByText('100 words')).toBeVisible();
  });

  test('should switch to editor when Edit clicked', async ({ page }) => {
    await page.goto('/documents');
    await page.getByText('readme.md').click();
    await page.getByRole('button', { name: /Edit/i }).click();
    // Editor textarea should be visible
    await expect(page.getByPlaceholder('Write your markdown content here...')).toBeVisible();
  });

  test('should show delete confirmation dialog', async ({ page }) => {
    await page.goto('/documents');
    await page.getByText('readme.md').click();
    await page.getByRole('button', { name: /Delete/i }).click();
    await expect(page.getByText('Delete document?')).toBeVisible();
  });

  test('should show New Document button', async ({ page }) => {
    await page.goto('/documents');
    await expect(page.getByRole('button', { name: /New Document/i })).toBeVisible();
  });

  test('should show Back to Chat link', async ({ page }) => {
    await page.goto('/documents');
    await expect(page.getByText('Back to Chat')).toBeVisible();
  });
});
