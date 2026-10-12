const assert = require('node:assert/strict');
const { createHash } = require('node:crypto');
const { chromium } = require('playwright');

const URL = process.env.DASHBOARD_URL || 'http://127.0.0.1:5173';
const WIDTHS = [375, 390, 768, 1024, 1280, 1366, 1536, 1920, 2560];
const DEFAULT_ORDER = ['working', 'apps', 'agents', 'devices', 'activity', 'realm', 'health'];
const LAYOUT_KEY = 'synapse.home.dashboard.v2';
const checks = [];
const errors = [];

async function settle(page) {
  await page.evaluate(() => new Promise(resolve => {
    requestAnimationFrame(() => requestAnimationFrame(resolve));
  }));
}

async function panelPositions(page) {
  return page.locator('.syn-dash-panel').evaluateAll(panels => panels.map(panel => {
    const bounds = panel.getBoundingClientRect();
    const grid = panel.parentElement.getBoundingClientRect();
    return {
      id: panel.dataset.panelId,
      x: Math.round((bounds.x - grid.x) * 10) / 10,
      y: Math.round((bounds.y - grid.y) * 10) / 10,
      width: bounds.width,
      height: bounds.height,
    };
  }));
}

async function assertOrder(page, expected, label) {
  await page.waitForFunction(order => {
    const actual = [...document.querySelectorAll('.syn-dash-panel')].map(panel => panel.dataset.panelId);
    return JSON.stringify(actual) === JSON.stringify(order);
  }, expected);
  await settle(page);
  const positions = await panelPositions(page);
  assert.deepEqual(positions.map(panel => panel.id), expected, label + ': DOM order');
  assert(positions.every(panel => panel.width > 0 && panel.height > 0), label + ': panels have visible bounds');
  const visualOrder = [...positions].sort((a, b) => Math.abs(a.y - b.y) > 1 ? a.y - b.y : a.x - b.x);
  assert.deepEqual(visualOrder.map(panel => panel.id), expected, label + ': rendered grid order');
  checks.push({ check: label, order: expected, positions: positions.map(({ id, x, y }) => ({ id, x, y })) });
  return positions;
}

function assertMoved(before, after, id, label) {
  const source = before.find(panel => panel.id === id);
  const destination = after.find(panel => panel.id === id);
  assert(source.x !== destination.x || source.y !== destination.y, label + ': ' + id + ' must actually move');
}

async function assertSaved(page, order, hidden = []) {
  await page.waitForFunction(({ key, order, hidden }) => {
    const stored = JSON.parse(localStorage.getItem(key) || 'null');
    return stored && JSON.stringify(stored.order) === JSON.stringify(order)
      && JSON.stringify(stored.hidden) === JSON.stringify(hidden);
  }, { key: LAYOUT_KEY, order, hidden });
}

// Deterministic drag: dispatches the same dragstart/dragover/drop/dragend sequence a browser would,
// with one shared DataTransfer, so it does not depend on OS-level pointer timing.
async function syntheticDragPanel(page, grip, target) {
  const targetId = await target.getAttribute('data-panel-id');
  await grip.evaluate((handle, id) => {
    const dataTransfer = new DataTransfer();
    const fire = (el, type) => el.dispatchEvent(new DragEvent(type, { bubbles: true, cancelable: true, dataTransfer }));
    const panel = document.querySelector(`[data-panel-id="${id}"]`);
    fire(handle, 'dragstart');
    return new Promise(resolve => requestAnimationFrame(() => {
      fire(panel, 'dragover');
      requestAnimationFrame(() => {
        fire(panel, 'drop');
        fire(handle, 'dragend');
        resolve();
      });
    }));
  }, targetId);
  await page.waitForFunction(() => !document.querySelector('[data-dragging="true"], [data-drop-target="true"]'));
}

