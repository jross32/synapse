const { chromium } = require('../node_modules/playwright');
const path = require('path');
const fs = require('fs');
const assert = require('node:assert/strict');
const url = 'file:///' + path.resolve(__dirname, 'index.html').replace(/\\/g, '/');

(async () => {
  const script = fs.readFileSync(path.resolve(__dirname, 'app.js'), 'utf8');
  const messageArray = script.match(/const heroMessages = \[([\s\S]*?)\];/);
  assert.ok(messageArray, 'Hero rotation must be defined');
  assert.equal(messageArray[1].split('\n').filter(line => line.trim().startsWith("'") || line.includes('heroLede.textContent.trim()')).length, 10, 'Exactly ten messages should rotate');

  const browser = await chromium.launch({ headless: true, timeout: 15000 });
  const errors = [];
  try {
    const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
    await page.route('https://api.github.com/**', route => route.abort());
    page.on('pageerror', error => errors.push(error.message));
    await page.clock.install();
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 12000 });

    const original = (await page.locator('.hero .lede').textContent()).trim();
    assert.ok(original.startsWith('Bring your AI assistants'));
    await page.clock.runFor(25000);
    assert.equal(await page.locator('.hero .lede').textContent(), original, 'Original holds through the first 25 seconds');

    await page.clock.runFor(5600);
    const changing = await page.locator('.hero .lede').textContent();
    assert.notEqual(changing, original, 'Text should start changing at 30 seconds');
    assert.equal(await page.locator('.hero .lede').evaluate(el => el.classList.contains('is-typing')), true);

    await page.clock.runFor(3200);
    const next = await page.locator('.hero .lede').textContent();
    assert.ok(next.includes('One command center for your AI assistants'), 'First replacement should be fully typed');
    assert.equal(await page.locator('.hero .lede').evaluate(el => el.classList.contains('is-typing')), false);
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false, 'No mobile overflow');
    assert.ok(await page.locator('.hero .lede').evaluate(el => parseFloat(getComputedStyle(el).minHeight) > 100), 'Mobile text height must be reserved');

    await page.clock.runFor(20000);
    assert.equal(await page.locator('.hero .lede').textContent(), next, 'Subsequent text should also hold for 30 seconds');

    const reduced = await browser.newPage({ reducedMotion: 'reduce' });
    await reduced.route('https://api.github.com/**', route => route.abort());
    await reduced.clock.install();
    await reduced.goto(url, { waitUntil: 'domcontentloaded', timeout: 12000 });
    await reduced.clock.runFor(60000);
    assert.equal((await reduced.locator('.hero .lede').textContent()).trim(), original, 'Reduced-motion visitors see stable original text');
    assert.deepEqual(errors, [], 'No page JavaScript errors');
    console.log('PASS 10 messages, initial 30-second hold, fast erase/type, next hold, mobile layout, reduced motion, JS errors');
  } finally {
    await Promise.race([
      browser.close(),
      new Promise(resolve => setTimeout(() => {
        console.warn('Browser shutdown exceeded 4 seconds; the assertions completed.');
        resolve();
      }, 4000))
    ]);
  }
})().then(() => process.exit(0)).catch(error => {
  console.error('FAIL', error);
  process.exit(1);
});
