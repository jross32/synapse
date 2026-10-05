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
const BATCH = path.join(REPO, 'templates/skills/ui-forge/scripts/batch_ast_edit.mjs');
const RESULTS = path.join(HERE, 'results');

function fail(message, detail = {}) {
  const error = new Error(message);
  error.detail = detail;
  throw error;
}

async function freePort() {
  return await new Promise((resolve, reject) => {
    const server = net.createServer();
    server.unref();
    server.once('error', reject);
    server.listen(0, '127.0.0.1', () => {
      const addr = server.address();
      const port = typeof addr === 'object' && addr ? addr.port : 0;
      server.close((error) => error ? reject(error) : resolve(port));
    });
  });
}

async function fixture(root) {
  await fs.mkdir(path.join(root, 'src'), { recursive: true });
  await fs.writeFile(path.join(root, 'index.html'), `<!doctype html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="icon" href="data:,"><title>UI Forge Batch E2E</title></head><body><div id="root"></div><script type="module" src="/src/main.jsx"></script></body></html>`, 'utf8');
  await fs.writeFile(path.join(root, 'src/main.jsx'), `import React from 'react';\nimport { createRoot } from 'react-dom/client';\nimport App from './App.jsx';\nimport './styles.css';\ncreateRoot(document.getElementById('root')).render(<App />);\n`, 'utf8');
  await fs.writeFile(path.join(root, 'src/App.jsx'), `import React from 'react';\n\nexport default function App() {\n  return (\n    <main className="shell">\n      <h1>Batch visual edit</h1>\n      <div className="actions">\n        <button id="one" className="cta">One</button>\n        <button id="two" className="cta">Two</button>\n        <button id="three" className="cta">Three</button>\n      </div>\n    </main>\n  );\n}\n`, 'utf8');
  await fs.writeFile(path.join(root, 'src/styles.css'), `:root{font-family:Inter,system-ui,sans-serif;background:#0b1016;color:#f5f7f9}*{box-sizing:border-box}body{margin:0;min-width:320px}.shell{min-height:100vh;display:grid;place-content:center;gap:20px;padding:28px}.actions{display:flex;flex-wrap:wrap;gap:12px}.cta{min-height:48px;padding:0 20px;border:0;border-radius:10px;font:inherit}.cta.emphasis{outline:3px solid currentColor;outline-offset:3px}`, 'utf8');
}