// Native drag with retries: a failed attempt (no dragstart/dragover delivered) is released and retried.
async function dragPanel(page, grip, target, { native = false } = {}) {
  if (!native) return syntheticDragPanel(page, grip, target);
  let lastError;
  for (let attempt = 1; attempt <= 3; attempt++) {
    try {
      return await nativeDragPanel(page, grip, target);
    } catch (error) {
      lastError = error;
      await page.mouse.up().catch(() => {});
      await page.keyboard.press('Escape').catch(() => {});
      await settle(page);
    }
  }
  throw lastError;
}

async function nativeDragPanel(page, grip, target) {
  await grip.hover();
  const sourceId = await grip.evaluate(handle => handle.closest('[data-panel-id]').dataset.panelId);
  const targetId = await target.getAttribute('data-panel-id');
  const start = await grip.boundingBox();
  assert(start, 'drag handle has visible bounds');
  await page.mouse.down();
  try {
    // Establish a native drag before scrolling the destination into view.
    // dragTo can scroll the source away after mousedown, preventing dragstart.
    await page.mouse.move(start.x + start.width / 2 + 10, start.y + start.height / 2, { steps: 5 });
    await page.waitForFunction(id =>
      document.querySelector(`[data-panel-id="${id}"]`)?.dataset.dragging === 'true', sourceId, { timeout: 5000 });

    const header = target.locator('header');
    await header.scrollIntoViewIfNeeded();
    const bounds = await header.boundingBox();
    assert(bounds, 'drop header has visible bounds');
    const point = { x: bounds.x + bounds.width / 2, y: bounds.y + bounds.height / 2 };
    assert.equal(await page.evaluate(({ x, y }) =>
      document.elementFromPoint(x, y)?.closest('[data-panel-id]')?.dataset.panelId, point),
    targetId, 'drop point hits the intended visible panel');
    await page.mouse.move(point.x, point.y, { steps: 10 });
    // A second movement delivers dragover even when the first only enters it.
    await page.mouse.move(point.x + 1, point.y);
    if (sourceId !== targetId) {
      await page.waitForFunction(id =>
        document.querySelector(`[data-panel-id="${id}"]`)?.dataset.dropTarget === 'true', targetId, { timeout: 5000 });
    }
  } finally {
    await page.mouse.up();
  }
  await page.waitForFunction(() => !document.querySelector('[data-dragging="true"], [data-drop-target="true"]'));
}

