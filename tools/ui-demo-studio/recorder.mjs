import { spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { createServer } from 'node:http';
import { readFile, rename, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { chromium } from 'playwright';
import { canonicalRoute, chooseTourAction, isDestructiveAction, isDistinctScene, mergeLinkFrontier, sceneSignature } from './tour-planner.mjs';

function args(argv) {
  const out = {};
  for (let i = 2; i < argv.length; i += 1) {
    if (!argv[i].startsWith('--')) continue;
    const key = argv[i].slice(2);
    const next = argv[i + 1];
    if (next === undefined || next.startsWith('--')) out[key] = 'true';
    else { out[key] = next; i += 1; }
  }
  return out;
}

function bool(value, fallback = true) {
  if (value === undefined || value === '') return fallback;
  return !['false', '0', 'no', 'off'].includes(String(value).toLowerCase());
}

function viewport(value) {
  const m = String(value || '1280x720').match(/^(\d+)x(\d+)$/i);
  return { width: m ? Number(m[1]) : 1280, height: m ? Number(m[2]) : 720 };
}

function journey(value) {
  const raw = String(value || '');
  if (raw === 'true') return [];
  return raw.split(/[>,\n]+/).map((x) => x.trim()).filter(Boolean).slice(0, 8);
}

function unsafe(label) {
  return isDestructiveAction(label);
}

function slug(value) {
  return String(value || 'scene').replace(/[^a-z0-9_-]+/gi, '-').replace(/^-+|-+$/g, '').slice(0, 45) || 'scene';
}

function html(value) {
  return String(value == null ? '' : value)
    .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;').replaceAll("'", '&#039;');
}

async function readJson(file) {
  return JSON.parse(await readFile(file, 'utf8'));
}

async function status(file, patch) {
  let old = {};
  try { old = await readJson(file); } catch {}
  const next = { ...old, ...patch, updated_at: new Date().toISOString() };
  await writeFile(file, JSON.stringify(next, null, 2), 'utf8');
}

async function browser(headless) {
  try { return await chromium.launch({ headless }); }
  catch (first) {
    try { return await chromium.launch({ headless, channel: 'chrome' }); }
    catch (second) {
      throw new Error('Could not launch Chromium. Run "npx playwright install chromium" or install Chrome. ' +
        String(first) + ' / ' + String(second));
    }
  }
}

async function warmBrowserTarget(browserInstance, targetUrl, vp, timeoutMs = 12000) {
  const context = await browserInstance.newContext({ viewport: vp, reducedMotion: 'no-preference' });
  const page = await context.newPage();
  const startedAt = Date.now();
  const deadline = startedAt + Math.max(2000, timeoutMs);
  try {
    const navigationBudget = timeoutWithin(deadline, { reserve: 1200, cap: 9000, min: 500 });
    if (!navigationBudget) throw new Error('Preflight deadline exhausted before navigation started.');
    await page.goto(targetUrl, { waitUntil: 'commit', timeout: navigationBudget });
    const visibleBudget = timeoutWithin(deadline, { reserve: 150, cap: 3000, min: 100 });
    if (visibleBudget) {
      await page.waitForFunction(() => {
        const body = document.body;
        return Boolean(body && ((body.innerText || '').trim().length >= 20 || document.querySelector('main,nav,form,button,a[href]')));
      }, { timeout: visibleBudget }).catch(() => undefined);
    }
    return {
      ok: true,
      title: await page.title().catch(() => ''),
      url: page.url(),
      elapsed_seconds: roundSeconds(Date.now() - startedAt)
    };
  } catch (error) {
    return {
      ok: false,
      error: String(error && error.message ? error.message : error).slice(0,500),
      url: page.url(),
      elapsed_seconds: roundSeconds(Date.now() - startedAt)
    };
  } finally {
    await page.evaluate(() => window.stop()).catch(() => undefined);
    await page.close({ runBeforeUnload: false }).catch(() => undefined);
    await context.close().catch(() => undefined);
  }
}

async function waitForVisibleUi(page, deadline) {
  const budget = timeoutWithin(deadline, { reserve: 250, cap: 5000, min: 100 });
  if (!budget) return;
  await page.waitForFunction(() => {
    const body = document.body;
    if (!body) return false;
    const text = (body.innerText || '').trim();
    const useful = document.querySelector('main,nav,form,button,a[href],[role="main"],[role="navigation"]');
    return text.length >= 20 || Boolean(useful);
  }, { timeout: budget }).catch(() => undefined);
}

async function overlay(page, label) {
  await page.evaluate((text) => {
    let dot = document.getElementById('__synapse_demo_cursor');
    if (!dot) {
      dot = document.createElement('div');
      dot.id = '__synapse_demo_cursor';
      Object.assign(dot.style, {
        position: 'fixed', left: '24px', top: '24px', width: '18px', height: '18px',
        borderRadius: '99px', background: '#7c3aed', border: '3px solid white',
        boxShadow: '0 4px 16px rgba(0,0,0,.35)', zIndex: '2147483647',
        pointerEvents: 'none', transition: 'left 420ms ease, top 420ms ease, transform 160ms ease'
      });
      document.documentElement.appendChild(dot);
    }
    let chip = document.getElementById('__synapse_demo_scene');
    if (!chip) {
      chip = document.createElement('div');
      chip.id = '__synapse_demo_scene';
      Object.assign(chip.style, {
        position: 'fixed', left: '22px', bottom: '22px', maxWidth: '72vw',
        padding: '10px 14px', borderRadius: '12px', color: '#fff',
        background: 'rgba(11,14,28,.88)', border: '1px solid rgba(255,255,255,.18)',
        boxShadow: '0 8px 28px rgba(0,0,0,.28)', zIndex: '2147483646',
        pointerEvents: 'none', font: '600 14px/1.25 system-ui,sans-serif'
      });
      document.documentElement.appendChild(chip);
    }
    chip.textContent = text || 'UI Demo';
  }, label);
}

function remaining(deadline) {
  return Math.max(0, deadline - Date.now());
}

function timeoutWithin(deadline, { reserve = 0, cap = 5000, min = 50 } = {}) {
  const budget = Math.min(cap, Math.max(0, remaining(deadline) - reserve));
  return budget >= min ? Math.floor(budget) : 0;
}

function roundSeconds(ms) {
  return Math.round((Math.max(0, ms) / 1000) * 100) / 100;
}

async function waitWithin(page, ms, deadline) {
  const budget = Math.min(ms, Math.max(0, remaining(deadline) - 40));
  if (budget > 0) await page.waitForTimeout(budget);
}

async function cursor(page, locator, deadline) {
  const timeout = Math.max(120, Math.min(700, remaining(deadline) - 300));
  if (timeout <= 120) return;
  const box = await locator.boundingBox({ timeout }).catch(() => null);
  if (!box) return;
  await page.evaluate(({ x, y }) => {
    const dot = document.getElementById('__synapse_demo_cursor');
    if (!dot) return;
    dot.style.left = String(Math.max(0, x - 9)) + 'px';
    dot.style.top = String(Math.max(0, y - 9)) + 'px';
  }, { x: box.x + box.width / 2, y: box.y + box.height / 2 });
  await waitWithin(page, 260, deadline);
  await page.evaluate(() => {
    const dot = document.getElementById('__synapse_demo_cursor');
    if (!dot) return;
    dot.style.transform = 'scale(.72)';
    setTimeout(() => { dot.style.transform = 'scale(1)'; }, 150);
  });
}

async function peek(page, deadline) {
  if (remaining(deadline) < 500) return;
  const can = await page.evaluate(() => document.documentElement.scrollHeight > innerHeight * 1.25).catch(() => false);
  if (!can) return;
  await page.evaluate(() => window.scrollTo({ top: Math.round(innerHeight * .48), behavior: 'smooth' }));
  await waitWithin(page, 300, deadline);
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'smooth' }));
  await waitWithin(page, 220, deadline);
}