async function run() {
  await fs.mkdir(RESULTS, { recursive: true });
  const root = await fs.mkdtemp(path.join(REPO, '.tmp-ui-forge-batch-e2e-'));
  let server;
  let browser;
  let stage = 'setup';
  const started = performance.now();
  try {
    stage = 'fixture';
    await fixture(root);
    const port = await freePort();
    stage = 'vite';
    server = await createServer({
      root,
      logLevel: 'silent',
      plugins: [react({ babel: { plugins: [[uiForgeSourceTags, { root }]] } })],
      server: { host: '127.0.0.1', port, strictPort: true },
    });
    await server.listen();
    const url = `http://127.0.0.1:${port}`;

    stage = 'browser';
    browser = await chromium.launch({ headless: true, timeout: 15_000 });
    const page = await browser.newPage({ viewport: { width: 900, height: 700 } });
    const consoleErrors = [];
    const pageErrors = [];
    page.on('console', (msg) => { if (msg.type() === 'error') consoleErrors.push({ text: msg.text(), location: msg.location() }); });
    page.on('pageerror', (error) => pageErrors.push(error.message));
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 20_000 });
    await page.locator('#three').waitFor({ state: 'visible', timeout: 10_000 });

    stage = 'select-preview';
    await page.addScriptTag({ path: BRIDGE });
    const before = await page.evaluate(() => ['#one','#two','#three'].map((selector) => {
      const node = document.querySelector(selector);
      return { selector, source: node.getAttribute('data-ui-forge-source'), id: node.getAttribute('data-ui-forge-id'), cls: node.className };
    }));
    if (before.some((item) => !item.source || !item.id)) fail('compile-time source identity missing', { before });
    const preview = await page.evaluate(() => {
      const selected = window.UIForge.selectMany(['#one','#two','#three']);
      const result = window.UIForge.previewMany({ type: 'class_tokens', add: ['emphasis'], remove: [] });
      const during = ['#one','#two','#three'].map((s) => document.querySelector(s).className);
      const commit = window.UIForge.commitBatchSpec();
      const reverted = window.UIForge.revertBatchPreview();
      const after = ['#one','#two','#three'].map((s) => document.querySelector(s).className);
      return { selected, result, during, commit, reverted, after };
    });
    if (!preview.selected?.ok || preview.selected.selection_count !== 3) fail('multi-select failed', { preview });
    if (!preview.result?.commit_ready || !preview.commit?.ok || preview.commit.source_edits?.length !== 3) fail('batch preview was not commit-ready', { preview });
    if (!preview.during.every((cls) => cls.includes('emphasis'))) fail('batch preview did not affect every selected element', { preview });
    if (!preview.after.every((cls) => cls === 'cta')) fail('batch preview did not revert cleanly', { preview });

    stage = 'atomic-commit';
    const spec = path.join(root, 'batch.json');
    await fs.writeFile(spec, `${JSON.stringify({ edits: preview.commit.source_edits }, null, 2)}\n`, 'utf8');
    const apply = spawnSync(process.execPath, [BATCH, root, spec], { cwd: REPO, encoding: 'utf8', timeout: 45_000, windowsHide: true });
    let applyResult;
    try { applyResult = JSON.parse(apply.stdout || '{}'); } catch { fail('batch editor did not emit JSON', { stdout: apply.stdout, stderr: apply.stderr }); }
    if (apply.status !== 0 || !applyResult.ok || applyResult.edit_count !== 3 || applyResult.atomic !== true) fail('atomic batch source commit failed', { applyResult, stderr: apply.stderr });

    stage = 'hmr';
    await page.waitForFunction(() => ['one','two','three'].every((id) => document.getElementById(id)?.classList.contains('emphasis')), null, { timeout: 15_000 });
    const committed = await page.evaluate(() => ['#one','#two','#three'].map((selector) => {
      const node = document.querySelector(selector);
      return { selector, source: node.getAttribute('data-ui-forge-source'), id: node.getAttribute('data-ui-forge-id'), cls: node.className };
    }));
    for (let i = 0; i < before.length; i += 1) {
      if (committed[i].source !== before[i].source || committed[i].id !== before[i].id) fail('source identity changed after batch HMR', { before, committed });
      if (!committed[i].cls.includes('emphasis')) fail('committed class missing after HMR', { committed });
    }

    stage = 'audit';
    await page.addScriptTag({ path: AUDIT });
    const desktop = await page.evaluate(() => window.UIForgeAudit.run());
    await page.setViewportSize({ width: 390, height: 844 });
    const mobile = await page.evaluate(() => window.UIForgeAudit.run());
    const blockers = ['horizontal_overflow','missing_interactive_name_count','unlabeled_form_control_count','missing_image_alt_count','heading_level_jump_count'];
    for (const [label, audit] of [['desktop', desktop], ['mobile', mobile]]) {
      for (const key of blockers) {
        const value = audit.violations[key];
        if (value === true || (typeof value === 'number' && value > 0)) fail(`${label} audit failed: ${key}`, { audit });
      }
    }
    if (consoleErrors.length || pageErrors.length) fail('browser emitted errors', { consoleErrors, pageErrors });

    const source = await fs.readFile(path.join(root, 'src/App.jsx'), 'utf8');
    if ((source.match(/className="cta emphasis"/g) || []).length !== 3) fail('source did not persist all three batch class edits', { source });

    const result = {
      schema: 'ui-forge-batch-visual-edit-e2e-v1',
      generated_at: new Date().toISOString(),
      overall_pass: true,
      duration_ms: Math.round((performance.now() - started) * 1000) / 1000,
      selection_count: 3,
      preview: { commit_ready: preview.result.commit_ready, reverted_cleanly: preview.after.every((cls) => cls === 'cta') },
      source_commit: applyResult,
      identity_stable: committed.every((item, index) => item.source === before[index].source && item.id === before[index].id),
      browser: { console_errors: consoleErrors, page_errors: pageErrors, desktop_violations: desktop.violations, mobile_violations: mobile.violations },
      claims: { multi_select_preview_pass: true, atomic_batch_commit_pass: true, batch_hmr_identity_pass: true, not_a_full_ui_forge_or_lovable_claim: true },
    };
    await fs.writeFile(path.join(RESULTS, 'batch-visual-edit-e2e-latest.json'), `${JSON.stringify(result, null, 2)}\n`, 'utf8');
    console.log(JSON.stringify(result, null, 2));
    return 0;
  } catch (error) {
    const result = { schema: 'ui-forge-batch-visual-edit-e2e-v1', generated_at: new Date().toISOString(), overall_pass: false, stage, error: error.message, detail: error.detail || {}, duration_ms: Math.round((performance.now() - started) * 1000) / 1000 };
    await fs.writeFile(path.join(RESULTS, 'batch-visual-edit-e2e-latest.json'), `${JSON.stringify(result, null, 2)}\n`, 'utf8');
    console.error(JSON.stringify(result, null, 2));
    return 1;
  } finally {
    if (browser) await browser.close().catch(() => {});
    if (server) await server.close().catch(() => {});
    await fs.rm(root, { recursive: true, force: true }).catch(() => {});
  }
}

process.exitCode = await run();
