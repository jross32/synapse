#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const postcss = require('postcss');
const selectorParser = require('postcss-selector-parser');

const SKIP_DIRS = new Set(['node_modules', '.git', '.synapse', 'dist', 'build', 'coverage', '.next', '.nuxt']);
const SAFE_STATES = new Set(['hover','focus','focus-visible','active','disabled','checked']);

function normalizeMediaText(raw) {
  return String(raw || '').trim().replace(/\s+/g, ' ');
}
function normalizeMediaChain(raw) {
  if (raw == null || raw === '' || (Array.isArray(raw) && raw.length === 0)) return [];
  const items = Array.isArray(raw) ? raw : [raw];
  if (items.length > 4) throw new Error('media_chain is limited to 4 nested @media contexts');
  return items.map((item) => {
    const text = normalizeMediaText(item);
    if (!text) throw new Error('media_chain entries cannot be empty');
    if (text.length > 240 || /[{};]/.test(text)) throw new Error('media_chain contains unsafe or structural syntax');
    return text;
  });
}
function ruleMediaChain(rule) {
  const chain = [];
  let parent = rule.parent;
  while (parent) {
    if (parent.type === 'atrule' && String(parent.name || '').toLowerCase() === 'media') chain.unshift(normalizeMediaText(parent.params));
    parent = parent.parent;
  }
  return chain;
}
function sameMediaChain(a, b) {
  return a.length === b.length && a.every((item, index) => item === b[index]);
}
const SAFE_PROPERTIES = new Set([
  'margin','margin-top','margin-right','margin-bottom','margin-left',
  'padding','padding-top','padding-right','padding-bottom','padding-left',
  'gap','row-gap','column-gap',
  'color','background','background-color','opacity',
  'font-family','font-size','font-weight','font-style','line-height','letter-spacing','text-align','text-transform',
  'border','border-width','border-style','border-color','border-radius',
  'border-top','border-right','border-bottom','border-left',
  'box-shadow','outline','outline-offset',
  'width','min-width','max-width','height','min-height','max-height',
  'display','flex','flex-direction','flex-wrap','flex-grow','flex-shrink','flex-basis',
  'align-items','align-content','align-self','justify-content','justify-items','justify-self',
  'grid-template-columns','grid-template-rows','grid-auto-flow','grid-column','grid-row','place-items','place-content',
  'position','top','right','bottom','left','inset','z-index','overflow','overflow-x','overflow-y',
  'transform','transform-origin','transition','cursor','object-fit','object-position',
]);

function emit(payload, code = 0) {
  process.stdout.write(`${JSON.stringify(payload, null, 2)}\n`);
  process.exitCode = code;
}

function readJson(raw) {
  if (!raw) throw new Error('style request JSON/path is required');
  const maybe = path.resolve(raw);
  const text = fs.existsSync(maybe) && fs.statSync(maybe).isFile() ? fs.readFileSync(maybe, 'utf8') : raw;
  const parsed = JSON.parse(text);
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) throw new Error('style request must be an object');
  return parsed.style_request && typeof parsed.style_request === 'object' ? parsed.style_request : parsed;
}

function safeDeclarations(raw) {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) throw new Error('declarations must be an object');
  const entries = Object.entries(raw);
  if (!entries.length) throw new Error('declarations cannot be empty');
  if (entries.length > 20) throw new Error('style request is limited to 20 declarations');
  const out = {};
  for (const [keyRaw, valueRaw] of entries) {
    const key = String(keyRaw).trim().toLowerCase();
    const value = String(valueRaw).trim();
    if (!SAFE_PROPERTIES.has(key)) throw new Error(`CSS property is not in the safe visual-edit allowlist: ${key || '<empty>'}`);
    if (!value) throw new Error(`CSS value cannot be empty: ${key}`);
    if (/[;{}]/.test(value)) throw new Error(`CSS value contains structural syntax and is refused: ${key}`);
    if (/url\s*\(/i.test(value)) throw new Error(`CSS url() values require the main coding path: ${key}`);
    out[key] = value;
  }
  return out;
}

