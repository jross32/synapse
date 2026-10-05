import { spawn } from 'node:child_process';
import { createServer } from 'node:http';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';

const ROOT = process.cwd();
const TOOL = path.join(ROOT, 'tools', 'ui-demo-studio');
const DATA = path.join(ROOT, 'data', 'ui-demo-studio');
const RECORDER = path.join(TOOL, 'recorder.mjs');
const BENCH = path.join(TOOL, 'benchmark-runner.mjs');
const stamp = new Date().toISOString().replace(/[-:.]/g, '').replace('T', '-').replace('Z', '');
const suiteDir = path.join(DATA, `acceptance-${stamp}`);

const fixtures = {
  healthy: `<!doctype html><meta charset="utf-8"><title>Acceptance App</title><style>body{font-family:system-ui;margin:0;background:#101722;color:#f5f7fb}nav{display:flex;gap:12px;padding:18px}a,button{min-height:44px;padding:10px 16px;color:#fff;background:#26364a;border:0;border-radius:10px;text-decoration:none;display:inline-flex;align-items:center}main{padding:36px;max-width:760px}section{padding:24px;background:#172231;border-radius:16px}</style><nav><a href="/healthy/paper">Paper Lab</a><a href="/healthy/compare">Compare</a><a href="/healthy/how">How it works</a></nav><main><h1>Acceptance Dashboard</h1><p>A working application with several safe internal states.</p><section><h2>Overview</h2><p>Useful content.</p></section></main>`,
  paper: `<!doctype html><meta charset="utf-8"><title>Paper Lab · Acceptance App</title><nav><a href="/healthy">Dashboard</a><a href="/healthy/compare">Compare</a></nav><main><h1>Paper Lab</h1><button type="button" onclick="this.textContent='Ready'">Prepare</button></main>`,
  compare: `<!doctype html><meta charset="utf-8"><title>Compare · Acceptance App</title><nav><a href="/healthy">Dashboard</a><a href="/healthy/how">How it works</a></nav><main><h1>Compare</h1><p>Comparison workspace.</p></main>`,
  how: `<!doctype html><meta charset="utf-8"><title>How it works · Acceptance App</title><nav><a href="/healthy">Dashboard</a></nav><main><h1>How it works</h1><p>Explanation.</p></main>`,
  noInteraction: `<!doctype html><meta charset="utf-8"><title>Beautiful Inert App</title><style>body{font-family:system-ui;background:#111827;color:white;display:grid;place-items:center;min-height:100vh}.card{padding:48px;border-radius:24px;background:#1f2937;box-shadow:0 20px 60px #0008}</style><div class="card"><h1>Beautiful Dashboard</h1><p>Looks polished but cannot do anything.</p></div>`,
  disabled: `<!doctype html><meta charset="utf-8"><title>Disabled Controls</title><main><h1>Ready when you are</h1><button disabled>Continue</button><button aria-disabled="true">Open dashboard</button></main>`,
  focusBroken: `<!doctype html><meta charset="utf-8"><title>Focus Invisible</title><style>*:focus,*:focus-visible{outline:none!important;box-shadow:none!important}body{font-family:system-ui;padding:32px}a,button,input{margin:12px;padding:12px}</style><main><h1>Keyboard workspace</h1><a href="/focus-broken#details">Details</a><button type="button">Preview</button><input aria-label="Search"></main>`,
  mobileNavBroken: `<!doctype html><meta charset="utf-8"><title>Broken Mobile Nav</title><style>body{font-family:system-ui;margin:0}nav{display:flex;gap:18px;padding:18px}nav a{padding:10px}main{padding:32px}@media(max-width:500px){nav{display:none}}</style><nav><a href="#one">Overview</a><a href="#two">Reports</a><a href="#three">Settings</a></nav><main><h1>Workspace</h1><button type="button">Create report</button></main>`,
  trapped: `<!doctype html><meta charset="utf-8"><title>Trapped Modal</title><main><h1>Workspace</h1><div role="dialog" aria-modal="true"><h2>Finish setup</h2><p>This modal intentionally has no close path.</p><button type="button">Continue</button></div></main>`
};

