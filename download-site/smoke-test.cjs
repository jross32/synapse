const { chromium } = require('../node_modules/playwright');
const path = require('path');
const assert = require('node:assert/strict');

(async () => {
  const browser = await chromium.launch({ headless: true, timeout: 15000 });
  let failures = 0;
  const url = 'file:///' + path.resolve(__dirname, 'index.html').replace(/\\/g, '/');
  try {
    for (const [label, width, height] of [
      ['desktop', 1440, 900], ['tablet', 768, 1024],
      ['iphone', 390, 844], ['small-iphone', 320, 700]
    ]) {
      const page = await browser.newPage({
        viewport: { width, height }, deviceScaleFactor: 1,
        isMobile: label.includes('iphone'), hasTouch: label.includes('iphone')
      });
      await page.route('https://api.github.com/**', route => route.abort());
      await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 12000 });
      const result = await page.evaluate(() => ({
        overflow: document.documentElement.scrollWidth > innerWidth,
        heading: document.querySelector('h1')?.innerText,
        download: document.getElementById('download-windows')?.getAttribute('href'),
        cards: document.querySelectorAll('.platform').length
      }));
      console.log(label, JSON.stringify(result));
      if (result.overflow || result.cards !== 3 ||
        !/^https:\/\/github\.com\/jross32\/synapse\/releases\/download\/v(\d+\.\d+\.\d+)\/Synapse\.Setup\.\1\.exe$/.test(result.download ?? '')) {
        failures++;
      }
      if (label === 'iphone') {
        await page.locator('#menu-toggle').click();
        const expanded = await page.locator('#menu-toggle').getAttribute('aria-expanded');
        const visible = await page.locator('#primary-nav').isVisible();
        console.log('iphone-menu', expanded, visible);
        if (expanded !== 'true' || !visible) failures++;
        await page.locator('#primary-nav a[href="#downloads"]').click();
        if (await page.locator('#menu-toggle').getAttribute('aria-expanded') !== 'false') failures++;
      }
      await page.close();
    }
    console.log('FAILURES', failures);
    assert.equal(failures, 0);
  } finally {
    await Promise.race([
      browser.close(),
      new Promise(resolve => setTimeout(resolve, 4000))
    ]);
  }
})().then(() => process.exit(0)).catch(error => {
  console.error(error);
  process.exit(1);
});
