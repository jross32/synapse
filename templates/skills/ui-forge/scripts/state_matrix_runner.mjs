#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const AUDIT = path.join(HERE, 'browser_audit.js');
const SCHEMA = 'ui-forge-state-matrix-v1';
const DEFAULT_VIEWPORTS = [
  { name: 'desktop', width: 1280, height: 800 },
  { name: 'mobile', width: 390, height: 844 },
];
const SUPPORTED_ACTIONS = new Set(['click','fill','check','uncheck','hover','focus','press','wait','reload']);
const SUPPORTED_ASSERTIONS = new Set(['visible','hidden','text_equals','text_contains','value_equals','attribute_equals','enabled','disabled','checked','unchecked','count_equals','url_contains']);

function emit(payload, code = 0) { process.stdout.write(`${JSON.stringify(payload, null, 2)}\n`); process.exitCode = code; }
function readJson(file) { return JSON.parse(fs.readFileSync(path.resolve(file), 'utf8')); }
function validate(spec) {
  const errors = [];
  if (!spec || typeof spec !== 'object' || Array.isArray(spec)) return ['state matrix must be an object'];
  if (spec.schema !== SCHEMA) errors.push(`schema must be ${SCHEMA}`);
  if (!Array.isArray(spec.states) || !spec.states.length) errors.push('states must be a non-empty array');
  const ids = new Set();
  for (const state of spec.states || []) {
    if (!state || typeof state !== 'object') { errors.push('state entries must be objects'); continue; }
    const id = String(state.id || '').trim();
    if (!id) errors.push('every state needs an id');
    else if (ids.has(id)) errors.push(`duplicate state id: ${id}`);
    else ids.add(id);
    if (!Array.isArray(state.assertions) || !state.assertions.length) errors.push(`state ${id || '<unknown>'} needs at least one assertion`);
    for (const action of state.actions || []) if (!SUPPORTED_ACTIONS.has(String(action?.type || ''))) errors.push(`state ${id}: unsupported action ${action?.type || '<empty>'}`);
    for (const assertion of state.assertions || []) if (!SUPPORTED_ASSERTIONS.has(String(assertion?.type || ''))) errors.push(`state ${id}: unsupported assertion ${assertion?.type || '<empty>'}`);
    for (const route of state.routes || []) {
      if (!route?.url_pattern) errors.push(`state ${id}: route needs url_pattern`);
      if (route?.delay_ms != null && (!Number.isFinite(Number(route.delay_ms)) || Number(route.delay_ms) < 0 || Number(route.delay_ms) > 30_000)) errors.push(`state ${id}: invalid route delay_ms`);
    }
  }
  if (Array.isArray(spec.required_states)) for (const id of spec.required_states) if (!ids.has(String(id))) errors.push(`required state missing from matrix: ${id}`);
  const viewports = spec.viewports || DEFAULT_VIEWPORTS;
  if (!Array.isArray(viewports) || !viewports.length) errors.push('viewports must be a non-empty array');
  else for (const viewport of viewports) if (!viewport?.name || Number(viewport.width) < 200 || Number(viewport.height) < 200) errors.push('every viewport needs name and dimensions >=200');
  return errors;
}
function absolutize(baseUrl, state) {
  const raw = state.url || state.path || '/';
  try { return new URL(raw, baseUrl).toString(); } catch { throw new Error(`invalid state URL/path: ${raw}`); }
}
async function installRoutes(page, routes) {
  for (const route of routes || []) {
    const pattern = String(route.url_pattern);
    let callIndex = 0;
    await page.route(pattern, async (handler) => {
      const sequence = Array.isArray(route.sequence) && route.sequence.length ? route.sequence : null;
      const response = sequence ? { ...route, ...sequence[Math.min(callIndex, sequence.length - 1)] } : route;
      callIndex += 1;
      if (response.delay_ms) await new Promise((resolve) => setTimeout(resolve, Number(response.delay_ms)));
      if (response.abort) { await handler.abort(String(response.abort)); return; }
      const body = typeof response.body === 'string' ? response.body : JSON.stringify(response.body ?? null);
      await handler.fulfill({
        status: Number(response.status || 200),
        contentType: response.content_type || 'application/json',
        body,
        headers: response.headers || {},
      });
    });
  }
}
async function runAction(page, action) {
  const type = String(action.type || '');
  if (type === 'wait') {
    if (action.selector) await page.locator(action.selector).waitFor({ state: action.state || 'visible', timeout: Number(action.timeout_ms || 5_000) });
    else await page.waitForTimeout(Number(action.ms || 100));
    return;
  }
  if (type === 'reload') { await page.reload({ waitUntil: 'domcontentloaded', timeout: Number(action.timeout_ms || 15_000) }); return; }
  if (type === 'press') { await page.keyboard.press(String(action.key || '')); return; }
  const locator = page.locator(String(action.selector || ''));
  if (type === 'click') await locator.click({ timeout: Number(action.timeout_ms || 5_000) });
  else if (type === 'fill') await locator.fill(String(action.value ?? ''), { timeout: Number(action.timeout_ms || 5_000) });
  else if (type === 'check') await locator.check({ timeout: Number(action.timeout_ms || 5_000) });
  else if (type === 'uncheck') await locator.uncheck({ timeout: Number(action.timeout_ms || 5_000) });
  else if (type === 'hover') await locator.hover({ timeout: Number(action.timeout_ms || 5_000) });
  else if (type === 'focus') await locator.focus({ timeout: Number(action.timeout_ms || 5_000) });
}
async function evaluateAssertion(page, assertion) {
  const type = String(assertion.type || '');
  const selector = assertion.selector == null ? null : String(assertion.selector);
  const locator = selector ? page.locator(selector) : null;
  try {
    let actual;
    let passed = false;
    if (type === 'visible') { actual = await locator.isVisible(); passed = actual === true; }
    else if (type === 'hidden') { actual = await locator.isHidden(); passed = actual === true; }
    else if (type === 'text_equals') { actual = await locator.textContent(); passed = String(actual ?? '').trim() === String(assertion.value ?? ''); }
    else if (type === 'text_contains') { actual = await locator.textContent(); passed = String(actual ?? '').includes(String(assertion.value ?? '')); }
    else if (type === 'value_equals') { actual = await locator.inputValue(); passed = actual === String(assertion.value ?? ''); }
    else if (type === 'attribute_equals') { actual = await locator.getAttribute(String(assertion.name || '')); passed = actual === (assertion.value == null ? null : String(assertion.value)); }
    else if (type === 'enabled') { actual = await locator.isEnabled(); passed = actual === true; }
    else if (type === 'disabled') { actual = await locator.isDisabled(); passed = actual === true; }
    else if (type === 'checked') { actual = await locator.isChecked(); passed = actual === true; }
    else if (type === 'unchecked') { actual = await locator.isChecked(); passed = actual === false; }
    else if (type === 'count_equals') { actual = await locator.count(); passed = actual === Number(assertion.value); }
    else if (type === 'url_contains') { actual = page.url(); passed = actual.includes(String(assertion.value || '')); }
    return { ...assertion, passed, actual };
  } catch (error) {
    return { ...assertion, passed: false, error: error.message };
  }
}
function auditBlockers(violations) {
  const blockers = [];
  for (const key of ['horizontal_overflow','missing_interactive_name_count','unlabeled_form_control_count','missing_image_alt_count','heading_level_jump_count']) {
    const value = violations?.[key];
    if (value === true || (typeof value === 'number' && value > 0)) blockers.push({ key, value });
  }
  return blockers;
}
function allowedConsole(message, patterns) {
  return (patterns || []).some((pattern) => {
    try { return new RegExp(String(pattern)).test(message); } catch { return false; }
  });
}
function globPatternToRegExp(pattern) {
  const raw = String(pattern || '');
  const escaped = raw.replace(/[.+^${}()|[\]\\]/g, '\\$&').replace(/\*\*/g, '§§DOUBLESTAR§§').replace(/\*/g, '[^/]*').replace(/§§DOUBLESTAR§§/g, '.*');
  try { return new RegExp(`^${escaped}$`); } catch { return null; }
}
function routeDeclaresFailure(route) {
  if (route?.abort) return true;
  if (Number(route?.status || 200) >= 400) return true;
  return Array.isArray(route?.sequence) && route.sequence.some((item) => item?.abort || Number(item?.status || 200) >= 400);
}
function expectedFailureConsole(message, location, routes) {
  if (!String(message || '').includes('Failed to load resource')) return false;
  const url = String(location?.url || '');
  if (!url) return false;
  return (routes || []).some((route) => {
    if (!routeDeclaresFailure(route)) return false;
    const regex = globPatternToRegExp(route.url_pattern);
    return regex ? regex.test(url) : false;
  });
}
async function runCase(browser, spec, state, viewport, baseUrl, screenshotRoot) {
  const context = await browser.newContext({ viewport: { width: Number(viewport.width), height: Number(viewport.height) } });
  const page = await context.newPage();
  const consoleErrors = [];
  const expectedFailureConsoleErrors = [];
  const pageErrors = [];
  page.on('console', (msg) => {
    if (msg.type() !== 'error') return;
    const location = msg.location();
    const entry = { text: msg.text(), location };
    if (allowedConsole(msg.text(), state.allow_console_error_patterns || spec.allow_console_error_patterns)) return;
    if (expectedFailureConsole(msg.text(), location, state.routes)) { expectedFailureConsoleErrors.push(entry); return; }
    consoleErrors.push(entry);
  });
  page.on('pageerror', (error) => pageErrors.push(error.message));
  let stage = 'routes';
  try {
    await installRoutes(page, state.routes);
    stage = 'navigate';
    const url = absolutize(baseUrl, state);
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: Number(state.navigation_timeout_ms || spec.navigation_timeout_ms || 20_000) });
    stage = 'actions';
    for (const action of state.actions || []) await runAction(page, action);
    if (state.settle_ms) await page.waitForTimeout(Number(state.settle_ms));
    stage = 'assertions';
    const assertions = [];
    for (const assertion of state.assertions) assertions.push(await evaluateAssertion(page, assertion));
    stage = 'audit';
    await page.addScriptTag({ path: AUDIT });
    const audit = await page.evaluate(() => window.UIForgeAudit.run());
    const blockers = state.skip_objective_audit ? [] : auditBlockers(audit.violations);
    let screenshot = null;
    if (screenshotRoot) {
      fs.mkdirSync(screenshotRoot, { recursive: true });
      const filename = `${state.id}-${viewport.name}.png`.replace(/[^A-Za-z0-9_.-]+/g, '-');
      screenshot = path.join(screenshotRoot, filename);
      await page.screenshot({ path: screenshot, fullPage: Boolean(state.full_page_screenshot) });
    }
    const passed = assertions.every((item) => item.passed) && blockers.length === 0 && consoleErrors.length === 0 && pageErrors.length === 0;
    return { state: state.id, viewport: viewport.name, passed, url: page.url(), assertions, objective_audit: audit.violations, audit_blockers: blockers, expected_failure_console_errors: expectedFailureConsoleErrors, console_errors: consoleErrors, page_errors: pageErrors, screenshot };
  } catch (error) {
    return { state: state.id, viewport: viewport.name, passed: false, stage, error: error.message, expected_failure_console_errors: expectedFailureConsoleErrors, console_errors: consoleErrors, page_errors: pageErrors };
  } finally {
    await context.close().catch(() => {});
  }
}
async function main() {
  const args = process.argv.slice(2);
  if (!args.length) { emit({ ok: false, error: 'usage: state_matrix_runner.mjs <matrix.json> [--base-url URL] [--output result.json] [--screenshots DIR]' }, 2); return; }
  let spec;
  try { spec = readJson(args[0]); } catch (error) { emit({ ok: false, error: `invalid matrix JSON: ${error.message}` }, 2); return; }
  const errors = validate(spec);
  if (errors.length) { emit({ ok: false, error: 'invalid state matrix', errors }, 2); return; }
  const argValue = (name) => { const i = args.indexOf(name); return i >= 0 ? args[i + 1] : null; };
  const baseUrl = argValue('--base-url') || spec.base_url;
  if (!baseUrl) { emit({ ok: false, error: 'base_url is required in spec or --base-url' }, 2); return; }
  const output = argValue('--output');
  const screenshotRoot = argValue('--screenshots') || spec.screenshots_dir || null;
  const viewports = spec.viewports || DEFAULT_VIEWPORTS;
  const started = performance.now();
  let browser;
  try {
    browser = await chromium.launch({ headless: true, timeout: 15_000 });
    const cases = [];
    for (const state of spec.states) for (const viewport of viewports) cases.push(await runCase(browser, spec, state, viewport, baseUrl, screenshotRoot));
    const stateSummary = spec.states.map((state) => {
      const matches = cases.filter((item) => item.state === state.id);
      return { id: state.id, passed: matches.length === viewports.length && matches.every((item) => item.passed), viewport_passes: matches.filter((item) => item.passed).length, viewport_total: matches.length };
    });
    const required = spec.required_states || spec.states.map((state) => state.id);
    const requiredPass = required.every((id) => stateSummary.find((item) => item.id === id)?.passed === true);
    const result = { ok: requiredPass, schema: 'ui-forge-state-matrix-result-v1', generated_at: new Date().toISOString(), duration_ms: Math.round((performance.now() - started) * 1000) / 1000, base_url: baseUrl, required_states: required, state_summary: stateSummary, cases, overall_pass: requiredPass };
    if (output) { fs.mkdirSync(path.dirname(path.resolve(output)), { recursive: true }); fs.writeFileSync(path.resolve(output), `${JSON.stringify(result, null, 2)}\n`, 'utf8'); }
    emit(result, requiredPass ? 0 : 1);
  } catch (error) {
    emit({ ok: false, schema: 'ui-forge-state-matrix-result-v1', overall_pass: false, error: error.message }, 1);
  } finally { if (browser) await browser.close().catch(() => {}); }
}
await main();
