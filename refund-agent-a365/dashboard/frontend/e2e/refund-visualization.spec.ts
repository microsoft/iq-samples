import { test, expect, type Page } from '@playwright/test';

// ---------------------------------------------------------------------------
// Refund visualization tests (mocked WebSocket — no backend needed)
// ---------------------------------------------------------------------------

const REFUND_RESPONSE = {
  type: 'chat_message',
  role: 'assistant',
  text: 'Package PKG-5003 has been stuck at HUB-DEN for 5 days. I recommend a full refund.',
};

const REFUND_SHIPMENT_DATA = {
  type: 'shipment_data',
  payload: {
    tables: [],
    entities: [
      { id: 'PKG-5003', type: 'package', label: 'PKG-5003', color: '#4FC3F7', shape: 'box' },
      { id: 'HUB-SEA', type: 'hub', label: 'HUB-SEA', color: '#81C784', shape: 'hexagon' },
      { id: 'HUB-DEN', type: 'hub', label: 'HUB-DEN', color: '#81C784', shape: 'hexagon' },
      { id: 'HUB-CHI', type: 'hub', label: 'HUB-CHI', color: '#81C784', shape: 'hexagon' },
    ],
    entity_counts: { package: 1, hub: 3 },
    focus_query: 'Check refund for PKG-5003',
    narrative: 'Package PKG-5003 has been stuck at HUB-DEN for 5 days.',
    refund_recommended: true,
    package_route: [
      { location: 'Origin', type: 'origin', status: 'completed' },
      { location: 'HUB-SEA', type: 'hub', status: 'completed' },
      { location: 'HUB-DEN', type: 'hub', status: 'stuck' },
      { location: 'HUB-CHI', type: 'hub', status: 'upcoming' },
      { location: 'Destination', type: 'destination', status: 'upcoming' },
    ],
    stuck_at: 'HUB-DEN',
    package_id: 'PKG-5003',
  },
};

const NON_REFUND_SHIPMENT_DATA = {
  type: 'shipment_data',
  payload: {
    tables: [],
    entities: [
      { id: 'PKG-5003', type: 'package', label: 'PKG-5003', color: '#4FC3F7', shape: 'box' },
    ],
    entity_counts: { package: 1 },
    focus_query: 'How many packages?',
    narrative: 'There are 10 packages.',
    refund_recommended: false,
  },
};

/**
 * Install a fake WebSocket via addInitScript so the page never needs
 * a real backend.  The mock replies with the given scenario data.
 */
