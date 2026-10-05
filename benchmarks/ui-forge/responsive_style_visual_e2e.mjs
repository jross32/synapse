#!/usr/bin/env node
import fs from 'node:fs/promises';
import net from 'node:net';
import path from 'node:path';
import process from 'node:process';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { createServer } from 'vite';
import react from '@vitejs/plugin-react';
import { chromium } from 'playwright';

import uiForgeSourceTags from '../../templates/skills/ui-forge/scripts/babel_source_tags.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(HERE, '../..');
const BRIDGE = path.join(REPO, 'templates/skills/ui-forge/scripts/visual_edit_bridge.js');
const AUDIT = path.join(REPO, 'templates/skills/ui-forge/scripts/browser_audit.js');
const CSS_EDITOR = path.join(REPO, 'templates/skills/ui-forge/scripts/css_style_editor.mjs');
const RESULTS = path.join(HERE, 'results');

function fail(message, detail = {}) { const e = new Error(message); e.detail = detail; throw e; }
async function freePort() {
  return await new Promise((resolve, reject) => {
    const s = net.createServer(); s.unref(); s.once('error', reject); s.listen(0, '127.0.0.1', () => {
      const a = s.address(); const port = typeof a === 'object' && a ? a.port : 0; s.close((err) => err ? reject(err) : resolve(port));
    });
  });
}
async function fixture(root) {
  await fs.mkdir(path.join(root, 'src'), { recursive: true });
  await fs.writeFile(path.join(root, 'index.html'), '<!doctype html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="icon" href="data:,"><title>Responsive Style E2E</title></head><body><div id="root"></div><script type="module" src="/src/main.jsx"></script></body></html>', 'utf8');
  await fs.writeFile(path.join(root, 'src/main.jsx'), "import React from 'react';\nimport { createRoot } from 'react-dom/client';\nimport App from './App.jsx';\nimport './styles.css';\ncreateRoot(document.getElementById('root')).render(<App />);\n", 'utf8');
  await fs.writeFile(path.join(root, 'src/App.jsx'), "import React from 'react';\nexport default function App(){return <main className=\"shell\"><h1>Responsive owner edit</h1><button id=\"cta\" className=\"cta\">Launch</button></main>}\n", 'utf8');
await fs.writeFile(path.join(root, 'src/styles.css'), `:root { font-family: Inter, system-ui, sans-serif; background: #0b1016; color: #f5f7f9; }
* { box-sizing: border-box; }
body { margin: 0; min-width: 320px; }
.shell { min-height: 100vh; display: grid; place-content: center; justify-items: start; gap: 20px; padding: 28px; }
.cta { min-height: 48px; padding: 0 20px; border: 0; border-radius: 10px; font: inherit; font-weight: 700; }
@media (max-width: 640px) { .cta { padding: 0 12px; border-radius: 8px; } }
`, 'utf8');
}

