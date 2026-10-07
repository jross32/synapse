import { chromium } from 'playwright';

const baseUrl = process.env.SYNAPSE_VERIFY_URL || 'http://127.0.0.1:5198';
const browser = await chromium.launch({ headless: true });
let failed = false;

for (const viewport of [
  { name: 'desktop', width: 1440, height: 900 },
  { name: 'mobile', width: 390, height: 844 },
]) {
  const page = await browser.newPage({ viewport });
  const errors = [];
  page.on('pageerror', (error) => errors.push(String(error)));

  try {
    await page.goto(baseUrl, { waitUntil: 'domcontentloaded', timeout: 30_000 });
    await page.getByRole('button', { name: 'Settings' }).click();
    await page.waitForTimeout(2_500);
    await page.getByRole('button', { name: 'Open profile' }).click();

    const home = page.getByTestId('account-apps-home');
    await home.waitFor({ state: 'visible' });
    for (const label of ['Gmail & Google', 'GitHub', 'Cloudflare', 'eBay', 'More']) {
      if (!(await home.getByText(label, { exact: true }).isVisible())) throw new Error(`Missing featured app: ${label}`);
    }

    await home.getByRole('button', { name: 'Show more apps' }).click();
    const all = page.getByTestId('account-apps-all');
    await all.waitFor({ state: 'visible' });
    const allText = await all.innerText();
    for (const label of ['Gmail & Google', 'GitHub', 'Cloudflare', 'eBay', 'Google Drive', 'Google Calendar', 'Slack', 'Discord', 'Canva', 'Adobe']) {
      if (!allText.includes(label)) throw new Error(`Missing catalog app: ${label}`);
    }

    await all.getByRole('button', { name: /Gmail & Google/ }).click();
    const detail = page.getByTestId('account-app-detail');
    await detail.waitFor({ state: 'visible' });
    const detailText = await detail.innerText();
    for (const phrase of ['Gmail & Google', 'Access', 'Privacy', 'Similar apps']) {
      if (!detailText.includes(phrase)) throw new Error(`Missing detail section: ${phrase}`);
    }

    await detail.getByRole('button', { name: /All apps/ }).click();
    await page.getByTestId('account-apps-all').waitFor({ state: 'visible' });
    await page.getByRole('button', { name: /Accounts/ }).click();
    await page.getByTestId('account-apps-home').waitFor({ state: 'visible' });

    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);
    if (overflow) throw new Error('Horizontal document overflow detected');
    if (errors.length) throw new Error(`Browser errors: ${errors.join(' | ')}`);
    console.log(`PASS ${viewport.name}: account apps navigation, catalog, detail, back-stack, and overflow`);
  } catch (error) {
    failed = true;
    console.error(`FAIL ${viewport.name}: ${error instanceof Error ? error.message : String(error)}`);
  } finally {
    await page.close();
  }
}

await browser.close();
if (failed) process.exit(1);

