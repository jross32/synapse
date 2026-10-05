#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const postcss = require('postcss');
const SKIP_DIRS = new Set(['node_modules','.git','.synapse','dist','build','coverage','.next','.nuxt']);
const SCHEMA = 'ui-forge-theme-capsule-v1';

function emit(payload, code = 0) { process.stdout.write(`${JSON.stringify(payload, null, 2)}\n`); process.exitCode = code; }
function cssFiles(root) {
  const out = [];
  function walk(dir) {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      if (entry.isDirectory()) { if (!SKIP_DIRS.has(entry.name)) walk(path.join(dir, entry.name)); continue; }
      if (entry.isFile() && /\.css$/i.test(entry.name)) {
        const file = path.join(dir, entry.name); if (fs.statSync(file).size <= 1_000_000) out.push(file);
      }
    }
  }
  walk(root); return out.sort();
}
function category(token) {
  const name = token.toLowerCase();
  if (/(color|bg|background|surface|text|muted|accent|success|warning|danger|focus)/.test(name)) return 'color';
  if (/(font|type|line-height|letter)/.test(name)) return 'typography';
  if (/(space|gap|spacing|padding|margin)/.test(name)) return 'spacing';
  if (/(radius|rounded)/.test(name)) return 'radius';
  if (/(shadow|elevation)/.test(name)) return 'shadow';
  if (/(duration|ease|motion|transition)/.test(name)) return 'motion';
  return 'other';
}
function parseFile(file) {
  const source = fs.readFileSync(file, 'utf8');
  return { source, ast: postcss.parse(source, { from: file }) };
}
function tokenOccurrences(root) {
  const found = new Map();
  for (const file of cssFiles(root)) {
    const parsed = parseFile(file);
    parsed.ast.walkRules((rule) => {
      const selector = String(rule.selector || '');
      if (!selector.split(',').some((part) => part.trim() === ':root' || part.trim() === 'html')) return;
      rule.walkDecls((decl) => {
        if (!decl.prop.startsWith('--')) return;
        const item = { file, relative: path.relative(root, file).replace(/\\/g,'/'), selector: rule.selector, line: decl.source?.start?.line || 0, value: decl.value, decl };
        if (!found.has(decl.prop)) found.set(decl.prop, []);
        found.get(decl.prop).push(item);
      });
    });
  }
  return found;
}
function validateTheme(theme) {
  const errors = [];
  if (!theme || typeof theme !== 'object' || Array.isArray(theme)) errors.push('theme must be an object');
  if (theme?.schema !== SCHEMA) errors.push(`theme.schema must be ${SCHEMA}`);
  if (!theme?.tokens || typeof theme.tokens !== 'object' || Array.isArray(theme.tokens)) errors.push('theme.tokens must be an object');
  else {
    for (const [name, value] of Object.entries(theme.tokens)) {
      if (!/^--[A-Za-z0-9_-]+$/.test(name)) errors.push(`invalid CSS custom property: ${name}`);
      if (typeof value !== 'string' || !value.trim()) errors.push(`theme token value must be a non-empty string: ${name}`);
      if (typeof value === 'string' && /[{};]/.test(value)) errors.push(`theme token contains structural CSS syntax: ${name}`);
    }
  }
  return errors;
}
function loadTheme(file) { return JSON.parse(fs.readFileSync(path.resolve(file), 'utf8')); }
function extract(root, output, name) {
  const occurrences = tokenOccurrences(root);
  const tokens = {};
  const conflicts = [];
  const provenance = {};
  for (const [token, items] of [...occurrences.entries()].sort()) {
    const values = [...new Set(items.map((item) => item.value))];
    if (values.length > 1) { conflicts.push({ token, values, occurrences: items.map(({relative,selector,line,value}) => ({file:relative,selector,line,value})) }); continue; }
    tokens[token] = values[0];
    provenance[token] = items.map(({relative,selector,line}) => ({ file: relative, selector, line }));
  }
  const categories = {};
  for (const token of Object.keys(tokens)) { const c = category(token); (categories[c] ||= []).push(token); }
  const theme = { schema: SCHEMA, name: name || path.basename(root), extracted_at: new Date().toISOString(), source_project: path.resolve(root), tokens, categories, provenance };
  if (conflicts.length) {
    emit({ ok: false, error: 'conflicting root theme token definitions; extraction refused', conflicts, partial_theme: theme }, 1); return;
  }
  if (!Object.keys(tokens).length) { emit({ ok: false, error: 'no :root/html CSS custom properties found' }, 1); return; }
  fs.mkdirSync(path.dirname(path.resolve(output)), { recursive: true });
  fs.writeFileSync(path.resolve(output), `${JSON.stringify(theme, null, 2)}\n`, 'utf8');
  emit({ ok: true, command: 'extract', schema: SCHEMA, output: path.resolve(output), token_count: Object.keys(tokens).length, categories, theme });
}
function apply(root, themeFile, dryRun, allowPartial) {
  const theme = loadTheme(themeFile);
  const errors = validateTheme(theme);
  if (errors.length) { emit({ ok: false, error: 'invalid theme capsule', errors }, 2); return; }
  const occurrences = tokenOccurrences(root);
  const missing = []; const ambiguous = []; const plans = [];
  for (const [token, value] of Object.entries(theme.tokens)) {
    const items = occurrences.get(token) || [];
    if (!items.length) { missing.push(token); continue; }
    if (items.length !== 1) { ambiguous.push({ token, occurrences: items.map(({relative,selector,line,value:v}) => ({file:relative,selector,line,value:v})) }); continue; }
    plans.push({ token, value, item: items[0] });
  }
  if (ambiguous.length || (missing.length && !allowPartial)) {
    emit({ ok: false, error: ambiguous.length ? 'theme token ownership is ambiguous' : 'target project is missing theme tokens; use --allow-partial only when partial application is intentional', missing, ambiguous, planned_count: plans.length }, 1); return;
  }
  if (!plans.length) { emit({ ok: false, error: 'no theme tokens can be applied to target project', missing }, 1); return; }

  const files = new Map();
  for (const plan of plans) {
    const file = plan.item.file;
    if (!files.has(file)) files.set(file, parseFile(file));
  }
  const changes = [];
  for (const plan of plans) {
    const parsed = files.get(plan.item.file);
    let target = null;
    parsed.ast.walkRules((rule) => {
      if (target || rule.selector !== plan.item.selector) return;
      rule.walkDecls(plan.token, (decl) => { if (!target && (decl.source?.start?.line || 0) === plan.item.line) target = decl; });
    });
    if (!target) { emit({ ok: false, error: `theme token moved during planning: ${plan.token}` }, 1); return; }
    changes.push({ token: plan.token, file: plan.item.relative, before: target.value, after: plan.value });
    target.value = plan.value;
  }
  const rendered = new Map();
  try {
    for (const [file, parsed] of files) { const text = parsed.ast.toString(); postcss.parse(text, { from: file }); rendered.set(file, text); }
  } catch (error) { emit({ ok: false, error: `theme application failed CSS reparse: ${error.message}` }, 1); return; }
  if (!dryRun) {
    const backups = new Map([...files.keys()].map((file) => [file, fs.readFileSync(file, 'utf8')]));
    try { for (const [file, text] of rendered) fs.writeFileSync(file, text, 'utf8'); }
    catch (error) { for (const [file, text] of backups) fs.writeFileSync(file, text, 'utf8'); emit({ ok: false, error: 'theme write failed; every touched stylesheet was restored', rolled_back: true, detail: error.message }, 1); return; }
  }
  emit({ ok: true, command: 'apply', schema: SCHEMA, dry_run: dryRun, atomic: true, allow_partial: allowPartial, applied_count: changes.length, missing, changes, files: [...files.keys()].map((file) => path.relative(root,file).replace(/\\/g,'/')), verification_required: ['rerender target project','run desktop/mobile UI Forge browser audit','verify contrast/brand semantics','inspect design-system drift'] });
}
function main() {
  const args = process.argv.slice(2); const command = args[0];
  try {
    if (command === 'extract') { if (args.length < 3) throw new Error('usage: theme_capsule.mjs extract <project-root> <output-json> [--name <name>]'); const idx = args.indexOf('--name'); extract(path.resolve(args[1]), args[2], idx >= 0 ? args[idx+1] : null); return; }
    if (command === 'validate') { if (args.length < 2) throw new Error('usage: theme_capsule.mjs validate <theme-json>'); const theme = loadTheme(args[1]); const errors = validateTheme(theme); emit({ ok: errors.length === 0, command: 'validate', schema: SCHEMA, errors, token_count: Object.keys(theme.tokens || {}).length }, errors.length ? 1 : 0); return; }
    if (command === 'apply') { if (args.length < 3) throw new Error('usage: theme_capsule.mjs apply <project-root> <theme-json> [--dry-run] [--allow-partial]'); apply(path.resolve(args[1]), args[2], args.includes('--dry-run'), args.includes('--allow-partial')); return; }
    throw new Error('command must be extract, validate, or apply');
  } catch (error) { emit({ ok: false, error: error.message }, 2); }
}
main();