async function audit(page) {
  return await page.evaluate(() => {
    const visible = (el) => {
      const s = getComputedStyle(el);
      const r = el.getBoundingClientRect();
      return s.display !== 'none' && s.visibility !== 'hidden' && Number(s.opacity || 1) > 0 && r.width > 0 && r.height > 0;
    };
    const name = (el) => {
      const id = el.id;
      const explicit = id ? document.querySelector('label[for="' + CSS.escape(id) + '"]') : null;
      const wrapped = el.closest('label');
      return (el.getAttribute('aria-label') || el.getAttribute('title') || el.getAttribute('alt') ||
        (explicit && explicit.textContent) || (wrapped && wrapped.textContent) || el.textContent ||
        el.getAttribute('value') || '').trim();
    };
    const all = Array.from(document.querySelectorAll('button,a[href],input:not([type="hidden"]),select,textarea,[role="button"],[role="link"]')).filter(visible);
    const inputs = all.filter((el) => ['INPUT','SELECT','TEXTAREA'].includes(el.tagName));
    const unnamed = all.filter((el) => !name(el));
    const unlabeled = inputs.filter((el) => !name(el) && !el.getAttribute('placeholder'));
    const small = all.filter((el) => {
      const r = el.getBoundingClientRect();
      return r.width < 36 || r.height < 36;
    });
    const noAlt = Array.from(document.querySelectorAll('img')).filter(visible).filter((x) => !x.hasAttribute('alt'));
    const ids = Array.from(document.querySelectorAll('[id]')).map((x) => x.id).filter(Boolean);
    const dupes = [...new Set(ids.filter((id, i) => ids.indexOf(id) !== i))];
    const hs = Array.from(document.querySelectorAll('h1,h2,h3,h4,h5,h6')).filter(visible).map((x) => Number(x.tagName.slice(1)));
    let jumps = 0;
    for (let i = 1; i < hs.length; i += 1) if (hs[i] - hs[i - 1] > 1) jumps += 1;
    return {
      title: document.title, url: location.href,
      horizontal_overflow_px: Math.max(0, document.documentElement.scrollWidth - innerWidth),
      unnamed_interactive_count: unnamed.length,
      unlabeled_input_count: unlabeled.length,
      small_target_count: small.length,
      missing_alt_count: noAlt.length,
      duplicate_id_count: dupes.length,
      heading_jump_count: jumps,
      samples: {
        unnamed: unnamed.slice(0,3).map((x) => x.outerHTML.slice(0,160)),
        unlabeled: unlabeled.slice(0,3).map((x) => x.outerHTML.slice(0,160)),
        small: small.slice(0,3).map((x) => name(x) || x.outerHTML.slice(0,100)),
        duplicate_ids: dupes.slice(0,6)
      }
    };
  });
}

