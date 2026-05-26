import { test, expect, type Page } from '@playwright/test';

// Helper: wait for WebSocket "Connected" status
async function waitForConnected(page: Page) {
  await expect(page.locator('.chat-disclaimer')).toContainText('Connected', {
    timeout: 15_000,
  });
}

// ---------------------------------------------------------------------------
// 1. Page loads & split layout
// ---------------------------------------------------------------------------
test.describe('Page load', () => {
  test('renders split layout with chat panel and dashboard', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('.chat-panel')).toBeVisible();
    await expect(page.locator('.viz-panel')).toBeVisible();
    await expect(page.locator('.welcome-title')).toContainText('Shipment Coordinator');
    await expect(page.locator('.welcome-hint')).toContainText('deliveries');
  });

  test('shows example question buttons', async ({ page }) => {
    await page.goto('/');
    const buttons = page.locator('.example-button');
    await expect(buttons).toHaveCount(3);
    await expect(buttons.nth(0)).toContainText('packages');
    await expect(buttons.nth(1)).toContainText('deliveries');
    await expect(buttons.nth(2)).toContainText('hub');
  });

  test('dashboard shows empty state initially', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('.dashboard-empty')).toBeVisible();
    await expect(page.locator('.dashboard-empty h2')).toContainText('Shipment Dashboard');
  });
});

// ---------------------------------------------------------------------------
// 2. WebSocket connection
// ---------------------------------------------------------------------------
test.describe('WebSocket connection', () => {
  test('shows Connected status', async ({ page }) => {
    await page.goto('/');
    await waitForConnected(page);
  });
});

// ---------------------------------------------------------------------------
// 3. Send a message
// ---------------------------------------------------------------------------
test.describe('Send a message', () => {
  test('typing and pressing Enter sends the message', async ({ page }) => {
    await page.goto('/');
    await waitForConnected(page);

    const input = page.locator('.chat-input');
    await input.fill('Hello from Playwright');
    await input.press('Enter');

    const userMsg = page.locator('.chat-message.user .message-content');
    await expect(userMsg.first()).toContainText('Hello from Playwright');
  });

  test('clicking send button sends the message', async ({ page }) => {
    await page.goto('/');
    await waitForConnected(page);

    const input = page.locator('.chat-input');
    await input.fill('Send button test');
    await page.locator('.send-button').click();

    const userMsg = page.locator('.chat-message.user .message-content');
    await expect(userMsg.first()).toContainText('Send button test');
  });
});

// ---------------------------------------------------------------------------
// 4. Thinking indicator
// ---------------------------------------------------------------------------
test.describe('Thinking indicator', () => {
  test('shows thinking indicator after sending a message', async ({ page }) => {
    await page.goto('/');
    await waitForConnected(page);

    const input = page.locator('.chat-input');
    await input.fill('How many packages are in the system?');
    await input.press('Enter');

    await expect(page.locator('.thinking-text')).toBeVisible({ timeout: 10_000 });
  });
});

// ---------------------------------------------------------------------------
// 5. Receive response with dashboard data
// ---------------------------------------------------------------------------
test.describe('Receive response', () => {
  test('assistant responds and dashboard updates', async ({ page }) => {
    await page.goto('/');
    await waitForConnected(page);

    const input = page.locator('.chat-input');
    await input.fill('How many packages are in the system?');
    await input.press('Enter');

    // Wait for assistant response — real agent may take 15-30s
    const assistantMsg = page.locator('.chat-message.assistant .message-content');
    await expect(assistantMsg.first()).toBeVisible({ timeout: 45_000 });
    await expect(assistantMsg.first()).not.toBeEmpty();

    // Dashboard empty state should be gone (either data or query bar shown)
    await expect(page.locator('.dashboard-empty')).not.toBeVisible({ timeout: 5_000 });
  });
});

// ---------------------------------------------------------------------------
// 6. Example question buttons
// ---------------------------------------------------------------------------
test.describe('Example question buttons', () => {
  test('clicking an example question sends it', async ({ page }) => {
    await page.goto('/');
    await waitForConnected(page);

    const firstExample = page.locator('.example-button').first();
    const questionText = await firstExample.textContent();
    await firstExample.click();

    await expect(page.locator('.chat-welcome')).not.toBeVisible({ timeout: 10_000 });

    const userMsg = page.locator('.chat-message.user .message-content');
    await expect(userMsg.first()).toContainText(questionText!.trim());
  });
});

// ---------------------------------------------------------------------------
// 7. New conversation
// ---------------------------------------------------------------------------
test.describe('New conversation', () => {
  test('clears the chat and resets dashboard', async ({ page }) => {
    await page.goto('/');
    await waitForConnected(page);

    const input = page.locator('.chat-input');
    await input.fill('Test message for clearing');
    await input.press('Enter');
    await expect(page.locator('.chat-message.user')).toHaveCount(1);

    await page.locator('button[title="New conversation"]').click();

    // Welcome screen should reappear
    await expect(page.locator('.chat-welcome')).toBeVisible({ timeout: 5_000 });
    // Dashboard should return to empty state
    await expect(page.locator('.dashboard-empty')).toBeVisible({ timeout: 5_000 });
  });
});