async function installMockWs(page: Page, refundScenario: boolean) {
  const chatResponse = refundScenario
    ? REFUND_RESPONSE
    : { type: 'chat_message', role: 'assistant', text: 'There are 10 packages currently in the system.' };
  const shipmentData = refundScenario ? REFUND_SHIPMENT_DATA : NON_REFUND_SHIPMENT_DATA;

  await page.addInitScript(
    ({ chatResp, shipData }) => {
      /* ---------- minimal fake WebSocket ---------- */
      const OPEN = 1;
      const CLOSED = 3;
      (window as any).__MOCK_WS_INSTANCES = [];

      class FakeWebSocket {
        static CONNECTING = 0;
        static OPEN = 1;
        static CLOSING = 2;
        static CLOSED = 3;
        CONNECTING = 0;
        OPEN = 1;
        CLOSING = 2;
        CLOSED = 3;

        url: string;
        readyState = OPEN;
        binaryType = 'blob';
        bufferedAmount = 0;
        extensions = '';
        protocol = '';
        onopen: ((ev: Event) => void) | null = null;
        onclose: ((ev: CloseEvent) => void) | null = null;
        onerror: ((ev: Event) => void) | null = null;
        onmessage: ((ev: MessageEvent) => void) | null = null;

        constructor(url: string) {
          this.url = url;
          (window as any).__MOCK_WS_INSTANCES.push(this);
          // Fire onopen on next tick so event handlers are attached first
          setTimeout(() => this.onopen?.({ type: 'open' } as unknown as Event), 30);
        }

        send(data: string) {
          let msg: Record<string, unknown>;
          try { msg = JSON.parse(data); } catch { return; }
          if (msg.type === 'chat') {
            // echo user message
            this._emit({ type: 'chat_message', role: 'user', text: msg.message });
            // thinking
            this._emit({ type: 'thinking', text: 'Thinking' });
            this._emit({ type: 'tool_calling' });
            // respond after short delay
            setTimeout(() => {
              this._emit({ type: 'tool_result', tool: 'fabric_agent', result: {} });
              this._emit(chatResp);
              this._emit(shipData);
            }, 200);
          }
        }

        close() { this.readyState = CLOSED; }
        addEventListener() {}
        removeEventListener() {}
        dispatchEvent() { return true; }

        /* helper: deliver a message to the page */
        _emit(obj: unknown) {
          const event = new MessageEvent('message', { data: JSON.stringify(obj) });
          this.onmessage?.(event);
        }
      }

      (window as any).WebSocket = FakeWebSocket as unknown as typeof WebSocket;
    },
    { chatResp: chatResponse, shipData: shipmentData },
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test.describe('Refund visualization', () => {
  test('shows package path and Grant Refund button when refund is recommended', async ({ page }) => {
    await installMockWs(page, true);
    await page.goto('/');

    // Wait for mock WebSocket to "connect"
    await expect(page.locator('.chat-disclaimer')).toContainText('Connected', { timeout: 10_000 });

    // Send a message
    const input = page.locator('.chat-input');
    await input.fill('Is PKG-5003 eligible for a refund?');
    await input.press('Enter');

    // Wait for the package path visualization
    const pathViz = page.locator('[data-testid="package-path-visualization"]');
    await expect(pathViz).toBeVisible({ timeout: 15_000 });

    // 5 nodes: Origin, HUB-SEA, HUB-DEN(stuck), HUB-CHI, Destination
    await expect(pathViz.locator('.path-node')).toHaveCount(5);
    await expect(pathViz.locator('.path-node.completed')).toHaveCount(2);
    await expect(pathViz.locator('.path-node.stuck')).toBeVisible();
    await expect(pathViz.locator('.path-node.stuck .path-node-label')).toContainText('HUB-DEN');
    await expect(pathViz.locator('.path-node.stuck .path-node-status')).toContainText('Delayed');
    await expect(pathViz.locator('.path-node.upcoming')).toHaveCount(2);
    await expect(pathViz.locator('.path-connector')).toHaveCount(4);

    // Grant Refund button
    const refundBtn = page.locator('[data-testid="grant-refund-button"]');
    await expect(refundBtn).toBeVisible();
    await expect(refundBtn).toContainText('Grant Refund');

    // Click → changes to granted
    await refundBtn.click();
    await expect(refundBtn).toContainText('Refund Granted');
    await expect(refundBtn).toHaveClass(/granted/);

    // Screenshot
    await page.screenshot({ path: 'e2e/screenshots/refund-visualization.png', fullPage: true });
  });

  test('does NOT show refund visualization for non-refund responses', async ({ page }) => {
    await installMockWs(page, false);
    await page.goto('/');
    await expect(page.locator('.chat-disclaimer')).toContainText('Connected', { timeout: 10_000 });

    const input = page.locator('.chat-input');
    await input.fill('How many packages are there?');
    await input.press('Enter');

    // Wait for assistant response
    await expect(page.locator('.chat-message.assistant')).toBeVisible({ timeout: 10_000 });

    // NO refund visualization
    await expect(page.locator('[data-testid="package-path-visualization"]')).not.toBeVisible();
    await expect(page.locator('[data-testid="grant-refund-button"]')).not.toBeVisible();
  });

  test('package path visualization shows correct title with package ID', async ({ page }) => {
    await installMockWs(page, true);
    await page.goto('/');
    await expect(page.locator('.chat-disclaimer')).toContainText('Connected', { timeout: 10_000 });

    const input = page.locator('.chat-input');
    await input.fill('Refund check');
    await input.press('Enter');

    const pathViz = page.locator('[data-testid="package-path-visualization"]');
    await expect(pathViz).toBeVisible({ timeout: 15_000 });
    await expect(pathViz.locator('.section-title')).toContainText('PKG-5003');
  });
});