function finding(map, code, severity, title, detail, evidence = [], occurrences = 1) {
  const old = map.get(code);
  if (!old) map.set(code, { code, severity, title, detail, evidence: evidence.slice(0,8), occurrences });
  else {
    old.occurrences += occurrences;
    for (const e of evidence) if (!old.evidence.includes(e) && old.evidence.length < 8) old.evidence.push(e);
  }
}

function auditFindings(map, a) {
  const base = (a.title || 'Untitled') + ' — ' + a.url;
  if (a.horizontal_overflow_px > 2) finding(map, 'layout.horizontal_overflow', 'high', 'Horizontal page overflow',
    'Content extends ' + a.horizontal_overflow_px + 'px past the viewport.', [base]);
  if (a.unlabeled_input_count) finding(map, 'a11y.unlabeled_input', 'high', 'Form controls without usable labels',
    String(a.unlabeled_input_count) + ' visible form controls have no useful label.', [base, ...a.samples.unlabeled], a.unlabeled_input_count);
  if (a.unnamed_interactive_count) finding(map, 'a11y.unnamed_interactive', 'medium', 'Interactive controls without accessible names',
    String(a.unnamed_interactive_count) + ' visible interactive controls have no detectable accessible name.', [base, ...a.samples.unnamed], a.unnamed_interactive_count);
  if (a.duplicate_id_count) finding(map, 'dom.duplicate_ids', 'medium', 'Duplicate DOM ids',
    String(a.duplicate_id_count) + ' duplicate id values can break labels, automation, and accessibility.', [base, ...a.samples.duplicate_ids], a.duplicate_id_count);
  if (a.small_target_count) finding(map, 'mobile.small_targets', 'low', 'Small interaction targets',
    String(a.small_target_count) + ' controls are under 36px in at least one dimension.', [base, ...a.samples.small], a.small_target_count);
  if (a.missing_alt_count) finding(map, 'a11y.missing_alt', 'low', 'Images missing alt attributes',
    String(a.missing_alt_count) + ' visible images have no alt attribute.', [base], a.missing_alt_count);
  if (a.heading_jump_count) finding(map, 'structure.heading_jumps', 'low', 'Heading levels skip',
    String(a.heading_jump_count) + ' heading transitions skip a level.', [base], a.heading_jump_count);
}

async function scene(page, dir, index, label, findings, scenes, deadline) {
  await overlay(page, label);
  await waitWithin(page, 120, deadline);
  const a = await audit(page);
  auditFindings(findings, a);
  const shot = path.join(dir, 'scene-' + String(index).padStart(2,'0') + '-' + slug(label) + '.png');
  let screenshot = shot;
  let screenshotError = null;
  const shotBudget = timeoutWithin(deadline, { reserve: 250, cap: 3500, min: 500 });
  if (!shotBudget) {
    screenshot = null;
    screenshotError = 'recording deadline left no bounded screenshot budget';
  } else {
    try {
      await page.screenshot({ path: shot, fullPage: false, animations: 'disabled', timeout: shotBudget });
    } catch (error) {
      screenshot = null;
      screenshotError = String(error?.message || error).slice(0, 500);
    }
  }
  if (screenshotError) finding(findings, 'evidence.screenshot_failed', 'low', 'Scene screenshot unavailable',
    'A scene was still audited and recorded on video, but its PNG evidence could not be captured within the bounded recording window.', [a.url, screenshotError]);
  scenes.push({ index, label, title: a.title, url: a.url, screenshot, screenshot_error: screenshotError, audit: a });
}

async function guided(page, label) {
  const escaped = label.replace(/[.*+?^$()|[\]\\]/g, '\\$&');
  const re = new RegExp(escaped, 'i');
  const candidates = [
    page.getByRole('link', { name: re }).first(),
    page.getByRole('button', { name: re }).first(),
    page.locator('a,button,[role="button"],[role="link"]').filter({ hasText: re }).first()
  ];
  for (const loc of candidates) {
    if (await loc.isVisible({ timeout: 650 }).catch(() => false)) return loc;
  }
  return null;
}