function pageFor(url) {
  if (url === '/healthy' || url === '/healthy/') return fixtures.healthy;
  if (url === '/healthy/paper') return fixtures.paper;
  if (url === '/healthy/compare') return fixtures.compare;
  if (url === '/healthy/how') return fixtures.how;
  if (url === '/no-interaction') return fixtures.noInteraction;
  if (url === '/disabled-only') return fixtures.disabled;
  if (url === '/focus-broken') return fixtures.focusBroken;
  if (url === '/mobile-nav-broken') return fixtures.mobileNavBroken;
  if (url === '/trapped-modal') return fixtures.trapped;
  return null;
}

async function runNode(script, args, timeoutMs = 70000) {
  return await new Promise((resolve, reject) => {
    const child = spawn(process.execPath, [script, ...args], { cwd: ROOT, windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] });
    let stdout = '', stderr = '';
    child.stdout.on('data', (d) => { stdout += d.toString(); });
    child.stderr.on('data', (d) => { stderr += d.toString(); });
    const timer = setTimeout(() => {
      try { child.kill(); } catch {}
      reject(new Error(`Timed out running ${path.basename(script)} after ${timeoutMs}ms`));
    }, timeoutMs);
    child.on('error', reject);
    child.on('exit', (code) => {
      clearTimeout(timer);
      if (code === 0) resolve({ code, stdout, stderr });
      else reject(new Error(`${path.basename(script)} exited ${code}\n${stderr || stdout}`));
    });
  });
}

async function readJson(file) { return JSON.parse(await readFile(file, 'utf8')); }
function assert(condition, message) { if (!condition) throw new Error(message); }

async function executeCase(name, target, duration = 8) {
  const runDir = path.join(suiteDir, name);
  await mkdir(runDir, { recursive: true });
  const statusFile = path.join(runDir, 'status.json');
  const seed = {
    run_id: `acceptance-${name}-${stamp}`,
    status: 'queued', target_input: target, target_url: target,
    duration_seconds: duration, viewport: '1280x720', headless: true,
    journey: [], created_at: new Date().toISOString(), run_dir: runDir, status_file: statusFile
  };
  await writeFile(statusFile, JSON.stringify(seed, null, 2), 'utf8');
  await runNode(RECORDER, ['--run-dir', runDir, '--run-id', seed.run_id, '--target', target, '--target-input', target, '--duration', String(duration), '--viewport', '1280x720', '--headless', 'true'], Math.max(60000, duration * 4000 + 30000));
  await runNode(BENCH, ['--run-dir', runDir, '--run-id', seed.run_id, '--target', target, '--target-input', target, '--duration', String(duration), '--viewport', '1280x720', '--headless', 'true'], 70000);
  return {
    status: await readJson(statusFile),
    scorecard: await readJson(path.join(runDir, 'scorecard.json')),
    audit: await readJson(path.join(runDir, 'ux-audit.json')),
    runDir
  };
}

async function waitForDetachedStatus(statusFile, timeoutMs = 90000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try { const current = await readJson(statusFile); if (['completed','error','aborted'].includes(current.status)) return current; } catch {}
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error('Detached action did not reach a terminal status in time');
}

async function executeActionCase(target, duration = 8) {
  const token = (await readFile(path.join(ROOT, 'data', 'auth-token'), 'utf8')).trim();
  const body = { source: 'auto', fields: { target, duration, journey: '', viewport: '1280x720', headless: true } };
  const started = Date.now();
  const response = await fetch('http://127.0.0.1:7878/api/v1/tools/ui-demo-studio/actions/record', { method: 'POST', headers: { 'X-Synapse-Token': token, 'Content-Type': 'application/json' }, body: JSON.stringify(body), signal: AbortSignal.timeout(8000) });
  const launchMs = Date.now() - started;
  const text = await response.text();
  let payload; try { payload = JSON.parse(text); } catch { payload = { raw: text }; }
  if (!response.ok) throw new Error('Action launch HTTP ' + response.status + ': ' + JSON.stringify(payload));
  const output = payload?.state?.result?.output ?? payload?.result?.output ?? payload?.output;
  if (!output) throw new Error('Action response omitted worker receipt: ' + JSON.stringify(payload));
  let receipt; try { receipt = typeof output === 'string' ? JSON.parse(output.trim()) : output; } catch { throw new Error('Action worker receipt is not JSON: ' + String(output).slice(0,1000)); }
  if (!receipt?.status_file) throw new Error('Worker receipt omitted status_file');
  const finalStatus = await waitForDetachedStatus(receipt.status_file, 100000);
  return { launchMs, receipt, finalStatus };
}