async function verifyReordering(page) {
  await page.getByRole('button', { name: 'Customize dashboard', exact: true }).click();
  await page.getByRole('button', { name: 'Reset', exact: true }).click();
  const initial = await assertOrder(page, DEFAULT_ORDER, 'initial panel positions');
  const healthGrip = page.getByRole('button', { name: 'Reorder System Health', exact: true });
  const working = page.locator('[data-panel-id="working"]');
  const realm = page.locator('[data-panel-id="realm"]');
  assert.equal(await healthGrip.getAttribute('draggable'), 'true', 'reorder grip is draggable');
  assert.equal(await working.evaluate(panel => panel.draggable), false, 'panel controls are not drag handles');

  await working.evaluate(panel => {
    const dataTransfer = new DataTransfer();
    dataTransfer.setData('text/plain', 'health');
    panel.dispatchEvent(new DragEvent('drop', { bubbles: true, cancelable: true, dataTransfer }));
  });
  await assertOrder(page, DEFAULT_ORDER, 'unrelated external drop leaves positions unchanged');
  await dragPanel(page, healthGrip, page.locator('[data-panel-id="health"]'));
  await assertOrder(page, DEFAULT_ORDER, 'dropping a panel on itself leaves positions unchanged');

  // Native smoke test: the one real pointer-driven drag.
  await dragPanel(page, healthGrip, working, { native: true });
  const firstOrder = ['health', ...DEFAULT_ORDER.filter(id => id !== 'health')];
  const backward = await assertOrder(page, firstOrder, 'drag last panel to first');
  assertMoved(initial, backward, 'health', 'backward drag');

  await dragPanel(page, healthGrip, working);
  const adjacentOrder = ['working', 'health', ...DEFAULT_ORDER.filter(id => !['working', 'health'].includes(id))];
  const adjacent = await assertOrder(page, adjacentOrder, 'drag forward one position');
  assertMoved(backward, adjacent, 'health', 'adjacent forward drag');

  await dragPanel(page, healthGrip, realm);
  const forward = await assertOrder(page, DEFAULT_ORDER, 'drag first row to last position');
  assertMoved(adjacent, forward, 'health', 'forward drag');

  const keyboardMoves = [
    ['Home', firstOrder],
    ['ArrowUp', firstOrder],
    ['ArrowDown', adjacentOrder],
    ['ArrowUp', firstOrder],
    ['End', DEFAULT_ORDER],
    ['ArrowDown', DEFAULT_ORDER],
  ];
  await healthGrip.focus();
  for (const [key, expected] of keyboardMoves) {
    await page.keyboard.press(key);
    await assertOrder(page, expected, 'keyboard ' + key);
    assert(await healthGrip.evaluate(grip => document.activeElement === grip), key + ': focus stays on moved grip');
  }

  await page.getByRole('checkbox', { name: 'Recent Activity', exact: true }).uncheck();
  await healthGrip.focus();
  await page.keyboard.press('Home');
  const visibleOrder = firstOrder.filter(id => id !== 'activity');
  await assertOrder(page, visibleOrder, 'keyboard reorder with hidden panel');
  await assertSaved(page, firstOrder, ['activity']);
  await page.reload({ waitUntil: 'domcontentloaded' });
  await assertOrder(page, visibleOrder, 'reordered positions and hidden panel persist after reload');
  assert.equal(await page.locator('[data-panel-id="activity"]').count(), 0, 'hidden panel stays absent');

  await page.getByRole('button', { name: 'Customize dashboard', exact: true }).click();
  await page.getByRole('button', { name: 'Reset', exact: true }).click();
  await assertOrder(page, DEFAULT_ORDER, 'reset restores all panel positions');
  await assertSaved(page, DEFAULT_ORDER);
  await page.getByRole('button', { name: 'Done customizing', exact: true }).click();
  assert.equal(await page.getByRole('button', { name: /^Reorder / }).count(), 0, 'drag handles leave with customization');
}

async function verifyBrain(page) {
  // Stabilize WebGL snapshots by disabling continuous ambient motion; gestures still invalidate/render.
  await page.emulateMedia({ reducedMotion: 'reduce' });
  const host = page.locator('.synapse-brain-3d__canvas');
  const canvas = host.locator('canvas');
  await canvas.waitFor({ state: 'visible' });
  await canvas.scrollIntoViewIfNeeded();
  await page.getByRole('button', { name: 'Reset view', exact: true }).click();
  const capture = async () => {
    await page.mouse.move(0, 0); // Clear node hover before comparing rendered pixels.
    await settle(page);
    return canvas.screenshot({ animations: 'disabled' }); // In-memory only; preserve the shared checkout.
  };
  const baseline = await capture();
  const initialView = await host.getAttribute('data-view');
  const bounds = await canvas.boundingBox();
  assert(bounds && bounds.width > 0 && bounds.height > 0, 'brain canvas has visible bounds');
  const center = { x: bounds.x + bounds.width * 0.5, y: bounds.y + bounds.height * 0.5 };
  await page.mouse.move(center.x, center.y);
  await page.mouse.down();
  assert.equal(await host.getAttribute('data-dragging'), 'true', 'brain captures drag');
  await page.mouse.move(bounds.x + bounds.width * 0.8, bounds.y + bounds.height * 0.65, { steps: 10 });
  await page.mouse.up();
  assert.equal(await host.getAttribute('data-dragging'), 'false', 'brain releases drag');
  const rotated = await capture();
  assert(!rotated.equals(baseline), 'drag changes the rendered brain');
  assert.equal(await page.locator('.syn-dash').count(), 1, 'drag does not select a navigation node');

  await page.mouse.move(center.x, center.y);
  await page.mouse.wheel(0, 250);
  const zoomed = await capture();
  assert(!zoomed.equals(rotated), 'wheel changes the rendered brain zoom');
  // A canvas corner avoids accidentally activating a glowing navigation node.
  await canvas.dblclick({ position: { x: 4, y: 4 } });
  const doubleClickReset = await capture();
  assert.equal(await host.getAttribute('data-view'), initialView, 'double-click restores the original rotation and zoom');

  await page.mouse.move(center.x, center.y);
  await page.mouse.wheel(0, -250);
  assert(!(await capture()).equals(baseline), 'zoom-in changes the brain before keyboard reset');
  await page.getByRole('button', { name: 'Reset view', exact: true }).focus();
  await page.keyboard.press('Enter');
  await capture();
  assert.equal(await host.getAttribute('data-view'), initialView, 'keyboard Reset view restores original rotation and zoom');
  const digest = buffer => createHash('sha256').update(buffer).digest('hex').slice(0, 12);
  checks.push({ check: 'brain rotation, zoom, double-click and keyboard reset',
    baseline: digest(baseline), rotated: digest(rotated), zoomed: digest(zoomed) });

  await page.getByRole('group', { name: 'Brain regions', exact: true })
    .getByRole('button', { name: 'Devices', exact: true }).focus();
  await page.keyboard.press('Enter');
  await page.getByRole('heading', { name: 'Settings', exact: true }).waitFor({ state: 'visible' });
  assert.equal(await page.locator('.syn-dash').count(), 0, 'brain region activation navigates away from dashboard');
  assert.equal(await page.getByRole('navigation', { name: 'Primary', exact: true })
    .getByRole('button', { name: 'Settings', exact: true }).getAttribute('aria-current'), 'page',
  'Devices brain region selects Settings navigation');
  checks.push({ check: 'brain region keyboard navigation', destination: 'Settings' });
}