async function activate(page, locator, deadline) {
  const href = await locator.getAttribute('href').catch(() => null);
  const activationLabel = await locator.evaluate((el) => (el.getAttribute('aria-label') || el.getAttribute('title') || el.textContent || '').trim().replace(/\s+/g, ' ')).catch(() => '');
  if (unsafe(activationLabel + ' ' + (href || ''))) throw new Error('Refused potentially destructive demo action.');
  if (href) {
    let target;
    let current;
    try {
      target = new URL(href, page.url());
      current = new URL(page.url());
    } catch {
      throw new Error('Refused invalid navigation target.');
    }
    if (!/^https?:$/i.test(target.protocol) || target.origin !== current.origin || /^javascript:/i.test(target.href)) {
      throw new Error('Refused cross-origin or unsafe-protocol navigation.');
    }
    await page.goto(target.href, {
      waitUntil: 'commit',
      timeout: Math.max(700, Math.min(2200, remaining(deadline) - 700))
    });
    await waitForVisibleUi(page, deadline);
    return { kind: 'navigation', url: page.url() };
  }

  const control = await locator.evaluate((el) => ({
    type: el instanceof HTMLButtonElement ? el.type : (el.getAttribute('type') || ''),
    disabled: Boolean(el.disabled || el.getAttribute('aria-disabled') === 'true' || el.closest('[inert]')),
  })).catch(() => ({ type: '', disabled: false }));
  if (control.disabled) throw new Error('Refused disabled control.');
  if (control.type === 'submit') throw new Error('Refused form-submit control in demo journey.');

  const beforeUrl = page.url();
  await locator.click({ timeout: Math.max(500, Math.min(1200, remaining(deadline) - 700)), noWaitAfter: true });
  await waitWithin(page, 220, deadline);
  if (page.url() !== beforeUrl) await waitForVisibleUi(page, deadline);
  return { kind: 'click', url: page.url() };
}

async function tourSnapshot(page) {
  return await page.evaluate(() => {
    const visibleText = (selector, limit) => Array.from(document.querySelectorAll(selector)).filter((el) => {
      const style = getComputedStyle(el), rect = el.getBoundingClientRect();
      return style.display !== 'none' && style.visibility !== 'hidden' && Number(style.opacity || 1) > 0 && rect.width > 0 && rect.height > 0;
    }).map((el) => (el.getAttribute('aria-label') || el.textContent || '').trim().replace(/\s+/g, ' ')).filter(Boolean).slice(0, limit);
    return {
      url: location.href,
      headings: visibleText('h1,h2,h3', 6),
      landmarks: visibleText('main,[role="main"],nav,[role="navigation"],aside', 8),
      dialogs: visibleText('[role="dialog"],dialog[open]', 4),
    };
  });
}

async function autoCandidates(page) {
  return await page.evaluate(() => {
    const visible = (el) => {
      const style = getComputedStyle(el), rect = el.getBoundingClientRect();
      return style.display !== 'none' && style.visibility !== 'hidden' && Number(style.opacity || 1) > 0 && rect.width > 0 && rect.height > 0;
    };
    const region = (el) => {
      if (el.closest('main,[role="main"]')) return 'main';
      if (el.closest('nav,[role="navigation"]')) return 'nav';
      if (el.closest('aside')) return 'aside';
      if (el.closest('header')) return 'header';
      if (el.closest('footer')) return 'footer';
      return 'other';
    };
    const roleFor = (el) => {
      const explicit = (el.getAttribute('role') || '').toLowerCase();
      if (explicit) return explicit;
      if (el.tagName === 'A') return 'link';
      if (el.tagName === 'BUTTON') return 'button';
      return '';
    };
    return Array.from(document.querySelectorAll('a[href],button,[role="button"],[role="link"],[role="tab"]'))
      .filter(visible)
      .map((el, domOrder) => {
        const label = (el.getAttribute('aria-label') || el.getAttribute('title') || el.textContent || '').trim().replace(/\s+/g, ' ');
        const id = 'tour-' + domOrder;
        el.setAttribute('data-synapse-demo-candidate', id);
        const expanded = el.getAttribute('aria-expanded');
        const tag = el.tagName.toLowerCase();
        const buttonType = el instanceof HTMLButtonElement ? el.type : (el.getAttribute('type') || '');
        return {
          id,
          tag,
          role: roleFor(el),
          label,
          href: tag === 'a' ? el.href : (el.getAttribute('href') || ''),
          region: region(el),
          domOrder,
          sourceUrl: location.href,
          type: buttonType,
          submit: buttonType === 'submit',
          disabled: Boolean(el.disabled),
          ariaDisabled: el.getAttribute('aria-disabled') === 'true',
          inert: Boolean(el.closest('[inert]')),
          ariaControls: el.getAttribute('aria-controls') || '',
          ariaExpanded: expanded === 'true' ? true : expanded === 'false' ? false : null,
          download: el.hasAttribute('download'),
          externalTarget: el.getAttribute('target') === '_blank' || /\bexternal\b/i.test(el.getAttribute('rel') || ''),
        };
      })
      .filter((item) => item.label && item.label.length <= 120);
  });
}
function score(items) {
  const w = { critical: 22, high: 12, medium: 5, low: 2 };
  return Math.max(0, 100 - items.reduce((n, x) => n + (w[x.severity] || 2), 0));
}

