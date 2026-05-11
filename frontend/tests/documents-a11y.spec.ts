import { test, expect, Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { setupAuthenticatedMocks, setupAgentAPIMocks, setupDocumentMocks } from './mocks';

async function setupDocumentPageMocks(page: Page) {
  await setupAuthenticatedMocks(page);
  await setupAgentAPIMocks(page);
  await setupDocumentMocks(page);
}

/**
 * Helper: press ArrowDown N times to navigate to the Nth visible node.
 *
 * The useTreeKeyboard hook tracks focusedPath state internally. When focusedPath
 * is null (initial), the first ArrowDown always moves to index 0 (first node).
 *
 * We focus the first treeitem via .focus() to ensure keyboard events bubble
 * through the tree container's onKeyDown handler. This does NOT update React's
 * focusedPath — only the hook's focusNode() does that in response to key events.
 *
 * Between each key press, we wait briefly for React to process the async
 * setFocusedPath() state update so the next key press uses the updated closure.
 */
async function focusNthNode(page: Page, n: number) {
  // DOM-focus the first treeitem so keyboard events bubble to the tree container
  await page.locator('[role="treeitem"]').first().focus();
  for (let i = 0; i < n; i++) {
    await page.keyboard.press('ArrowDown');
    // Allow React to process the batched state update before the next key press
    await page.locator('[role="treeitem"][tabindex="0"]').waitFor({ state: 'attached', timeout: 2000 });
  }
}

/**
 * Helper: wait for the announcer live region to contain a specific text.
 * The announce() utility uses requestAnimationFrame, so we need to wait for it.
 * Also handles potential multiple aria-live elements from Radix UI.
 */
async function waitForAnnouncement(page: Page, text: string) {
  await page.waitForFunction(
    (expected) => {
      const elements = document.querySelectorAll('[aria-live="polite"]');
      return Array.from(elements).some((el) => el.textContent?.includes(expected));
    },
    text,
    { timeout: 5000 },
  );
}

// ---------------------------------------------------------------------------
// Accessibility Audit (F10)
// ---------------------------------------------------------------------------

test.describe('Document Browser Accessibility Audit', () => {
  test.beforeEach(async ({ page }) => {
    await setupDocumentPageMocks(page);
  });

  test('full page should pass WCAG 2.1 AA structural checks', async ({ page }) => {
    await page.goto('/documents');
    await page.waitForSelector('[role="tree"]');
    await page.waitForFunction(() => document.documentElement.classList.contains('dark'));

    const results = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .disableRules(['color-contrast'])
      .analyze();

    const violations = results.violations.map((v) => ({
      id: v.id,
      impact: v.impact,
      description: v.description,
      nodes: v.nodes.length,
      helpUrl: v.helpUrl,
    }));
    expect(violations).toEqual([]);
  });

  test('document tree region passes axe scan', async ({ page }) => {
    await page.goto('/documents');
    await page.waitForSelector('[role="tree"]');

    const results = await new AxeBuilder({ page })
      .include('[role="tree"]')
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .disableRules(['color-contrast'])
      .analyze();

    expect(results.violations).toEqual([]);
  });

  test('expanded directory passes axe scan', async ({ page }) => {
    await page.goto('/documents');
    await page.getByText('security', { exact: true }).click();
    await expect(page.getByText('auth-guide.md')).toBeVisible();

    const results = await new AxeBuilder({ page })
      .include('[role="tree"]')
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .disableRules(['color-contrast'])
      .analyze();

    expect(results.violations).toEqual([]);
  });

  test('document viewer passes axe scan', async ({ page }) => {
    await page.goto('/documents');
    await page.getByText('readme.md').click();
    await expect(page.getByText('100 words')).toBeVisible();

    const results = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .disableRules(['color-contrast'])
      .analyze();

    expect(results.violations).toEqual([]);
  });

  test('all tree items have proper ARIA roles', async ({ page }) => {
    await page.goto('/documents');
    await page.waitForSelector('[role="tree"]');
    // Expand security to get more tree items
    await page.getByText('security', { exact: true }).click();
    await expect(page.getByText('auth-guide.md')).toBeVisible();

    const allValid = await page.$$eval('[role="treeitem"]', (elements) =>
      elements.every((el) => {
        const hasLevel = el.hasAttribute('aria-level');
        const isDir = el.hasAttribute('aria-expanded');
        const isDoc = el.hasAttribute('aria-selected');
        return hasLevel && (isDir || isDoc);
      }),
    );
    expect(allValid).toBe(true);
  });

  test('skip link is present and functional', async ({ page }) => {
    await page.goto('/documents');
    const skipLink = page.locator('a[href="#document-tree"]');
    await expect(skipLink).toBeAttached();
    // Skip link should become visible on focus
    await skipLink.focus();
    await expect(skipLink).toBeVisible();
    // Target element should exist
    await expect(page.locator('#document-tree')).toBeAttached();
  });
});

// ---------------------------------------------------------------------------
// Keyboard Navigation (F21, 18.8)
//
// NOTE: The useTreeKeyboard hook manages focusedPath state internally.
// Calling .focus() from Playwright moves DOM focus but does NOT update
// the React state. We must use keyboard presses (ArrowDown from the tree
// always starts at index 0) or .click() to set the initial focus context.
// Clicking a directory toggles its expansion as a side effect.
// ---------------------------------------------------------------------------

test.describe('Document Tree Keyboard Navigation', () => {
  test.beforeEach(async ({ page }) => {
    await setupDocumentPageMocks(page);
  });

  test('ArrowDown moves focus through tree items', async ({ page }) => {
    await page.goto('/documents');
    await page.waitForSelector('[role="tree"]');

    // Tree (collapsed): security, operations, readme.md
    // First ArrowDown from tree container → focuses security (index 0)
    await focusNthNode(page, 1);
    await expect(page.locator('[data-path="security"]')).toHaveAttribute('tabindex', '0');

    // Second ArrowDown → operations (index 1)
    await page.keyboard.press('ArrowDown');
    await expect(page.locator('[data-path="operations"]')).toHaveAttribute('tabindex', '0');

    // Third ArrowDown → readme.md (index 2)
    await page.keyboard.press('ArrowDown');
    await expect(page.locator('[data-path="readme.md"]')).toHaveAttribute('tabindex', '0');
  });

  test('ArrowUp moves focus backwards', async ({ page }) => {
    await page.goto('/documents');
    await page.waitForSelector('[role="tree"]');

    // Navigate to readme.md (3rd item)
    await focusNthNode(page, 3);
    await expect(page.locator('[data-path="readme.md"]')).toHaveAttribute('tabindex', '0');

    // ArrowUp → operations
    await page.keyboard.press('ArrowUp');
    await expect(page.locator('[data-path="operations"]')).toHaveAttribute('tabindex', '0');

    // ArrowUp → security
    await page.keyboard.press('ArrowUp');
    await expect(page.locator('[data-path="security"]')).toHaveAttribute('tabindex', '0');
  });

  test('ArrowRight expands collapsed directory', async ({ page }) => {
    await page.goto('/documents');
    await page.waitForSelector('[role="tree"]');

    // Focus security (first node)
    await focusNthNode(page, 1);
    const securityItem = page.locator('[data-path="security"]');
    await expect(securityItem).toHaveAttribute('aria-expanded', 'false');

    // ArrowRight expands it
    await page.keyboard.press('ArrowRight');
    await expect(securityItem).toHaveAttribute('aria-expanded', 'true');
    await expect(page.getByText('auth-guide.md')).toBeVisible();
  });

  test('ArrowRight on expanded directory moves to first child', async ({ page }) => {
    await page.goto('/documents');
    await page.waitForSelector('[role="tree"]');

    // Focus security and expand it
    await focusNthNode(page, 1);
    await page.keyboard.press('ArrowRight'); // expand
    await expect(page.locator('[data-path="security"]')).toHaveAttribute('aria-expanded', 'true');

    // ArrowRight again moves to first child
    await page.keyboard.press('ArrowRight');
    await expect(page.locator('[data-path="security/auth-guide.md"]')).toHaveAttribute('tabindex', '0');
  });

  test('ArrowLeft collapses expanded directory', async ({ page }) => {
    await page.goto('/documents');
    await page.waitForSelector('[role="tree"]');

    // Focus and expand security
    await focusNthNode(page, 1);
    await page.keyboard.press('ArrowRight'); // expand
    await expect(page.locator('[data-path="security"]')).toHaveAttribute('aria-expanded', 'true');

    // ArrowLeft collapses it
    await page.keyboard.press('ArrowLeft');
    await expect(page.locator('[data-path="security"]')).toHaveAttribute('aria-expanded', 'false');
  });

  test('ArrowLeft on child moves focus to parent', async ({ page }) => {
    await page.goto('/documents');
    await page.waitForSelector('[role="tree"]');

    // Focus security, expand, move to first child
    await focusNthNode(page, 1);
    await page.keyboard.press('ArrowRight'); // expand
    await expect(page.locator('[data-path="security"]')).toHaveAttribute('aria-expanded', 'true');
    await page.keyboard.press('ArrowRight'); // move to auth-guide.md
    await expect(page.locator('[data-path="security/auth-guide.md"]')).toHaveAttribute('tabindex', '0');

    // ArrowLeft from child → parent
    await page.keyboard.press('ArrowLeft');
    await expect(page.locator('[data-path="security"]')).toHaveAttribute('tabindex', '0');
  });

  test('Enter toggles directory expand/collapse', async ({ page }) => {
    await page.goto('/documents');
    await page.waitForSelector('[role="tree"]');

    // Focus security
    await focusNthNode(page, 1);
    const securityItem = page.locator('[data-path="security"]');
    await expect(securityItem).toHaveAttribute('aria-expanded', 'false');

    // Enter expands
    await page.keyboard.press('Enter');
    await expect(securityItem).toHaveAttribute('aria-expanded', 'true');

    // Enter collapses
    await page.keyboard.press('Enter');
    await expect(securityItem).toHaveAttribute('aria-expanded', 'false');
  });

  test('Enter on document selects it and opens viewer', async ({ page }) => {
    await page.goto('/documents');
    await page.waitForSelector('[role="tree"]');

    // Navigate to readme.md (3rd item) and press Enter
    await focusNthNode(page, 3);
    await page.keyboard.press('Enter');

    // Document viewer should appear
    await expect(page.getByText('100 words')).toBeVisible();
  });

  test('Home moves focus to first item', async ({ page }) => {
    await page.goto('/documents');
    await page.waitForSelector('[role="tree"]');

    // Navigate to last item (readme.md)
    await focusNthNode(page, 3);
    await expect(page.locator('[data-path="readme.md"]')).toHaveAttribute('tabindex', '0');

    // Home → first item
    await page.keyboard.press('Home');
    await expect(page.locator('[data-path="security"]')).toHaveAttribute('tabindex', '0');
  });

  test('End moves focus to last item', async ({ page }) => {
    await page.goto('/documents');
    await page.waitForSelector('[role="tree"]');

    // Focus first item
    await focusNthNode(page, 1);
    await expect(page.locator('[data-path="security"]')).toHaveAttribute('tabindex', '0');

    // End → last item
    await page.keyboard.press('End');
    await expect(page.locator('[data-path="readme.md"]')).toHaveAttribute('tabindex', '0');
  });

  test('screen reader announces directory expand', async ({ page }) => {
    await page.goto('/documents');
    await page.waitForSelector('[role="tree"]');

    // Click security to expand — triggers announce()
    await page.getByText('security', { exact: true }).click();
    await expect(page.getByText('auth-guide.md')).toBeVisible();

    await waitForAnnouncement(page, 'security expanded');
  });

  test('screen reader announces directory collapse', async ({ page }) => {
    await page.goto('/documents');
    await page.waitForSelector('[role="tree"]');

    // Expand then collapse
    await page.getByText('security', { exact: true }).click();
    await expect(page.getByText('auth-guide.md')).toBeVisible();
    await page.getByText('security', { exact: true }).click();

    await waitForAnnouncement(page, 'security collapsed');
  });

  test('focused item has tabindex 0, others have -1', async ({ page }) => {
    await page.goto('/documents');
    await page.waitForSelector('[role="tree"]');

    // Navigate to focus security
    await focusNthNode(page, 1);
    await expect(page.locator('[data-path="security"]')).toHaveAttribute('tabindex', '0');
    await expect(page.locator('[data-path="operations"]')).toHaveAttribute('tabindex', '-1');
    await expect(page.locator('[data-path="readme.md"]')).toHaveAttribute('tabindex', '-1');
  });
});
