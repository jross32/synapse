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
const publisher = JSON.parse(read('electron/update-publisher.json'));
const feed = process.env.SYNAPSE_UPDATE_FEED_URL || publisher.feedUrl;
const key = process.env.SYNAPSE_UPDATE_PUBLIC_KEY || publisher.publicKey;
check(!Object.keys(publisher).some(name => /private|secret/i.test(name)), 'Private signing fields must never be embedded');
check(updater.includes("import publisherConfig from './update-publisher.json'"), 'Immutable public publisher configuration not imported');
const packagedPublisher = path.join(root,'dist-electron/update-publisher.json');
check(fs.existsSync(packagedPublisher) && JSON.parse(fs.readFileSync(packagedPublisher,'utf8')).publicKey === key, 'Embedded public publisher configuration missing from Electron build');
if (!feed || !key) warnings.push('Publisher feed and public verification key not configured; installed updater will be disabled.');
else {
  try { check(new URL(feed).protocol === 'https:', 'Publisher feed must use HTTPS'); } catch { issues.push('Invalid publisher feed URL'); }
  try { crypto.createPublicKey(key); } catch { issues.push('Invalid publisher verification key'); }
}
warnings.push('Zero-downtime upgrade and NSIS handoff have not been proven; do not claim background services cannot stop.');
console.log(JSON.stringify({ result: issues.length ? 'BLOCKED' : 'PASS_WITH_WARNINGS', version: pkg.version, checks: 13, issues, warnings }, null, 2));
process.exitCode = issues.length ? 1 : 0;
