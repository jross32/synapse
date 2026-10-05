const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({
    viewport: { width: 390, height: 844 },
    hasTouch: true,
    isMobile: true
  });
  const errors = [];
  page.on('pageerror', error => errors.push('pageerror: ' + error.message));
  page.on('console', message => {
    if (message.type() === 'error') errors.push('console: ' + message.text());
  });

  await page.goto('http://127.0.0.1:8091', { waitUntil: 'networkidle' });
  await page.evaluate(() => localStorage.removeItem('signal-drift-best-score'));
  await page.reload({ waitUntil: 'networkidle' });

  const initial = await page.evaluate(() => ({
    state: window.__SIGNAL_DRIFT__.getState(),
    bestText: document.getElementById('best').textContent,
    shareDisabled: document.getElementById('share-score').disabled,
    touchDisplay: getComputedStyle(document.querySelector('.touch-controls')).display
  }));

  const right = page.locator('[data-touch-code="ArrowRight"]');
  const box = await right.boundingBox();
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await page.waitForTimeout(180);
  await page.mouse.up();
  const afterMove = await page.evaluate(() => window.__SIGNAL_DRIFT__.getState());

  await page.click('#dash-button');
  const afterDash = await page.evaluate(() => window.__SIGNAL_DRIFT__.getState());

  await page.waitForTimeout(250);
  await page.evaluate(() => window.__SIGNAL_DRIFT__.defeat());
  const defeated = await page.evaluate(() => ({
    state: window.__SIGNAL_DRIFT__.getState(),
    bestText: document.getElementById('best').textContent,
    savedBest: localStorage.getItem('signal-drift-best-score'),
    shareDisabled: document.getElementById('share-score').disabled,
    shareText: window.__SIGNAL_DRIFT__.shareText()
  }));

  await page.evaluate(() => {
    Object.defineProperty(navigator, 'share', { configurable: true, value: undefined });
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText: async text => { window.__COPIED_RUN__ = text; } }
    });
  });
  await page.click('#share-score');
  const shared = await page.evaluate(() => ({
    copied: window.__COPIED_RUN__ || '',
    status: document.getElementById('status').textContent
  }));

  await page.reload({ waitUntil: 'networkidle' });
  const reloaded = await page.evaluate(() => ({
    bestText: document.getElementById('best').textContent,
    savedBest: localStorage.getItem('signal-drift-best-score'),
    shareDisabled: document.getElementById('share-score').disabled
  }));

  const result = {
    initial,
    afterMove,
    afterDash,
    defeated,
    shared,
    reloaded,
    errors,
    assertions: {
      touchVisible: initial.touchDisplay !== 'none',
      movedRight: afterMove.playerX > initial.state.playerX,
      dashTriggered: afterDash.dashActive || afterDash.dashCooldown > 0,
      defeated: defeated.state.running === false,
      shareEnabledAfterDefeat: defeated.shareDisabled === false && defeated.state.shareEnabled === true,
      bestPersisted: Number(defeated.savedBest) > 0 && reloaded.savedBest === defeated.savedBest,
      copiedChallenge: shared.copied.includes('Signal Drift:') && shared.copied.includes('Can you beat it?'),
      shareDisabledAfterReload: reloaded.shareDisabled === true,
      noBrowserErrors: errors.length === 0
    }
  };

  console.log(JSON.stringify(result, null, 2));
  await browser.close();

  if (Object.values(result.assertions).some(value => !value)) process.exitCode = 1;
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});