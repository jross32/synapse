#!/usr/bin/env node
import fs from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import net from 'node:net';
import { createServer } from 'vite';
import react from '@vitejs/plugin-react';
import { chromium } from 'playwright';

import uiForgeSourceTags from '../../templates/skills/ui-forge/scripts/babel_source_tags.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(HERE, '../..');
const BRIDGE = path.join(REPO_ROOT, 'templates/skills/ui-forge/scripts/visual_edit_bridge.js');
const AUDIT = path.join(REPO_ROOT, 'templates/skills/ui-forge/scripts/browser_audit.js');
const DIRECT_EDIT = path.join(REPO_ROOT, 'templates/skills/ui-forge/scripts/direct_ast_edit.mjs');
const RESULTS_DIR = path.join(HERE, 'results');

async function reserveFreePort() {
  return await new Promise((resolve, reject) => {
    const socket = net.createServer();
    socket.unref();
    socket.on('error', reject);
    socket.listen(0, '127.0.0.1', () => {
      const address = socket.address();
      const port = typeof address === 'object' && address ? address.port : 0;
      socket.close(error => error ? reject(error) : resolve(port));
    });
  });
}

function fail(message, detail = {}) {
  const error = new Error(message);
  error.detail = detail;
  throw error;
}

async function writeFixture(root) {
  await fs.mkdir(path.join(root, 'src'), { recursive: true });
  await fs.writeFile(path.join(root, 'index.html'), `<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 1 1%22></svg>" />
    <title>UI Forge E2E</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.jsx"></script>
  </body>
</html>
`, 'utf8');
  await fs.writeFile(path.join(root, 'src/main.jsx'), `import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App.jsx';
import './styles.css';

createRoot(document.getElementById('root')).render(<App />);
`, 'utf8');
  await fs.writeFile(path.join(root, 'src/App.jsx'), `import React from 'react';

export default function App() {
  return (
    <main className="shell">
      <p className="eyebrow">UI FORGE E2E</p>
      <h1>Browser to source, precisely.</h1>
      <button id="cta" className="cta"><span aria-hidden="true">+</span> Add item <kbd>N</kbd></button>
    </main>
  );
}
`, 'utf8');
  await fs.writeFile(path.join(root, 'src/styles.css'), `:root { font-family: Inter, ui-sans-serif, system-ui, sans-serif; background: #0b1016; color: #f5f7f9; }
* { box-sizing: border-box; }
body { margin: 0; min-width: 320px; }
.shell { min-height: 100vh; display: grid; place-content: center; justify-items: start; gap: 18px; padding: 32px; }
.eyebrow { margin: 0; font-size: 12px; letter-spacing: .18em; }
h1 { max-width: 620px; margin: 0; font-size: clamp(34px, 7vw, 72px); line-height: .98; }
.cta { min-height: 48px; padding: 0 22px; border: 0; border-radius: 12px; font: inherit; font-weight: 700; cursor: pointer; }
`, 'utf8');
}