function cssFiles(root) {
  const found = [];
  function walk(dir) {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      if (entry.isDirectory()) {
        if (!SKIP_DIRS.has(entry.name)) walk(path.join(dir, entry.name));
        continue;
      }
      if (!entry.isFile() || !/\.css$/i.test(entry.name)) continue;
      const target = path.join(dir, entry.name);
      if (fs.statSync(target).size <= 1_000_000) found.push(target);
    }
  }
  walk(root);
  return found.sort();
}

function rightmostCompound(selectorNode) {
  const nodes = selectorNode.nodes || [];
  let start = 0;
  for (let i = nodes.length - 1; i >= 0; i -= 1) {
    if (nodes[i].type === 'combinator') { start = i + 1; break; }
  }
  return nodes.slice(start);
}

function scoreSelector(selectorText, probe, requestedState = null) {
  let best = null;
  let parsed;
  try { parsed = selectorParser().astSync(selectorText); } catch { return null; }
  parsed.each((selectorNode) => {
    const compound = rightmostCompound(selectorNode);
    const pseudos = compound.filter((node) => node.type === 'pseudo').map((node) => node.value);
    if (requestedState) {
      const expected = `:${requestedState}`;
      // Automatic state editing requires exactly the requested pseudo-state. Complex
      // selectors (:not, :has, pseudo-elements, multiple states) require explicit ownership.
      if (pseudos.length !== 1 || pseudos[0] !== expected) return;
    } else if (pseudos.length) {
      // Base-state editing must never silently land in :hover/:focus/etc.
      return;
    }
    let score = 0;
    let matched = 0;
    let impossible = false;
    let specificity = 0;
    for (const node of compound) {
      if (node.type === 'id') {
        specificity += 100;
        if (probe.id && node.value === probe.id) { score += 150; matched += 1; }
        else impossible = true;
      } else if (node.type === 'class') {
        specificity += 10;
        if ((probe.classes || []).includes(node.value)) { score += 40; matched += 1; }
        else impossible = true;
      } else if (node.type === 'tag' && node.value !== '*') {
        specificity += 1;
        if (probe.tag && node.value.toLowerCase() === String(probe.tag).toLowerCase()) { score += 20; matched += 1; }
        else impossible = true;
      } else if (node.type === 'pseudo') {
        // Pseudo classes/elements refine a rule but do not disqualify ownership.
        specificity += node.value.startsWith('::') ? 1 : 10;
      }
    }
    if (impossible || matched === 0) return;
    const candidate = { selector: selectorNode.toString(), score: score + Math.min(specificity, 30) / 10, matched, specificity };
    if (!best || candidate.score > best.score) best = candidate;
  });
  return best;
}

function candidateRules(projectRoot, probe, explicitFile, explicitSelector, requestedState = null, requestedMediaChain = []) {
  const root = path.resolve(projectRoot);
  const files = explicitFile ? [path.resolve(root, explicitFile)] : cssFiles(root);
  const candidates = [];
  for (const file of files) {
    const rel = path.relative(root, file);
    if (rel.startsWith('..') || path.isAbsolute(rel) || !fs.existsSync(file)) throw new Error(`stylesheet escapes project root or does not exist: ${explicitFile}`);
    const source = fs.readFileSync(file, 'utf8');
    let ast;
    try { ast = postcss.parse(source, { from: file }); } catch (error) { throw new Error(`PostCSS could not parse ${rel}: ${error.message}`); }
    ast.walkRules((rule) => {
      const mediaChain = ruleMediaChain(rule);
      if (!sameMediaChain(mediaChain, requestedMediaChain)) return;
      if (explicitSelector && rule.selector !== explicitSelector) return;
      const match = explicitSelector
        ? { selector: rule.selector, score: 10_000, matched: 1, specificity: 0 }
        : scoreSelector(rule.selector, probe, requestedState);
      if (!match) return;
      candidates.push({ file, relative: rel.replace(/\\/g, '/'), source, ast, rule, media_chain: mediaChain, ...match });
    });
  }
  return candidates.sort((a, b) => b.score - a.score || a.relative.localeCompare(b.relative) || a.rule.source.start.line - b.rule.source.start.line);
}

function ruleSnapshot(rule) {
  const declarations = {};
  rule.walkDecls((decl) => { declarations[decl.prop] = decl.value + (decl.important ? ' !important' : ''); });
  return { selector: rule.selector, declarations };
}

