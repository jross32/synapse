#!/usr/bin/env node
'use strict';
/* Read-only packaging gate. No installs, process termination, or deployment. */
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const root = path.resolve(__dirname, '..');
const read = (name) => fs.readFileSync(path.join(root, name), 'utf8');
const issues = [];
const warnings = [];
function check(ok, message) { if (!ok) issues.push(message); }
const pkg = JSON.parse(read('package.json'));
const main = read('electron/main.ts');
const preload = read('electron/preload.ts');
const updater = read('electron/desktop-updater.ts');
const ui = read('renderer/App.tsx');
const notice = read('renderer/components/DesktopUpdateNotice.tsx');
check(pkg.build?.win?.target === 'nsis', 'Windows NSIS target missing');
check(pkg.build?.files?.includes('dist-electron/**/*'), 'Electron bundle excluded from installer');
check(main.includes('registerDesktopUpdater();'), 'Updater IPC not registered');
check(preload.includes('synapse:update-check') && preload.includes('synapse:update-install'), 'Update bridge incomplete');
check(ui.includes('<DesktopUpdateNotice />') && notice.includes('installDesktopUpdate'), 'Update banner not wired');
check(updater.includes('crypto.verify(') && updater.includes("createHash('sha256')"), 'Release signature or hash verification missing');
check(updater.includes('https.get(') && updater.includes('request.destroy'), 'HTTPS download protection missing');
check(updater.includes('if (!app.isPackaged'), 'Dev mode must disable updater');
check(!updater.includes('restartApp(') && !updater.includes('daemonProc.kill('), 'Updater must not stop live services');
check(fs.existsSync(path.join(root, 'dist-electron/desktop-updater.js')), 'Build Electron before packaging');
check(fs.existsSync(path.join(root, 'dist/index.html')), 'Build renderer before packaging');
const { publicKey, privateKey } = crypto.generateKeyPairSync('ed25519');
const artifact = { url: 'https://updates.example.test/setup.exe', sha256: 'a'.repeat(64), size: 1024 };
const payload = JSON.stringify({ version: '0.1.999', notes: 'Preflight', windows: artifact });
const signature = crypto.sign(null, Buffer.from(payload), privateKey);
check(crypto.verify(null, Buffer.from(payload), publicKey, signature), 'Signature verification self-test failed');
check(!crypto.verify(null, Buffer.from(payload + 'tampered'), publicKey, signature), 'Signature tampering test failed');
const feed = process.env.SYNAPSE_UPDATE_FEED_URL;
const key = process.env.SYNAPSE_UPDATE_PUBLIC_KEY;
const bundledConfigFile = path.join(root, 'dist-electron/update-publisher.json');
if (fs.existsSync(bundledConfigFile)) {
  try {
    const bundled = JSON.parse(fs.readFileSync(bundledConfigFile, 'utf8'));
    check(bundled.schema === 1, 'Bundled publisher schema missing or wrong');
    check(new URL(bundled.feed_url).protocol === 'https:', 'Bundled publisher URL must use HTTPS');
    check(crypto.createPublicKey(bundled.public_key).asymmetricKeyType === 'ed25519',
      'Bundled publisher key must be Ed25519');
  } catch (error) { issues.push('Bundled updater publisher metadata invalid: ' + String(error)); }
} else if (!feed || !key) {
  issues.push('No bundled publisher trust config or explicit legacy publisher env supplied');
} else {
  try { check(new URL(feed).protocol === 'https:', 'Publisher feed must use HTTPS'); } catch { issues.push('Invalid publisher feed URL'); }
  try { check(crypto.createPublicKey(key).asymmetricKeyType === 'ed25519', 'Invalid publisher verification key'); }
  catch { issues.push('Invalid publisher verification key'); }
}
warnings.push('Zero-downtime upgrade and NSIS handoff have not been proven; do not claim background services cannot stop.');
console.log(JSON.stringify({ result: issues.length ? 'BLOCKED' : 'PASS_WITH_WARNINGS', version: pkg.version, checks: 13, issues, warnings }, null, 2));
process.exitCode = issues.length ? 1 : 0;
