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

function fail(message, detail = {}) { const error = new Error(message); error.detail = detail; throw error; }
async function freePort() {
  return await new Promise((resolve, reject) => {
    const server = net.createServer(); server.unref(); server.once('error', reject); server.listen(0, '127.0.0.1', () => {
      const a = server.address(); const port = typeof a === 'object' && a ? a.port : 0; server.close((e) => e ? reject(e) : resolve(port));
    });
  });
}
async function fixture(root) {
  await fs.mkdir(path.join(root, 'src'), { recursive: true });
  await fs.writeFile(path.join(root, 'index.html'), '<!doctype html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="icon" href="data:,"><title>UI Forge State E2E</title></head><body><div id="root"></div><script type="module" src="/src/main.jsx"></script></body></html>', 'utf8');
  await fs.writeFile(path.join(root, 'src/main.jsx'), "import React from 'react';\nimport { createRoot } from 'react-dom/client';\nimport App from './App.jsx';\nimport './styles.css';\ncreateRoot(document.getElementById('root')).render(<App />);\n", 'utf8');
  await fs.writeFile(path.join(root, 'src/App.jsx'), "import React from 'react';\nexport default function App(){return <main className=\"shell\"><h1>Interaction states</h1><button id=\"cta\" className=\"cta\">Hover me</button><button id=\"disabled\" className=\"cta\" disabled>Unavailable</button></main>}\n", 'utf8');
  await fs.writeFile(path.join(root, 'src/styles.css'), `:root{font-family:Inter,system-ui,sans-serif;background:#0b1016;color:#f5f7f9}*{box-sizing:border-box}body{margin:0;min-width:320px}.shell{min-height:100vh;display:grid;place-content:center;justify-items:start;gap:18px;padding:28px}.cta{min-height:48px;padding:0 22px;border:0;border-radius:12px;font:inherit;background-color:rgb(30,40,50);color:white;transform:none}.cta:hover{background-color:rgb(40,50,60);transform:translateY(-1px)}.cta:disabled{opacity:.5;cursor:not-allowed}.cta:focus-visible{outline:2px solid white;outline-offset:2px}`, 'utf8');
}
function applyStyle(root, request) {
  const spec = path.join(root, `state-${request.state || 'base'}.json`);
  return fs.writeFile(spec, `${JSON.stringify(request, null, 2)}\n`, 'utf8').then(() => {
    const cp = spawnSync(process.execPath, [CSS_EDITOR, root, spec], { cwd: REPO, encoding: 'utf8', timeout: 30_000, windowsHide: true });
    let payload; try { payload = JSON.parse(cp.stdout || '{}'); } catch { fail('state CSS editor did not emit JSON', { stdout: cp.stdout, stderr: cp.stderr }); }
    if (cp.status !== 0 || !payload.ok) fail('state CSS source commit failed', { payload, stderr: cp.stderr });
    return payload;
  });
}
async function run() {
  await fs.mkdir(RESULTS, { recursive: true });
  const root = await fs.mkdtemp(path.join(REPO, '.tmp-ui-forge-state-e2e-'));
  let server; let browser; let stage = 'setup'; const started = performance.now();
  try {
    stage = 'fixture'; await fixture(root); const port = await freePort();
    stage = 'vite'; server = await createServer({ root, logLevel: 'silent', plugins: [react({ babel: { plugins: [[uiForgeSourceTags, { root }]] } })], server: { host: '127.0.0.1', port, strictPort: true } }); await server.listen();
    stage = 'browser'; browser = await chromium.launch({ headless: true, timeout: 15_000 }); const page = await browser.newPage({ viewport: { width: 900, height: 700 } });
    const consoleErrors = []; const pageErrors = []; page.on('console', (m) => { if (m.type() === 'error') consoleErrors.push({ text: m.text(), location: m.location() }); }); page.on('pageerror', (e) => pageErrors.push(e.message));
    await page.goto(`http://127.0.0.1:${port}`, { waitUntil: 'domcontentloaded', timeout: 20_000 }); await page.locator('#disabled').waitFor({ state: 'visible', timeout: 10_000 }); await page.addScriptTag({ path: BRIDGE });

    const initial = await page.locator('#cta').evaluate((el) => ({ source: el.getAttribute('data-ui-forge-source'), id: el.getAttribute('data-ui-forge-id'), inlineStyle: el.getAttribute('style') }));
    if (!initial.source || !initial.id) fail('source identity missing', { initial });

    stage = 'hover-preview';
    const hoverPreview = await page.evaluate(() => {
      window.UIForge.select('#cta');
      const preview = window.UIForge.preview({ type: 'style_props', state: 'hover', properties: { 'background-color': 'rgb(250, 80, 10)', transform: 'translateY(-3px)' } });
      const node = document.querySelector('#cta'); const during = { background: getComputedStyle(node).backgroundColor, transform: getComputedStyle(node).transform, inlineStyle: node.getAttribute('style') };
      const commit = window.UIForge.styleCommitSpec(); const reverted = window.UIForge.revertPreview(); const after = { background: getComputedStyle(node).backgroundColor, transform: getComputedStyle(node).transform, inlineStyle: node.getAttribute('style') };
      return { preview, during, commit, reverted, after };
    });
    if (!hoverPreview.commit?.ok || hoverPreview.commit.style_request?.state !== 'hover' || hoverPreview.commit.preview_mode !== 'simulated-inline-state-design-preview') fail('hover state preview contract invalid', { hoverPreview });
    if (hoverPreview.during.background !== 'rgb(250, 80, 10)' || hoverPreview.after.inlineStyle !== initial.inlineStyle) fail('hover design preview/revert failed', { hoverPreview });
    const hoverCommit = await applyStyle(root, hoverPreview.commit.style_request);
    if (hoverCommit.selector !== '.cta:hover' || hoverCommit.state !== 'hover') fail('hover commit resolved wrong state owner', { hoverCommit });

    stage = 'real-hover-proof';
    await page.mouse.move(5, 5); await page.waitForTimeout(100);
    const baseAfterCommit = await page.locator('#cta').evaluate((el) => ({ background: getComputedStyle(el).backgroundColor, transform: getComputedStyle(el).transform, inlineStyle: el.getAttribute('style'), source: el.getAttribute('data-ui-forge-source'), id: el.getAttribute('data-ui-forge-id') }));
    if (baseAfterCommit.background !== 'rgb(30, 40, 50)' || baseAfterCommit.transform !== 'none') fail('base state changed after hover-only edit', { baseAfterCommit });
    await page.hover('#cta');
    await page.waitForFunction(() => getComputedStyle(document.querySelector('#cta')).backgroundColor === 'rgb(250, 80, 10)', null, { timeout: 10_000 });
    const realHover = await page.locator('#cta').evaluate((el) => ({ background: getComputedStyle(el).backgroundColor, transform: getComputedStyle(el).transform, inlineStyle: el.getAttribute('style') }));
    if (realHover.transform === 'none' || realHover.inlineStyle !== initial.inlineStyle) fail('real hover state did not receive committed state rule cleanly', { realHover });

    stage = 'disabled-preview';
    const disabledPreview = await page.evaluate(() => {
      window.UIForge.select('#disabled');
      const preview = window.UIForge.preview({ type: 'style_props', state: 'disabled', properties: { opacity: '.25' } });
      const node = document.querySelector('#disabled'); const during = { opacity: getComputedStyle(node).opacity, inlineStyle: node.getAttribute('style') };
      const commit = window.UIForge.styleCommitSpec(); window.UIForge.revertPreview(); const after = { opacity: getComputedStyle(node).opacity, inlineStyle: node.getAttribute('style') };
      return { preview, during, commit, after };
    });
    if (!disabledPreview.commit?.ok || disabledPreview.commit.style_request?.state !== 'disabled' || disabledPreview.during.opacity !== '0.25') fail('disabled preview contract failed', { disabledPreview });
    const disabledCommit = await applyStyle(root, disabledPreview.commit.style_request);
    if (disabledCommit.selector !== '.cta:disabled') fail('disabled commit resolved wrong owner', { disabledCommit });
    await page.waitForFunction(() => getComputedStyle(document.querySelector('#disabled')).opacity === '0.25', null, { timeout: 10_000 });
    const realDisabled = await page.locator('#disabled').evaluate((el) => ({ disabled: el.disabled, opacity: getComputedStyle(el).opacity, cursor: getComputedStyle(el).cursor, inlineStyle: el.getAttribute('style') }));
    if (!realDisabled.disabled || realDisabled.opacity !== '0.25' || realDisabled.cursor !== 'not-allowed' || realDisabled.inlineStyle !== null) fail('real disabled state proof failed', { realDisabled });

    stage = 'audit'; await page.mouse.move(5,5); await page.addScriptTag({ path: AUDIT }); const desktop = await page.evaluate(() => window.UIForgeAudit.run()); await page.setViewportSize({ width: 390, height: 844 }); const mobile = await page.evaluate(() => window.UIForgeAudit.run());
    for (const audit of [desktop,mobile]) for (const key of ['horizontal_overflow','missing_interactive_name_count','unlabeled_form_control_count','missing_image_alt_count','heading_level_jump_count']) { const value = audit.violations[key]; if (value === true || (typeof value === 'number' && value > 0)) fail(`audit failed: ${key}`, { audit }); }
    if (consoleErrors.length || pageErrors.length) fail('browser emitted errors', { consoleErrors, pageErrors });
    const identity = await page.locator('#cta').evaluate((el) => ({ source: el.getAttribute('data-ui-forge-source'), id: el.getAttribute('data-ui-forge-id') }));
    if (identity.source !== initial.source || identity.id !== initial.id) fail('source identity changed during state CSS HMR', { initial, identity });

    const result = { schema:'ui-forge-state-style-visual-e2e-v1', generated_at:new Date().toISOString(), overall_pass:true, duration_ms:Math.round((performance.now()-started)*1000)/1000, hover:{ preview_mode:hoverPreview.commit.preview_mode, source_commit:hoverCommit, base_after_commit:baseAfterCommit, real_state:realHover }, disabled:{ source_commit:disabledCommit, real_state:realDisabled }, identity_stable:true, browser:{ console_errors:consoleErrors, page_errors:pageErrors, desktop_violations:desktop.violations, mobile_violations:mobile.violations }, claims:{ simulated_preview_then_real_hover_proof:true, real_disabled_state_proof:true, pseudo_state_source_ownership_pass:true, not_a_full_ui_forge_or_lovable_claim:true } };
    await fs.writeFile(path.join(RESULTS,'state-style-visual-e2e-latest.json'), `${JSON.stringify(result,null,2)}\n`, 'utf8'); console.log(JSON.stringify(result,null,2)); return 0;
  } catch (error) {
    const result = { schema:'ui-forge-state-style-visual-e2e-v1', generated_at:new Date().toISOString(), overall_pass:false, stage, error:error.message, detail:error.detail || {}, duration_ms:Math.round((performance.now()-started)*1000)/1000 };
    await fs.writeFile(path.join(RESULTS,'state-style-visual-e2e-latest.json'), `${JSON.stringify(result,null,2)}\n`, 'utf8'); console.error(JSON.stringify(result,null,2)); return 1;
  } finally { if (browser) await browser.close().catch(()=>{}); if (server) await server.close().catch(()=>{}); await fs.rm(root,{recursive:true,force:true}).catch(()=>{}); }
}
process.exitCode = await run();