const server = createServer((req, res) => {
  const body = pageFor(new URL(req.url || '/', 'http://fixture').pathname);
  if (!body) { res.writeHead(404, { 'content-type': 'text/plain' }); res.end('not found'); return; }
  res.writeHead(200, { 'content-type': 'text/html; charset=utf-8', 'cache-control': 'no-store' });
  res.end(body);
});
await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve); });
const address = server.address();
const port = typeof address === 'object' && address ? address.port : null;
if (!port) throw new Error('Fixture server failed to bind');
const base = `http://127.0.0.1:${port}`;
await mkdir(suiteDir, { recursive: true });

const results = [];
async function check(name, fn) {
  const started = Date.now();
  try {
    const detail = await fn();
    results.push({ name, ok: true, ms: Date.now() - started, ...detail });
  } catch (error) {
    results.push({ name, ok: false, ms: Date.now() - started, error: String(error?.stack || error) });
  }
}

try {
  await check('healthy-auto-tour-and-duration', async () => {
    const r = await executeCase('healthy', `${base}/healthy`, 8);
    const delta = Math.abs(Number(r.status.video_duration_delta_seconds));
    assert(r.status.status === 'completed', `healthy status=${r.status.status}`);
    assert((r.audit.scenes || []).length >= 2, `expected >=2 scenes, got ${(r.audit.scenes || []).length}`);
    assert(new Set((r.audit.scenes || []).map((x) => String(x.url).replace(/#.*$/, ''))).size >= 2, 'expected >=2 distinct routes');
    assert(!(r.audit.findings || []).some((f) => f.code === 'journey.auto_step_failed'), 'auto tour had a failed step');
    const timingLimit = r.audit.recording_mode === 'screencast' ? 1.5 : 2.5;
    assert(Number.isFinite(delta) && delta <= timingLimit, `video duration delta ${r.status.video_duration_delta_seconds}s exceeds ${timingLimit}s for ${r.audit.recording_mode || 'unknown'}`);
    return { overall: r.scorecard.overall_score, ux: r.scorecard.scores?.ux, scenes: r.audit.scenes.length, recording_mode: r.audit.recording_mode, video_duration_seconds: r.status.video_duration_seconds, target_duration_seconds: r.status.target_duration_seconds, video_duration_delta_seconds: r.status.video_duration_delta_seconds };
  });

  await check('beautiful-but-inert-hard-gate', async () => {
    const r = await executeCase('no-interaction', `${base}/no-interaction`, 8);
    assert(r.scorecard.scores?.ux === 0, `expected UX 0, got ${r.scorecard.scores?.ux}`);
    assert(r.scorecard.overall_score <= 39, `expected overall <=39, got ${r.scorecard.overall_score}`);
    assert((r.scorecard.gates || []).some((g) => g.id === 'ux.no_interaction'), 'missing ux.no_interaction gate');
    return { overall: r.scorecard.overall_score, ux: r.scorecard.scores?.ux, gates: r.scorecard.gates?.map((g) => g.id) };
  });

  await check('disabled-controls-hard-gate', async () => {
    const r = await executeCase('disabled', `${base}/disabled-only`, 8);
    assert(r.scorecard.scores?.ux === 0, `expected UX 0, got ${r.scorecard.scores?.ux}`);
    assert(r.scorecard.overall_score <= 39, `expected overall <=39, got ${r.scorecard.overall_score}`);
    return { overall: r.scorecard.overall_score, ux: r.scorecard.scores?.ux, gates: r.scorecard.gates?.map((g) => g.id) };
  });

  await check('keyboard-focus-visible-browser-proof', async () => {
    const r = await executeCase('focus-broken', `${base}/focus-broken`, 8);
    const focus = r.scorecard.metrics?.accessibility?.find((m) => m.id === 'a11y.keyboard_focus');
    assert(focus?.status === 'measured', `keyboard focus status=${focus?.status}`);
    assert(Number(focus?.score) <= 65, `expected invisible focus score <=65, got ${focus?.score}`);
    assert(Number(r.audit?.benchmark_raw?.keyboard?.visible_focus_count) === 0, 'expected browser probe to observe zero detectable focus indicators');
    return { overall: r.scorecard.overall_score, accessibility: r.scorecard.scores?.accessibility, keyboard_focus: focus?.score, visible_focus_count: r.audit?.benchmark_raw?.keyboard?.visible_focus_count };
  });

  await check('mobile-navigation-browser-proof', async () => {
    const r = await executeCase('mobile-nav-broken', `${base}/mobile-nav-broken`, 8);
    const nav = r.scorecard.metrics?.ui?.find((m) => m.id === 'ui.mobile_navigation');
    const responsive = r.scorecard.metrics?.ui?.find((m) => m.id === 'ui.responsive');
    assert(nav?.status === 'measured', `mobile nav status=${nav?.status}`);
    assert(Number(nav?.score) === 0, `expected broken mobile nav score 0, got ${nav?.score}`);
    assert(Number(responsive?.score) <= 80, `expected responsive score <=80, got ${responsive?.score}`);
    return { overall: r.scorecard.overall_score, ui: r.scorecard.scores?.ui, mobile_navigation: nav?.score, responsive: responsive?.score };
  });

  await check('trapped-modal-hard-gate', async () => {
    const r = await executeCase('trapped', `${base}/trapped-modal`, 8);
    assert(r.scorecard.scores?.ux <= 59, `expected UX <=59, got ${r.scorecard.scores?.ux}`);
    assert(r.scorecard.overall_score <= 59, `expected overall <=59, got ${r.scorecard.overall_score}`);
    assert((r.scorecard.gates || []).some((g) => g.id === 'ux.trapped_dialog'), 'missing ux.trapped_dialog gate');
    const keyboardDialog = r.scorecard.metrics?.ux?.find((m) => m.id === 'ux.dialog_keyboard');
    assert(keyboardDialog?.status === 'measured', `trapped modal keyboard metric status=${keyboardDialog?.status}`);
    assert(Number(keyboardDialog?.score) <= 55, `expected trapped modal keyboard score <=55, got ${keyboardDialog?.score}`);
    return { overall: r.scorecard.overall_score, ux: r.scorecard.scores?.ux, keyboard_dialog: keyboardDialog?.score, gates: r.scorecard.gates?.map((g) => g.id) };
  });

  await check('synapse-action-detached-launch', async () => {
    const r = await executeActionCase(`${base}/healthy`, 8);
    assert(r.launchMs <= 5000, `action launcher took ${r.launchMs}ms; expected <=5000ms`);
    assert(r.finalStatus.status === 'completed', `detached run ended ${r.finalStatus.status}`);
    assert(Number(r.finalStatus.overall_score) >= 1, 'completed action did not publish benchmark score');
    const actionDelta = Math.abs(Number(r.finalStatus.video_duration_delta_seconds));
    const actionLimit = r.finalStatus.recording_mode === 'screencast' ? 1.5 : 2.5;
    assert(Number.isFinite(actionDelta) && actionDelta <= actionLimit, `action video duration delta ${r.finalStatus.video_duration_delta_seconds}s exceeds ${actionLimit}s`);
    return { launch_ms: r.launchMs, run_id: r.receipt.run_id, final_status: r.finalStatus.status, overall: r.finalStatus.overall_score, recording_mode: r.finalStatus.recording_mode, video_duration_delta_seconds: r.finalStatus.video_duration_delta_seconds };
  });
} finally {
  try { server.closeIdleConnections?.(); } catch {}
  try { server.closeAllConnections?.(); } catch {}
  await Promise.race([
    new Promise((resolve) => server.close(() => resolve())),
    new Promise((resolve) => setTimeout(resolve, 1500))
  ]);
}

const summary = { suite: 'ui-demo-studio-acceptance-v3', created_at: new Date().toISOString(), suite_dir: suiteDir, passed: results.filter((x) => x.ok).length, failed: results.filter((x) => !x.ok).length, results };
await writeFile(path.join(suiteDir, 'acceptance-summary.json'), JSON.stringify(summary, null, 2), 'utf8');
console.log(JSON.stringify(summary, null, 2));
if (summary.failed) process.exitCode = 1;