function markdown(data) {
  const lines = [
    '# UI Demo Studio — ' + data.target_input, '',
    '**Target:** ' + data.target_url,
    '**UX health (heuristic):** ' + data.score + '/100',
    '**Video:** ' + (data.video_path || 'not produced'),
    '**Trace:** ' + (data.trace_path || 'not produced'), '',
    '## Demo scenes', ''
  ];
  for (const s of data.scenes) lines.push('- **' + s.label + '** — ' + s.url);
  lines.push('', '## Findings', '');
  if (!data.findings.length) lines.push('No heuristic UX/runtime findings were detected in the visited scenes.');
  for (const f of data.findings) {
    lines.push('### ' + f.severity.toUpperCase() + ' — ' + f.title, '', f.detail, '', 'Occurrences: ' + f.occurrences, '');
    for (const e of f.evidence.slice(0,5)) lines.push('- ' + e);
    lines.push('');
  }
  lines.push('## Runtime evidence', '',
    '- Console errors: ' + data.console_errors.length,
    '- Page errors: ' + data.page_errors.length,
    '- Failed requests: ' + data.request_failures.length,
    '- HTTP 4xx/5xx responses: ' + data.bad_responses.length, '',
    '## Suggested next pass', '',
    '1. Fix high-severity runtime/layout/accessibility findings first.',
    '2. Re-run this exact journey and compare the report + video.',
    '3. Watch once as a first-time user and remove dead time, unclear labels, repeated steps, and crowded screens.',
    '4. Run a second mobile viewport (390x844) before calling the UI done.', '');
  return lines.join('\n');
}

function report(data) {
  const video = data.video_path ? path.basename(data.video_path) : '';
  const cards = data.findings.length ? data.findings.map((f) =>
    '<article><b>' + html(f.severity.toUpperCase()) + ' — ' + html(f.title) + '</b><p>' +
    html(f.detail) + '</p><small>Occurrences: ' + f.occurrences + '</small></article>').join('') :
    '<article><b>No heuristic findings</b><p>The visited scenes did not trigger the current audit rules.</p></article>';
  const shots = data.scenes.map((s) => {
    const media = s.screenshot
      ? '<img src="./' + html(path.basename(s.screenshot)) + '" alt="' + html('Scene ' + (Number(s.index) + 1) + ': ' + s.label) + '">'
      : '<div class="missing-shot" role="note">Screenshot unavailable; video + DOM audit evidence preserved.</div>';
    return '<figure>' + media + '<figcaption><b>' + html(s.label) +
      '</b><br><small>' + html(s.url) + '</small></figcaption></figure>';
  }).join('');
  return '<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">' +
    '<title>UI Demo Studio</title><style>body{margin:0;background:#080b14;color:#eef2fb;font:14px system-ui}main{max-width:1120px;margin:auto;padding:28px}' +
    '.hero{display:grid;grid-template-columns:1.4fr .6fr;gap:16px}.card,article,figure{background:#111625;border:1px solid #273047;border-radius:16px;padding:16px}' +
    'video,img{width:100%;border-radius:12px}.missing-shot{min-height:150px;display:grid;place-items:center;border:1px dashed #44506a;border-radius:12px;color:#aab6cb;padding:16px;text-align:center}.score{font-size:54px;font-weight:800;color:#9a7cff}article{margin:10px 0;border-left:4px solid #7c3aed}p,small{color:#aab6cb}' +
    '.shots{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px}figure{margin:0;padding:10px}figcaption{padding:8px 2px 2px;word-break:break-word}' +
    '@media(max-width:700px){.hero{grid-template-columns:1fr}main{padding:12px}}</style><main><div class="hero"><section class="card"><h1>UI Demo Studio</h1>' +
    '<p>' + html(data.target_input) + '</p>' + (video ? '<video controls playsinline src="./' + html(video) + '"></video>' : '<p>Video not produced.</p>') +
    '</section><aside class="card"><div class="score">' + data.score + '<small>/100</small></div><p>Heuristic UX health</p><p>' + data.scenes.length +
    ' scenes · ' + data.findings.length + ' finding types</p></aside></div><h2>UX & bug findings</h2>' + cards +
    '<h2>Journey evidence</h2><div class="shots">' + shots + '</div></main>';
}

function mp4(webm, dir) {
  if (!webm) return null;
  const probe = spawnSync('ffmpeg', ['-version'], { stdio: 'ignore', timeout: 5000 });
  if (probe.status !== 0) return null;
  const out = path.join(dir, 'demo.mp4');
  const done = spawnSync('ffmpeg', ['-y','-i',webm,'-movflags','+faststart','-pix_fmt','yuv420p',out], { stdio: 'ignore', timeout: 120000 });
  return done.status === 0 && existsSync(out) ? out : null;
}

async function playableVideoDuration(browserInstance, file) {
  if (!file || !existsSync(file)) return null;
  const bytes = await readFile(file);
  const contentType = String(file).toLowerCase().endsWith('.mp4') ? 'video/mp4' : 'video/webm';
  const server = createServer((req, res) => {
    if (req.url !== '/video') { res.writeHead(404); res.end(); return; }
    res.writeHead(200, { 'Content-Type': contentType, 'Content-Length': bytes.length, 'Cache-Control': 'no-store' });
    res.end(bytes);
  });
  await new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(0, '127.0.0.1', resolve);
  });
  const address = server.address();
  const port = typeof address === 'object' && address ? address.port : null;
  let metadataPage = null;
  try {
    if (!port) return null;
    metadataPage = await browserInstance.newPage();
    const measured = await metadataPage.evaluate(async (src) => {
      const video = document.createElement('video');
      video.preload = 'metadata';
      video.src = src;
      document.body.appendChild(video);
      await new Promise((resolve, reject) => {
        video.onloadedmetadata = resolve;
        video.onerror = () => reject(new Error('Video metadata could not be loaded.'));
      });
      return video.duration;
    }, 'http://127.0.0.1:' + port + '/video');
    return Number.isFinite(measured) ? Math.round(measured * 100) / 100 : null;
  } finally {
    if (metadataPage) await metadataPage.close({ runBeforeUnload: false }).catch(() => undefined);
    await new Promise((resolve) => server.close(() => resolve()));
  }
}