async function run() {
  await fs.mkdir(RESULTS_DIR, { recursive: true });
  const root = await fs.mkdtemp(path.join(REPO_ROOT, '.tmp-ui-forge-e2e-'));
  let server;
  let browser;
  let stage = 'setup';
  const started = performance.now();
  try {
    stage = 'write-fixture';
    await writeFixture(root);

    stage = 'start-vite';
    const port = await reserveFreePort();
    server = await createServer({
      root,
      logLevel: 'silent',
      plugins: [react({ babel: { plugins: [[uiForgeSourceTags, { root }]] } })],
      server: { host: '127.0.0.1', port, strictPort: true },
    });
    await server.listen();
    const address = server.httpServer?.address();
    if (!address || typeof address === 'string') fail('Vite did not expose a TCP port');
    const url = `http://127.0.0.1:${address.port}`;

    stage = 'launch-browser';
    browser = await chromium.launch({ headless: true, timeout: 15_000 });
    const page = await browser.newPage({ viewport: { width: 900, height: 700 } });
    const consoleErrors = [];
    const pageErrors = [];
    page.on('console', msg => {
      if (msg.type() === 'error') consoleErrors.push({ text: msg.text(), location: msg.location() });
    });
    page.on('pageerror', error => pageErrors.push(error.message));

    stage = 'initial-navigation';
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 20_000 });
    await page.locator('#cta').waitFor({ state: 'visible', timeout: 10_000 });
    const initial = await page.locator('#cta').evaluate(el => ({
      text: el.textContent,
      source: el.getAttribute('data-ui-forge-source'),
      forgeId: el.getAttribute('data-ui-forge-id'),
      className: el.className,
    }));
    if (initial.text !== '+ Add item N') fail('fixture did not render expected initial text', { initial });
    if (!/^src\/App\.jsx:\d+:\d+$/.test(initial.source || '')) fail('compile-time source tag missing', { initial });
    if (!/^uif-/.test(initial.forgeId || '')) fail('stable UI Forge id missing', { initial });

    stage = 'preview';
    await page.addScriptTag({ path: BRIDGE });
    const preview = await page.evaluate(() => {
      const selection = window.UIForge.select('#cta');
      const previewResult = window.UIForge.preview({ type: 'set_text_segment', segment_index: 0, expected_text: 'Add item', value: 'Add listing' });
      const during = document.querySelector('#cta')?.textContent;
      const commit = window.UIForge.commitSpec();
      const reverted = window.UIForge.revertPreview();
      const after = document.querySelector('#cta')?.textContent;
      return { selection, previewResult, during, commit, reverted, after };
    });
    if (preview.during !== '+ Add listing N' || preview.after !== '+ Add item N') fail('preview/revert cycle failed', { preview });
    if (!preview.commit?.ok) fail('source-tagged preview was not commit-ready', { preview });
    if (preview.commit.source_edit?.source !== initial.source) fail('commit source drifted from selected source tag', { preview, initial });

    stage = 'commit-source';
    const specPath = path.join(root, 'commit-spec.json');
    await fs.writeFile(specPath, `${JSON.stringify(preview.commit.source_edit, null, 2)}\n`, 'utf8');
    const edit = spawnSync(process.execPath, [DIRECT_EDIT, root, specPath], {
      cwd: REPO_ROOT,
      encoding: 'utf8',
      timeout: 30_000,
    });
    if (edit.status !== 0) fail('direct AST commit failed', { stdout: edit.stdout, stderr: edit.stderr, status: edit.status });
    let editResult;
    try {
      editResult = JSON.parse(edit.stdout);
    } catch {
      fail('direct AST editor did not return JSON', { stdout: edit.stdout });
    }
    if (!editResult.ok || !editResult.syntax_reparse_passed) fail('direct AST edit safety gate failed', { editResult });

    stage = 'hmr-settle';
    await page.waitForTimeout(500);
    await page.waitForLoadState('domcontentloaded').catch(() => {});
    await page.waitForFunction(() => document.querySelector('#cta')?.textContent === '+ Add listing N', null, { timeout: 10_000 });

    stage = 'verify-committed-dom';
    const committed = await page.locator('#cta').evaluate(el => ({
      text: el.textContent,
      source: el.getAttribute('data-ui-forge-source'),
      forgeId: el.getAttribute('data-ui-forge-id'),
      className: el.className,
    }));
    if (committed.source !== initial.source || committed.forgeId !== initial.forgeId) {
      fail('source identity changed after HMR', { initial, committed });
    }

    stage = 'browser-audit';
    await page.addScriptTag({ path: AUDIT });
    const desktopAudit = await page.evaluate(() => window.UIForgeAudit.run());
    await page.setViewportSize({ width: 390, height: 844 });
    const mobileAudit = await page.evaluate(() => window.UIForgeAudit.run());
    const blockingAuditKeys = [
      'horizontal_overflow',
      'missing_interactive_name_count',
      'unlabeled_form_control_count',
      'missing_image_alt_count',
      'heading_level_jump_count',
    ];
    for (const [label, audit] of [['desktop', desktopAudit], ['mobile', mobileAudit]]) {
      for (const key of blockingAuditKeys) {
        const value = audit.violations[key];
        if (value === true || (typeof value === 'number' && value > 0)) fail(`${label} audit failed: ${key}`, { audit });
      }
    }
    if (consoleErrors.length || pageErrors.length) fail('browser emitted runtime errors', { consoleErrors, pageErrors });

    stage = 'source-verify';
    const sourceAfter = await fs.readFile(path.join(root, 'src/App.jsx'), 'utf8');
    if (!sourceAfter.includes('</span> Add listing <kbd>N</kbd></button>')) fail('source file did not persist committed text', { sourceAfter });
    if (sourceAfter.includes('</span> Add item <kbd>N</kbd></button>')) fail('old static source text remained after commit', { sourceAfter });

    const result = {
      schema: 'ui-forge-mixed-content-visual-e2e-v1',
      generated_at: new Date().toISOString(),
      overall_pass: true,
      duration_ms: Math.round((performance.now() - started) * 1000) / 1000,
      initial,
      preview: {
        during: preview.during,
        after_revert: preview.after,
        source_edit: preview.commit.source_edit,
      },
      direct_edit: editResult,
      committed,
      browser: {
        console_errors: consoleErrors,
        page_errors: pageErrors,
        desktop_violations: desktopAudit.violations,
        mobile_violations: mobileAudit.violations,
      },
      claims: {
        real_vite_compile_time_source_tag: true,
        reversible_browser_preview: true,
        exact_source_commit: true,
        hmr_preserved_source_identity: true,
        desktop_mobile_objective_audit_pass: true,
        not_a_full_ui_forge_or_lovable_claim: true,
      },
    };
    await fs.writeFile(path.join(RESULTS_DIR, 'mixed-content-visual-e2e-latest.json'), `${JSON.stringify(result, null, 2)}\n`, 'utf8');
    console.log(JSON.stringify(result, null, 2));
    return 0;
  } catch (error) {
    const result = {
      schema: 'ui-forge-mixed-content-visual-e2e-v1',
      generated_at: new Date().toISOString(),
      overall_pass: false,
      duration_ms: Math.round((performance.now() - started) * 1000) / 1000,
      error: error.message,
      stage,
      detail: error.detail || {},
    };
    await fs.mkdir(RESULTS_DIR, { recursive: true });
    await fs.writeFile(path.join(RESULTS_DIR, 'mixed-content-visual-e2e-latest.json'), `${JSON.stringify(result, null, 2)}\n`, 'utf8');
    console.error(JSON.stringify(result, null, 2));
    return 1;
  } finally {
    if (browser) await browser.close().catch(() => {});
    if (server) await server.close().catch(() => {});
    await fs.rm(root, { recursive: true, force: true }).catch(() => {});
  }
}

process.exitCode = await run();
