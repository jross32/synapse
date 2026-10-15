const { _electron: electron } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');
(async () => {
  const root = path.resolve(__dirname, '..');
  const executablePath = path.join(root, 'release', 'win-unpacked', 'Synapse.exe');
  const userData = path.join(root, 'artifacts', 'packaged-smoke-profile-' + process.pid);
  if (!fs.existsSync(executablePath)) throw new Error('Packaged Synapse.exe missing');
  if (fs.existsSync(userData)) throw new Error('Refusing to reuse existing smoke profile');
  const app = await electron.launch({ executablePath, args: ['--user-data-dir=' + userData], timeout: 45000 });
  try {
    // The first Electron window is the startup progress screen, not the renderer.
    const deadline = Date.now() + 90000;
    let page;
    while (Date.now() < deadline) {
      const windows = app.windows();
      const titles = await Promise.all(windows.map(w => w.title().catch(() => '')));
      console.log('Electron windows:', JSON.stringify(titles));
      const index = titles.findIndex(t => t && !/Starting Synapse/i.test(t));
      if (index >= 0) { page = windows[index]; break; }
      await new Promise(resolve => setTimeout(resolve, 3000));
    }
    if (!page) throw new Error('Main renderer window did not open');
    await page.getByRole('button', { name: /get started/i }).waitFor({ state: 'visible', timeout: 45000 });
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