(async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    for (const width of WIDTHS) {
      const context = await browser.newContext({ viewport: { width, height: 900 }, reducedMotion: 'reduce' });
      try {
        // Mock this narrow endpoint so a signed-in developer's account layout cannot
        // be changed by verification. Fresh contexts isolate all local preferences.
        await context.route(/\/api\/v1\/profile\/preferences(?:\?.*)?$/, async route => {
          const request = route.request();
          const headers = request.headers();
          const body = request.method() === 'PATCH' ? request.postDataJSON() : { dashboard_layout: null };
          await route.fulfill({
            status: request.method() === 'OPTIONS' ? 204 : 200,
            contentType: 'application/json',
            headers: {
              'access-control-allow-origin': headers.origin || new globalThis.URL(URL).origin,
              'access-control-allow-credentials': 'true',
              'access-control-allow-methods': 'GET, PATCH, OPTIONS',
              'access-control-allow-headers': headers['access-control-request-headers'] || 'content-type, x-synapse-token',
            },
            body: request.method() === 'OPTIONS' ? '' : JSON.stringify(body),
          });
        });
        const page = await context.newPage();
        page.setDefaultTimeout(18000);
        page.on('pageerror', error => errors.push(width + ': ' + error.message));
        await page.goto(URL, { waitUntil: 'domcontentloaded' });
        await page.locator('.syn-dash-panel').first().waitFor({ state: 'visible' });
        await settle(page);
        const overflow = await page.evaluate(() => ({
          page: document.documentElement.scrollWidth - window.innerWidth,
          body: document.body.scrollWidth - window.innerWidth,
        }));
        assert(overflow.page <= 0 && overflow.body <= 0, width + ': no horizontal page overflow');
        checks.push({ width, overflow });
        if (width === 1536) {
          await verifyReordering(page);
          await verifyBrain(page);
        }
      } finally {
        await context.close();
      }
    }
    assert.equal(errors.length, 0, 'no uncaught browser errors');
    console.log(JSON.stringify({ url: URL, checks, errors, passed: true }, null, 2));
  } catch (error) {
    errors.push(error.stack || String(error));
    console.error(JSON.stringify({ url: URL, checks, errors, passed: false }, null, 2));
    process.exitCode = 1;
  } finally {
    await browser.close();
  }
})().catch(error => {
  console.error(error.stack || error);
  process.exitCode = 1;
});

