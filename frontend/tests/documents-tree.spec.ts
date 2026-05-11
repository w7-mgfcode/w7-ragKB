import { test, expect, Page } from '@playwright/test';
import { setupAuthenticatedMocks, setupAgentAPIMocks, setupDocumentMocks } from './mocks';

async function setupDocumentPageMocks(page: Page) {
  await setupAuthenticatedMocks(page);
  await setupAgentAPIMocks(page);
  await setupDocumentMocks(page);
}

test.describe('Document Tree Display', () => {
  test.beforeEach(async ({ page }) => {
    await setupDocumentPageMocks(page);
  });

  test('should display document tree heading and stats panel', async ({ page }) => {
    await page.goto('/documents');
    await expect(page.getByText('Documents').first()).toBeVisible();
    await expect(page.getByText('Spaces/Categories')).toBeVisible();
    await expect(page.getByText('Pages/Documents')).toBeVisible();
  });

  test('should show document tree with directories', async ({ page }) => {
    await page.goto('/documents');
    await expect(page.getByText('security')).toBeVisible();
    await expect(page.getByText('operations')).toBeVisible();
    await expect(page.getByText('readme.md')).toBeVisible();
  });

  test('should expand directory on click', async ({ page }) => {
    await page.goto('/documents');
    await page.getByText('security').click();
    await expect(page.getByText('auth-guide.md')).toBeVisible();
    await expect(page.getByText('rbac.md')).toBeVisible();
  });

  test('should collapse directory on second click', async ({ page }) => {
    await page.goto('/documents');
    await page.getByText('security', { exact: true }).click();
    await expect(page.getByText('auth-guide.md')).toBeVisible();
    await page.getByText('security', { exact: true }).click();
    await expect(page.getByText('auth-guide.md')).not.toBeVisible();
  });

  test('should display stats matching mock data', async ({ page }) => {
    await page.goto('/documents');
    // 2 directories, 4 documents, 1,130 words
    await expect(page.getByText('2').first()).toBeVisible();
    await expect(page.getByText('4').first()).toBeVisible();
    await expect(page.getByText('1,130')).toBeVisible();
  });
});
