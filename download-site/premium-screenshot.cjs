const { chromium } = require('C:\\Users\\justi\\synapse\\node_modules\\playwright');
const path = require('path');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const url = 'file:///' + path.resolve('C:\\Users\\justi\\synapse\\download-site\\index.html').replace(/\\/g, '/');

  // Desktop
  const desktop = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await desktop.route('https://api.github.com/**', route => route.abort());
  await desktop.goto(url, { waitUntil: 'domcontentloaded' });
  await desktop.screenshot({ path: 'C:\\Users\\justi\\synapse\\download-site\\premium-desktop.png' });
  console.log('Desktop screenshot saved');
  await desktop.close();

  // Tablet
  const tablet = await browser.newPage({ viewport: { width: 768, height: 1024 } });
  await tablet.route('https://api.github.com/**', route => route.abort());
  await tablet.goto(url, { waitUntil: 'domcontentloaded' });
  await tablet.screenshot({ path: 'C:\\Users\\justi\\synapse\\download-site\\premium-tablet.png' });
  console.log('Tablet screenshot saved');
  await tablet.close();

  // Mobile
  const mobile = await browser.newPage({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
  await mobile.route('https://api.github.com/**', route => route.abort());
  await mobile.goto(url, { waitUntil: 'domcontentloaded' });
  await mobile.screenshot({ path: 'C:\\Users\\justi\\synapse\\download-site\\premium-mobile.png' });
  console.log('Mobile screenshot saved');
  await mobile.close();

  await browser.close();
  process.exit(0);
})().catch(e => {
  console.error(e);
  process.exit(1);
});