async function run() {
  await fs.mkdir(RESULTS, { recursive: true });
  const root = await fs.mkdtemp(path.join(REPO, '.tmp-ui-forge-css-e2e-'));
  let server; let browser; let stage = 'setup'; const started = performance.now();
  try {
    stage = 'fixture'; await fixture(root); const port = await freePort();
    stage = 'vite'; server = await createServer({ root, logLevel: 'silent', plugins: [react({ babel: { plugins: [[uiForgeSourceTags, { root }]] } })], server: { host: '127.0.0.1', port, strictPort: true } }); await server.listen();
    stage = 'browser'; browser = await chromium.launch({ headless: true, timeout: 45_000 }); const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
    const consoleErrors = []; const pageErrors = []; page.on('console', (m) => { if (m.type() === 'error') consoleErrors.push({ text: m.text(), location: m.location() }); }); page.on('pageerror', (e) => pageErrors.push(e.message));
    await page.goto(`http://127.0.0.1:${port}`, { waitUntil: 'domcontentloaded', timeout: 20_000 }); await page.locator('#cta').waitFor({ state: 'visible', timeout: 10_000 });
    await page.addScriptTag({ path: BRIDGE });
    const before = await page.locator('#cta').evaluate((el) => { const s = getComputedStyle(el); return { source: el.getAttribute('data-ui-forge-source'), id: el.getAttribute('data-ui-forge-id'), width: el.getBoundingClientRect().width, paddingLeft: s.paddingLeft, borderRadius: s.borderRadius, inlineStyle: el.getAttribute('style') }; });
    if (!before.source || !before.id) fail('source identity missing', { before });

    stage = 'preview';
    const preview = await page.evaluate(() => {
      window.UIForge.select('#cta');
      const result = window.UIForge.preview({ type: 'style_props', properties: { padding: '0 28px', 'border-radius': '16px' }, media_chain: ['(max-width: 640px)'] });
      const node = document.querySelector('#cta'); const duringStyle = getComputedStyle(node); const during = { width: node.getBoundingClientRect().width, paddingLeft: duringStyle.paddingLeft, borderRadius: duringStyle.borderRadius, inlineStyle: node.getAttribute('style') };
      const normalCommit = window.UIForge.commitSpec(); const styleCommit = window.UIForge.styleCommitSpec(); const reverted = window.UIForge.revertPreview(); const afterStyle = getComputedStyle(node); const after = { width: node.getBoundingClientRect().width, paddingLeft: afterStyle.paddingLeft, borderRadius: afterStyle.borderRadius, inlineStyle: node.getAttribute('style') };
      return { result, during, normalCommit, styleCommit, reverted, after };
    });
    if (!preview.result?.style_commit_ready || !preview.styleCommit?.ok) fail('style preview was not CSS-commit-ready', { preview });
    if (preview.normalCommit?.ok || !preview.normalCommit?.style_request) fail('style preview incorrectly advertised JSX commit readiness', { preview });
    if (preview.during.paddingLeft !== '28px' || preview.during.borderRadius !== '16px' || preview.during.width <= before.width) fail('browser style preview did not change geometry/style', { before, preview });
    if (preview.after.paddingLeft !== before.paddingLeft || preview.after.borderRadius !== before.borderRadius || preview.after.inlineStyle !== before.inlineStyle) fail('style preview did not revert exactly', { before, preview });

    stage = 'css-commit'; const spec = path.join(root, 'style-request.json'); await fs.writeFile(spec, `${JSON.stringify(preview.styleCommit, null, 2)}\n`, 'utf8');
    const edit = spawnSync(process.execPath, [CSS_EDITOR, root, spec], { cwd: REPO, encoding: 'utf8', timeout: 30_000, windowsHide: true }); let editResult; try { editResult = JSON.parse(edit.stdout || '{}'); } catch { fail('CSS editor did not emit JSON', { stdout: edit.stdout, stderr: edit.stderr }); }
    if (edit.status !== 0 || !editResult.ok || editResult.selector !== '.cta' || JSON.stringify(editResult.media_chain) !== JSON.stringify(['(max-width: 640px)'])) fail('CSS ownership commit failed', { editResult, stderr: edit.stderr });

    stage = 'hmr'; await page.waitForFunction(() => { const el = document.querySelector('#cta'); if (!el) return false; const s = getComputedStyle(el); return true; }, null, { timeout: 15_000 });
    const committed = await page.locator('#cta').evaluate((el) => { const s = getComputedStyle(el); return { source: el.getAttribute('data-ui-forge-source'), id: el.getAttribute('data-ui-forge-id'), width: el.getBoundingClientRect().width, paddingLeft: s.paddingLeft, borderRadius: s.borderRadius, inlineStyle: el.getAttribute('style') }; }); if (committed.paddingLeft !== '28px' || committed.borderRadius !== '16px') fail('mobile committed responsive style not active', { committed }); await page.setViewportSize({ width: 900, height: 700 }); const desktopAfter = await page.locator('#cta').evaluate((el) => { const s=getComputedStyle(el); return {paddingLeft:s.paddingLeft,borderRadius:s.borderRadius}; }); if (desktopAfter.paddingLeft !== '20px' || desktopAfter.borderRadius !== '10px') fail('responsive edit leaked into desktop base style', { desktopAfter }); await page.setViewportSize({ width: 390, height: 844 });
    if (committed.source !== before.source || committed.id !== before.id) fail('source identity changed after CSS HMR', { before, committed });
    if (committed.inlineStyle !== before.inlineStyle) fail('committed style leaked into inline DOM style', { committed });

    stage = 'audit'; await page.addScriptTag({ path: AUDIT }); const desktop = await page.evaluate(() => window.UIForgeAudit.run()); await page.setViewportSize({ width: 390, height: 844 }); const mobile = await page.evaluate(() => window.UIForgeAudit.run());
    for (const audit of [desktop, mobile]) for (const key of ['horizontal_overflow','missing_interactive_name_count','unlabeled_form_control_count','missing_image_alt_count','heading_level_jump_count']) { const value = audit.violations[key]; if (value === true || (typeof value === 'number' && value > 0)) fail(`audit failed: ${key}`, { audit }); }
    if (consoleErrors.length || pageErrors.length) fail('browser emitted errors', { consoleErrors, pageErrors });
    const css = await fs.readFile(path.join(root, 'src/styles.css'), 'utf8'); if (!css.includes('@media (max-width: 640px)') || !css.includes('padding: 0 28px') || !css.includes('border-radius: 16px')) fail('stylesheet did not persist responsive edit', { css });

    const result = { schema: 'ui-forge-responsive-style-visual-e2e-v1', generated_at: new Date().toISOString(), overall_pass: true, duration_ms: Math.round((performance.now()-started)*1000)/1000, before, preview: { during: preview.during, after_revert: preview.after, normal_commit_refused: !preview.normalCommit.ok }, css_commit: editResult, committed, identity_stable: committed.source === before.source && committed.id === before.id, inline_style_clean: committed.inlineStyle === before.inlineStyle, browser: { console_errors: consoleErrors, page_errors: pageErrors, desktop_violations: desktop.violations, mobile_violations: mobile.violations }, claims: { reversible_css_preview_pass: true, css_owner_commit_pass: true, no_inline_style_debt: true, not_a_full_ui_forge_or_lovable_claim: true } };
    await fs.writeFile(path.join(RESULTS, 'responsive-style-visual-e2e-latest.json'), `${JSON.stringify(result, null, 2)}\n`, 'utf8'); console.log(JSON.stringify(result, null, 2)); return 0;
  } catch (error) {
    const result = { schema: 'ui-forge-responsive-style-visual-e2e-v1', generated_at: new Date().toISOString(), overall_pass: false, stage, error: error.message, detail: error.detail || {}, duration_ms: Math.round((performance.now()-started)*1000)/1000 };
    await fs.writeFile(path.join(RESULTS, 'responsive-style-visual-e2e-latest.json'), `${JSON.stringify(result, null, 2)}\n`, 'utf8'); console.error(JSON.stringify(result, null, 2)); return 1;
  } finally { if (browser) await browser.close().catch(() => {}); if (server) await server.close().catch(() => {}); await fs.rm(root, { recursive: true, force: true }).catch(() => {}); }
}
process.exitCode = await run();