function main() {
  const args = process.argv.slice(2);
  if (args.length < 2) {
    emit({ ok: false, error: 'usage: css_style_editor.mjs <project-root> <style-request-json-or-path> [--dry-run]' }, 2);
    return;
  }
  const projectRoot = path.resolve(args[0]);
  const dryRun = args.includes('--dry-run');
  let request;
  let declarations;
  try {
    request = readJson(args[1]);
    declarations = safeDeclarations(request.declarations || request.properties);
  } catch (error) {
    emit({ ok: false, error: error.message }, 2);
    return;
  }
  const probe = request.probe || request.selection || {};
  if (!probe || typeof probe !== 'object') {
    emit({ ok: false, error: 'style request requires a browser probe/selection object' }, 2);
    return;
  }
  const requestedState = request.state == null || request.state === '' ? null : String(request.state).trim().toLowerCase();
  if (requestedState && !SAFE_STATES.has(requestedState)) {
    emit({ ok: false, error: `unsupported interaction state: ${requestedState}` }, 2);
    return;
  }
  let requestedMediaChain;
  try {
    requestedMediaChain = normalizeMediaChain(request.media_chain ?? request.media ?? null);
  } catch (error) {
    emit({ ok: false, error: error.message }, 2);
    return;
  }

  let candidates;
  try {
    candidates = candidateRules(projectRoot, probe, request.file || null, request.selector || null, requestedState, requestedMediaChain);
  } catch (error) {
    emit({ ok: false, error: error.message }, 2);
    return;
  }
  if (!candidates.length) {
    emit({ ok: false, error: requestedState ? `no CSS rule could be linked to the selected element for state :${requestedState} in the requested media context` : 'no CSS rule could be linked to the selected element in the requested media context', state: requestedState, media_chain: requestedMediaChain, candidates: [] }, 1);
    return;
  }
  const top = candidates[0];
  const ties = candidates.filter((item) => item.score === top.score);
  if (ties.length > 1 && !(request.file && request.selector)) {
    emit({
      ok: false,
      error: 'ambiguous CSS ownership; provide explicit file + selector or use the main coding path',
      candidates: ties.slice(0, 10).map((item) => ({ file: item.relative, selector: item.rule.selector, media_chain: item.media_chain, score: item.score, line: item.rule.source.start.line })),
    }, 1);
    return;
  }

  const beforeFile = top.source;
  const beforeRule = ruleSnapshot(top.rule);
  const changes = [];
  for (const [prop, value] of Object.entries(declarations)) {
    let existing = null;
    top.rule.walkDecls(prop, (decl) => { if (!existing) existing = decl; });
    const before = existing ? existing.value + (existing.important ? ' !important' : '') : null;
    if (existing) existing.value = value;
    else top.rule.append({ prop, value });
    changes.push({ property: prop, before, after: value });
  }
  const afterFile = top.ast.toString();
  if (afterFile === beforeFile) {
    emit({ ok: false, error: 'style edit produced no source change' }, 1);
    return;
  }
  try { postcss.parse(afterFile, { from: top.file }); } catch (error) {
    emit({ ok: false, error: `edited CSS failed syntax reparse; nothing was written: ${error.message}` }, 1);
    return;
  }
  if (!dryRun) fs.writeFileSync(top.file, afterFile, 'utf8');

  emit({
    ok: true,
    schema: 'ui-forge-css-style-edit-v1',
    dry_run: dryRun,
    file: top.relative,
    selector: top.rule.selector,
    state: requestedState,
    media_chain: top.media_chain,
    line: top.rule.source.start.line,
    ownership_score: top.score,
    candidate_count: candidates.length,
    before_rule: beforeRule,
    after_rule: ruleSnapshot(top.rule),
    changes,
    syntax_reparse_passed: true,
    verification_required: [requestedState ? `exercise real browser state :${requestedState}` : 'rerender application', ...(requestedMediaChain.length ? [`exercise a viewport matching media chain: ${requestedMediaChain.join(' -> ')}`, 'exercise a contrasting viewport outside that media chain'] : []), 're-probe selected element computed style and geometry','check desktop/mobile layout','check console/runtime errors'],
  });
}

main();
