const { _electron: electron } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');
(async () => {
  const root = path.resolve(__dirname, '..');
  const executablePath = path.join(root, 'release', 'win-unpacked', 'Synapse.exe');
  const userData = path.join(root, 'artifacts', 'packaged-smoke-profile');
  if (!fs.existsSync(executablePath)) throw new Error('Packaged Synapse.exe missing');
  if (fs.existsSync(userData)) throw new Error('Refusing to reuse existing smoke profile');
  const app = await electron.launch({ executablePath, args: ['--user-data-dir=' + userData], timeout: 45000 });
  try {
    const page = await app.firstWindow({ timeout: 45000 });
    await page.waitForLoadState('domcontentloaded');
    await page.getByText('YOUR JOURNEY', { exact: true }).waitFor({ state: 'visible', timeout: 90000 });
    const title = await page.title();
    const body = (await page.locator('body').innerText()).slice(0, 1000);
    const marker = JSON.parse(fs.readFileSync(path.join(userData, 'first-launch-install-v1.json'), 'utf8'));
    const screenshot = path.join(root, 'artifacts', 'packaged-smoke-first-launch.png');
    await page.screenshot({ path: screenshot, fullPage: true });
    console.log(JSON.stringify({ title, marker, welcomeVisible: /get started|first.launch|your journey/i.test(body), body: body.slice(0, 350), screenshot }));
    if (marker.disposition !== 'new') throw new Error('Fresh install not classified new');
    if (!/get started|first.launch|your journey/i.test(body)) throw new Error('Welcome not rendered');
  } finally { await app.close(); }
})().catch(e => { console.error(e); process.exitCode = 1; });