const a = args(process.argv);
const dir = path.resolve(String(a['run-dir'] || '.'));
const statusPath = path.join(dir, 'status.json');
const runId = String(a['run-id'] || 'unknown');
const targetUrl = String(a.target || '');
const targetInput = String(a['target-input'] || targetUrl);
const duration = Math.max(8, Math.min(60, Number(a.duration) || 30));
const steps = journey(a.journey);
const vp = viewport(a.viewport);
const headless = bool(a.headless, true);
let started = null;

const consoleErrors = [], pageErrors = [], requestFailures = [], badResponses = [], scenes = [];
const autoTourStats = { attempts: 0, distinct_scenes: 0, no_change_actions: 0, safety_recoveries: 0 };
const findings = new Map();
let b = null, ctx = null, page = null, videoPath = null, tracePath = null;
let recordingMode = null;
let recordingElapsedSeconds = null;
let videoFinalizeSeconds = null;
let videoDurationSeconds = null;
let videoDurationDeltaSeconds = null;

await status(statusPath, { status: 'running', run_id: runId, target_input: targetInput, target_url: targetUrl,
  duration_seconds: duration, viewport: String(vp.width) + 'x' + String(vp.height), journey: steps, started_at: new Date().toISOString() });

try {
  await status(statusPath, { status: 'preflighting', message: 'Warming browser connection before recorded demo timing starts.' });
  b = await browser(headless);
  const preflight = await warmBrowserTarget(b, targetUrl, vp);

  // Prefer explicit screencast start/stop so context shutdown cannot append tail frames.
  // Recreate the context with legacy recordVideo only when this Playwright build lacks screencast support.
  ctx = await b.newContext({ viewport: vp, reducedMotion: 'no-preference' });
  await ctx.tracing.start({ screenshots: true, snapshots: true, sources: false });
  page = await ctx.newPage();
  videoPath = path.join(dir, 'demo.webm');
  try {
    if (!page.screencast || typeof page.screencast.start !== 'function' || typeof page.screencast.stop !== 'function') throw new Error('screencast unavailable');
    started = Date.now();
    await page.screencast.start({ path: videoPath, size: vp });
    recordingMode = 'screencast';
  } catch {
    try { await page.close({ runBeforeUnload: false }); } catch {}
    try { await ctx.tracing.stop().catch(() => undefined); } catch {}
    try { await ctx.close(); } catch {}
    ctx = await b.newContext({ viewport: vp, recordVideo: { dir, size: vp }, reducedMotion: 'no-preference' });
    await ctx.tracing.start({ screenshots: true, snapshots: true, sources: false });
    started = Date.now();
    page = await ctx.newPage();
    videoPath = null;
    recordingMode = 'recordVideo';
  }
  if (!Number.isFinite(started)) started = Date.now();
  const deadline = started + duration * 1000;
  page.setDefaultTimeout(1800);
  page.setDefaultNavigationTimeout(Math.max(3000, Math.min(10000, duration * 1000 - 1000)));
  await status(statusPath, { status: 'running', preflight_ok: Boolean(preflight?.ok), preflight_error: preflight?.ok ? null : (preflight?.error || 'warm-up did not complete'), preflight_elapsed_seconds: preflight?.elapsed_seconds ?? null, recording_started_at: new Date(started).toISOString(), recording_deadline_at: new Date(deadline).toISOString(), recording_mode: recordingMode, message: 'Recording timed walkthrough.' });
  page.on('console', (m) => { if (m.type() === 'error' && consoleErrors.length < 50) consoleErrors.push({ text: m.text().slice(0,800), url: page.url() }); });
  page.on('pageerror', (e) => { if (pageErrors.length < 50) pageErrors.push({ message: e.message.slice(0,900), url: page.url() }); });
  page.on('requestfailed', (r) => { if (requestFailures.length < 60) requestFailures.push({ method: r.method(), url: r.url(), failure: (r.failure() || {}).errorText || 'failed' }); });
  page.on('response', (r) => { if (r.status() >= 400 && badResponses.length < 80) badResponses.push({ status: r.status(), url: r.url() }); });

  const initialLoadBudget = timeoutWithin(deadline, { reserve: 2500, cap: 12000, min: 500 });
  if (!initialLoadBudget) throw new Error('Recording deadline exhausted before the initial page load could start.');
  await page.goto(targetUrl, { waitUntil: 'commit', timeout: initialLoadBudget });
  await waitForVisibleUi(page, deadline);
  await waitWithin(page, 260, deadline);
  await overlay(page, 'Opening view');
  await scene(page, dir, 0, 'Opening view', findings, scenes, deadline);
  await peek(page, deadline);

  if (steps.length) {
    let index = 1;
    for (const label of steps) {
      if (remaining(deadline) < 3200) break;
      if (unsafe(label)) {
        finding(findings, 'journey.unsafe_step_skipped', 'medium', 'Potentially destructive journey step skipped',
          "Skipped '" + label + "' because demos refuse destructive/payment/logout actions.", [page.url()]);
        continue;
      }
      const loc = await guided(page, label);
      if (!loc) {
        finding(findings, 'journey.step_missing', 'medium', 'Guided journey step not found',
          "Could not find a visible link/button matching '" + label + "'.", [page.url(), label]);
        continue;
      }
      try {
        await overlay(page, 'Next: ' + label);
        await cursor(page, loc, deadline);
        await activate(page, loc, deadline);
        await waitWithin(page, 260, deadline);
        await overlay(page, label);
        await peek(page, deadline);
        await scene(page, dir, index++, label, findings, scenes, deadline);
      } catch (e) {
        finding(findings, 'journey.step_failed', 'medium', 'Guided interaction failed',
          "The '" + label + "' control was found but could not be completed reliably.", [page.url(), String(e)]);
      }
    }
  } else {
    const visitedActions = new Set();
    const visitedRoutes = new Set();
    const visitedScenes = new Set();
    let frontier = [];
    const openingSnapshot = await tourSnapshot(page);
    visitedScenes.add(sceneSignature(openingSnapshot));
    const openingRoute = canonicalRoute(page.url(), page.url());
    if (openingRoute) visitedRoutes.add(openingRoute);

    const maxAutoScenes = Math.min(7, Math.max(2, Math.floor(duration / 4)));
    const maxAttempts = Math.max(maxAutoScenes * 3, 6);
    let index = 1;
    while (index <= maxAutoScenes && autoTourStats.attempts < maxAttempts) {
      if (remaining(deadline) < 2600) break;
      const currentUrl = page.url();
      const currentCandidates = await autoCandidates(page);
      frontier = mergeLinkFrontier(frontier, currentCandidates, currentUrl);
      const currentRoutes = new Set(currentCandidates.filter((item) => item.href).map((item) => canonicalRoute(item.href, currentUrl)).filter(Boolean));
      const fallbackLinks = frontier.filter((item) => !currentRoutes.has(canonicalRoute(item.href, currentUrl)));
      const choice = chooseTourAction([...currentCandidates, ...fallbackLinks], { currentUrl, visitedActions, visitedRoutes });
      if (!choice) break;

      autoTourStats.attempts += 1;
      visitedActions.add(choice.fingerprint);
      if (choice.route) visitedRoutes.add(choice.route);
      const beforeUrl = page.url();
      try {
        await overlay(page, 'Exploring: ' + choice.label);
        if (choice.kind === 'link') {
          const samePageControl = canonicalRoute(choice.sourceUrl || beforeUrl, beforeUrl) === canonicalRoute(beforeUrl, beforeUrl);
          if (samePageControl) {
            const loc = page.locator('[data-synapse-demo-candidate="' + choice.id + '"]').first();
            if (await loc.isVisible({ timeout: 300 }).catch(() => false)) await cursor(page, loc, deadline);
          }
          await page.goto(choice.href, { waitUntil: 'commit', timeout: Math.max(700, Math.min(2200, remaining(deadline) - 700)) });
          await waitForVisibleUi(page, deadline);
        } else {
          const loc = page.locator('[data-synapse-demo-candidate="' + choice.id + '"]').first();
          if (!(await loc.isVisible({ timeout: 350 }).catch(() => false))) {
            autoTourStats.no_change_actions += 1;
            continue;
          }
          await cursor(page, loc, deadline);
          await activate(page, loc, deadline);
        }

        let beforeOrigin = '';
        let afterOrigin = '';
        try { beforeOrigin = new URL(beforeUrl).origin; afterOrigin = new URL(page.url()).origin; } catch {}
        if (beforeOrigin && afterOrigin && beforeOrigin !== afterOrigin) {
          autoTourStats.safety_recoveries += 1;
          await page.goto(beforeUrl, { waitUntil: 'commit', timeout: Math.max(700, Math.min(2200, remaining(deadline) - 700)) }).catch(() => undefined);
          await waitForVisibleUi(page, deadline);
          continue;
        }

        await waitWithin(page, 180, deadline);
        const afterSnapshot = await tourSnapshot(page);
        const distinct = isDistinctScene(afterSnapshot, visitedScenes);
        if (!distinct.distinct) {
          autoTourStats.no_change_actions += 1;
          continue;
        }
        visitedScenes.add(distinct.signature);
        const finalRoute = canonicalRoute(page.url(), page.url());
        if (finalRoute) visitedRoutes.add(finalRoute);
        await overlay(page, choice.label);
        await peek(page, deadline);
        await scene(page, dir, index++, choice.label, findings, scenes, deadline);
        autoTourStats.distinct_scenes += 1;
      } catch {
        autoTourStats.no_change_actions += 1;
      }
    }
  }

  if (pageErrors.length) finding(findings, 'runtime.page_error', 'high', 'Unhandled page errors',
    'The browser reported unhandled page errors during the recorded journey.', pageErrors.slice(0,6).map((x) => x.url + ' — ' + x.message));
  if (consoleErrors.length) finding(findings, 'runtime.console_error', 'medium', 'Console errors',
    'Console errors appeared during the journey.', consoleErrors.slice(0,6).map((x) => x.url + ' — ' + x.text));
  if (requestFailures.length) finding(findings, 'network.request_failed', 'high', 'Network requests failed',
    'Requests failed at the browser/network layer.', requestFailures.slice(0,6).map((x) => x.method + ' ' + x.url + ' — ' + x.failure));
  const fives = badResponses.filter((x) => x.status >= 500);
  const fours = badResponses.filter((x) => x.status >= 400 && x.status < 500);
  if (fives.length) finding(findings, 'network.http_5xx', 'high', 'Server errors during journey',
    'The UI received HTTP 5xx responses.', fives.slice(0,6).map((x) => x.status + ' ' + x.url));
  if (fours.length) finding(findings, 'network.http_4xx', 'medium', 'HTTP 4xx responses during journey',
    'The UI requested resources/endpoints that returned 4xx.', fours.slice(0,6).map((x) => x.status + ' ' + x.url));

  const finalRemain = remaining(deadline);
  if (finalRemain > 80) {
    await overlay(page, 'Final result');
    await waitWithin(page, finalRemain, deadline);
  }

  const recordingStoppedAt = Date.now();
  recordingElapsedSeconds = roundSeconds(recordingStoppedAt - started);
  const finalizeStartedAt = Date.now();
  if (recordingMode === 'screencast') await page.screencast.stop();
  const vid = recordingMode === 'recordVideo' ? page.video() : null;
  await page.close({ runBeforeUnload: false });
  page = null;

  tracePath = path.join(dir, 'trace.zip');
  await ctx.tracing.stop({ path: tracePath }).catch(() => undefined);
  await ctx.close(); ctx = null;

  if (vid) {
    const raw = await vid.path();
    videoPath = path.join(dir, 'demo.webm');
    if (path.resolve(raw) !== path.resolve(videoPath)) {
      try { await rename(raw, videoPath); } catch { await vid.saveAs(videoPath); }
    }
  }
  videoFinalizeSeconds = roundSeconds(Date.now() - finalizeStartedAt);
  const converted = mp4(videoPath, dir);
  if (converted) videoPath = converted;
  videoDurationSeconds = await playableVideoDuration(b, videoPath).catch(() => null);
  videoDurationDeltaSeconds = Number.isFinite(videoDurationSeconds)
    ? Math.round((videoDurationSeconds - duration) * 100) / 100
    : null;
  await b.close(); b = null;

  const findingList = [...findings.values()];
  const data = {
    run_id: runId, target_input: targetInput, target_url: targetUrl, duration_seconds: duration, target_duration_seconds: duration,
    recording_mode: recordingMode, recording_elapsed_seconds: recordingElapsedSeconds, video_finalize_seconds: videoFinalizeSeconds,
    video_duration_seconds: videoDurationSeconds, video_duration_delta_seconds: videoDurationDeltaSeconds,
    viewport: String(vp.width) + 'x' + String(vp.height), journey_mode: steps.length ? 'guided' : 'automatic-safe-tour',
    journey: steps, auto_tour: steps.length ? null : autoTourStats, score: score(findingList), findings: findingList, scenes, console_errors: consoleErrors,
    page_errors: pageErrors, request_failures: requestFailures, bad_responses: badResponses,
    video_path: videoPath, trace_path: tracePath, completed_at: new Date().toISOString()
  };
  const auditPath = path.join(dir, 'ux-audit.json');
  const mdPath = path.join(dir, 'report.md');
  const reportPath = path.join(dir, 'report.html');
  await writeFile(auditPath, JSON.stringify(data, null, 2), 'utf8');
  await writeFile(mdPath, markdown(data), 'utf8');
  await writeFile(reportPath, report(data), 'utf8');
  await status(statusPath, { status: 'completed', completed_at: data.completed_at, score: data.score,
    finding_count: findingList.length, scene_count: scenes.length, target_duration_seconds: duration,
    recording_mode: recordingMode, recording_elapsed_seconds: recordingElapsedSeconds, video_finalize_seconds: videoFinalizeSeconds,
    video_duration_seconds: videoDurationSeconds, video_duration_delta_seconds: videoDurationDeltaSeconds,
    video_path: videoPath, trace_path: tracePath,
    audit_json: auditPath, report_markdown: mdPath, report_html: reportPath,
    message: 'Demo video and UX audit are ready. Use “Open latest report” in Synapse.' });
} catch (e) {
  try { if (page && recordingMode === 'screencast') await page.screencast.stop(); } catch {}
  try { if (page) await page.close({ runBeforeUnload: false }); } catch {}
  try { if (ctx) await ctx.tracing.stop().catch(() => undefined); } catch {}
  try { if (ctx) await ctx.close(); } catch {}
  try { if (b) await b.close(); } catch {}
  await status(statusPath, { status: 'error', failed_at: new Date().toISOString(),
    error: String(e && e.stack ? e.stack : e).slice(0,5000),
    message: 'UI Demo Studio run failed. Check the target/browser and re-run.' });
  process.exitCode = 1;
}
