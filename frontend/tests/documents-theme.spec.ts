import { test, expect, Page } from '@playwright/test';
import { setupAuthenticatedMocks, setupAgentAPIMocks, setupDocumentMocks } from './mocks';

async function setupDocumentPageMocks(page: Page) {
  await setupAuthenticatedMocks(page);
  await setupAgentAPIMocks(page);
  await setupDocumentMocks(page);
}

test.describe('Document Browser Theme', () => {
  test.beforeEach(async ({ page }) => {
    await setupDocumentPageMocks(page);
  });

  test('dark theme is applied to document page', async ({ page }) => {
    await page.goto('/documents');
    await page.waitForFunction(() => document.documentElement.classList.contains('dark'));

    const hasDarkClass = await page.evaluate(() =>
      document.documentElement.classList.contains('dark'),
    );
    expect(hasDarkClass).toBe(true);
  });

  test('dark theme persists after navigation', async ({ page }) => {
    await page.goto('/documents');
    await page.waitForFunction(() => document.documentElement.classList.contains('dark'));

    // Navigate away and back
    await page.goto('/');
    await page.goto('/documents');
    await page.waitForFunction(() => document.documentElement.classList.contains('dark'));

    const hasDarkClass = await page.evaluate(() =>
      document.documentElement.classList.contains('dark'),
    );
    expect(hasDarkClass).toBe(true);
  });

  test('background uses dark theme colors', async ({ page }) => {
    await page.goto('/documents');
    await page.waitForFunction(() => document.documentElement.classList.contains('dark'));

    const bgColor = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
    // Dark theme background should not be white (rgb(255, 255, 255))
    expect(bgColor).not.toBe('rgb(255, 255, 255)');
    // Should have some color value (not empty/transparent)
    expect(bgColor).toBeTruthy();
  });
});
