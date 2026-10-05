#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const parser = require('@babel/parser');
const traverseModule = require('@babel/traverse');
const t = require('@babel/types');
const traverse = traverseModule.default || traverseModule;

const SAFE_STRING_ATTRIBUTES = new Set([
  'aria-label', 'aria-description', 'aria-live', 'aria-current',
  'title', 'placeholder', 'alt', 'role', 'name', 'type', 'inputMode',
]);
const SOURCE_RE = /^(.*):(\d+):(\d+)$/;

function fail(message, code = 2, details = {}) {
  process.stdout.write(`${JSON.stringify({ ok: false, error: message, ...details }, null, 2)}\n`);
  process.exit(code);
}

function readEdit(raw) {
  if (!raw) fail('edit JSON/path is required');
  const maybePath = path.resolve(raw);
  let text = raw;
  if (fs.existsSync(maybePath) && fs.statSync(maybePath).isFile()) text = fs.readFileSync(maybePath, 'utf8');
  try {
    const parsed = JSON.parse(text);
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) fail('edit must be a JSON object');
    return parsed;
  } catch (error) {
    fail(`invalid edit JSON: ${error.message}`);
  }
}

function resolveSource(projectRoot, source) {
  const match = SOURCE_RE.exec(String(source || '').replace(/\\/g, '/'));
  if (!match) fail('source must be a UI Forge source pointer: relative/file.jsx:line:column');
  const [, relativeRaw, lineRaw, columnRaw] = match;
  const relative = relativeRaw.replace(/^\/+/, '');
  const root = path.resolve(projectRoot);
  const target = path.resolve(root, relative);
  const relCheck = path.relative(root, target);
  if (relCheck.startsWith('..') || path.isAbsolute(relCheck)) fail('source pointer escapes project root');
  if (!fs.existsSync(target) || !fs.statSync(target).isFile()) fail(`source file does not exist: ${relative}`);
  return { root, target, relative: relative.replace(/\\/g, '/'), line: Number(lineRaw), column: Number(columnRaw) };
}

function parserPlugins(filename) {
  const ext = path.extname(filename).toLowerCase();
  const plugins = ['jsx'];
  if (ext === '.ts' || ext === '.tsx') plugins.push('typescript');
  return plugins;
}

function parseSource(source, filename) {
  return parser.parse(source, {
    sourceType: 'unambiguous',
    sourceFilename: filename,
    plugins: parserPlugins(filename),
    errorRecovery: false,
  });
}

function jsxName(node) {
  if (t.isJSXIdentifier(node)) return node.name;
  if (t.isJSXMemberExpression(node)) return `${jsxName(node.object)}.${jsxName(node.property)}`;
  if (t.isJSXNamespacedName(node)) return `${jsxName(node.namespace)}:${jsxName(node.name)}`;
  return '';
}

function attributeName(attr) {
  if (!t.isJSXAttribute(attr)) return '';
  if (t.isJSXIdentifier(attr.name)) return attr.name.name;
  if (t.isJSXNamespacedName(attr.name)) return `${jsxName(attr.name.namespace)}:${jsxName(attr.name.name)}`;
  return '';
}

function findAttribute(opening, name) {
  return opening.attributes.find((attr) => t.isJSXAttribute(attr) && attributeName(attr) === name) || null;
}

function staticStringValue(attr) {
  if (!attr || !t.isJSXAttribute(attr)) return { ok: false, reason: 'attribute is missing' };
  if (t.isStringLiteral(attr.value)) {
    return { ok: true, value: attr.value.value, start: attr.value.start, end: attr.value.end };
  }
  if (t.isJSXExpressionContainer(attr.value) && t.isStringLiteral(attr.value.expression)) {
    return { ok: true, value: attr.value.expression.value, start: attr.value.start, end: attr.value.end };
  }
  return { ok: false, reason: 'attribute is not a static string' };
}

function quoted(value) {
  return JSON.stringify(String(value));
}

function patchExistingStringAttribute(opening, name, value) {
  const existing = findAttribute(opening, name);
  if (!existing) return null;
  const current = staticStringValue(existing);
  if (!current.ok) fail(`refusing to edit dynamic ${name}: ${current.reason}`);
  return {
    patch: { start: current.start, end: current.end, replacement: quoted(value) },
    result: { before: current.value, after: String(value) },
  };
}

function insertStringAttribute(opening, name, value) {
  const closeWidth = opening.selfClosing ? 2 : 1;
  const insertAt = opening.end - closeWidth;
  return {
    patch: { start: insertAt, end: insertAt, replacement: ` ${name}=${quoted(value)}` },
    result: { before: null, after: String(value) },
  };
}

function setStringAttribute(opening, name, value) {
  return patchExistingStringAttribute(opening, name, value) || insertStringAttribute(opening, name, value);
}

function classTokens(opening, op) {
  const existing = findAttribute(opening, 'className') || findAttribute(opening, 'class');
  const add = Array.isArray(op.add) ? op.add.map(String).filter(Boolean) : [];
  const remove = new Set(Array.isArray(op.remove) ? op.remove.map(String) : []);
  if (!existing) {
    if (!add.length) fail('class_tokens needs an existing static className/class or at least one add token');
    const after = [...new Set(add)].join(' ');
    const inserted = insertStringAttribute(opening, 'className', after);
    return { patch: inserted.patch, result: { before: '', after } };
  }
  const current = staticStringValue(existing);
  if (!current.ok) fail(`refusing to edit dynamic ${attributeName(existing)}: ${current.reason}`);
  const tokens = current.value.split(/\s+/).filter(Boolean).filter((token) => !remove.has(token));
  for (const token of add) if (!tokens.includes(token)) tokens.push(token);
  const after = tokens.join(' ');
  return {
    patch: { start: current.start, end: current.end, replacement: quoted(after) },
    result: { before: current.value, after },
  };
}

function setStaticText(element, value) {
  const meaningful = element.children.filter((child) => {
    if (t.isJSXText(child)) return child.value.trim().length > 0;
    return true;
  });
  if (meaningful.length !== 1 || !t.isJSXText(meaningful[0])) {
    fail('refusing set_text: selected element does not contain exactly one static JSX text child');
  }
  const text = String(value);
  if (/[<{]/.test(text)) {
    fail('refusing set_text containing < or {: use an AI/source edit because JSX escaping would change structure');
  }
  const node = meaningful[0];
  return {
    patch: { start: node.start, end: node.end, replacement: text },
    result: { before: node.value.trim(), after: text },
  };
}

function setTextSegment(element, operation) {
  const segments = element.children.filter((child) => t.isJSXText(child) && child.value.trim().length > 0);
  const index = Number(operation.segment_index ?? 0);
  if (!Number.isInteger(index) || index < 0 || index >= segments.length) fail('refusing set_text_segment: segment_index does not identify a static JSX text child');
  const node = segments[index];
  const expected = operation.expected_text == null ? null : String(operation.expected_text);
  const before = node.value.trim();
  if (expected !== null && before !== expected) fail('refusing set_text_segment: expected_text does not match current source text');
  const text = String(operation.value ?? '');
  if (/[<{]/.test(text)) fail('refusing set_text_segment containing < or {: use an AI/source edit because JSX escaping would change structure');
  const raw = node.value;
  const startOffset = raw.indexOf(before);
  if (startOffset < 0) fail('refusing set_text_segment: could not preserve surrounding JSX whitespace');
  const replacement = raw.slice(0, startOffset) + text + raw.slice(startOffset + before.length);
  return { patch: { start: node.start, end: node.end, replacement }, result: { before, after: text, segment_index: index } };
}

function buildOperation(elementPath, operation) {
  const opening = elementPath.node.openingElement;
  const type = String(operation?.type || '');
  if (type === 'set_text') {
    const built = setStaticText(elementPath.node, operation.value ?? '');
    return { type, ...built };
  }
  if (type === 'set_text_segment') {
    const built = setTextSegment(elementPath.node, operation);
    return { type, ...built };
  }
  if (type === 'class_tokens') {
    const built = classTokens(opening, operation);
    return { type, ...built };
  }
  if (type === 'replace_class') {
    const built = setStringAttribute(opening, 'className', operation.value ?? '');
    return { type, ...built };
  }
  if (type === 'set_attribute') {
    const name = String(operation.name || '');
    if (!SAFE_STRING_ATTRIBUTES.has(name)) fail(`attribute ${name || '<empty>'} is not in the safe direct-edit allowlist`);
    const built = setStringAttribute(opening, name, operation.value ?? '');
    return { type, name, ...built };
  }
  fail(`unsupported direct edit operation: ${type || '<empty>'}`);
}

function applyPatch(original, patch) {
  if (!Number.isInteger(patch.start) || !Number.isInteger(patch.end) || patch.start < 0 || patch.end < patch.start || patch.end > original.length) {
    fail('AST returned an invalid source range; refusing edit');
  }
  return `${original.slice(0, patch.start)}${patch.replacement}${original.slice(patch.end)}`;
}

function main() {
  const args = process.argv.slice(2);
  if (args.length < 2) fail('usage: direct_ast_edit.mjs <project-root> <edit-json-or-path> [--dry-run]');
  const dryRun = args.includes('--dry-run');
  const projectRoot = args[0];
  const edit = readEdit(args[1]);
  const source = resolveSource(projectRoot, edit.source || edit.ui_forge_source);
  const original = fs.readFileSync(source.target, 'utf8');

  let ast;
  try {
    ast = parseSource(original, source.relative);
  } catch (error) {
    fail(`Babel could not parse ${source.relative}: ${error.message}`);
  }

  let matched = null;
  traverse(ast, {
    JSXElement(elementPath) {
      if (matched) return;
      const opening = elementPath.node.openingElement;
      const loc = opening.loc?.start;
      if (!loc || loc.line !== source.line || loc.column + 1 !== source.column) return;
      const tag = jsxName(opening.name);
      if (!tag || tag[0] !== tag[0].toLowerCase() || tag.includes('.')) {
        fail(`refusing direct edit: source pointer targets non-intrinsic JSX element ${tag || '<unknown>'}`);
      }
      matched = { elementPath, tag };
      elementPath.stop();
    },
  });

  if (!matched) {
    fail('no JSX element matched the exact UI Forge source line/column; regenerate source tags before editing', 1, {
      source: `${source.relative}:${source.line}:${source.column}`,
    });
  }

  const built = buildOperation(matched.elementPath, edit.operation || {});
  const modified = applyPatch(original, built.patch);
  if (modified === original) fail('direct edit produced no source change', 1);
  try {
    parseSource(modified, source.relative);
  } catch (error) {
    fail(`edited source failed syntax reparse; nothing was written: ${error.message}`, 1);
  }
  if (!dryRun) fs.writeFileSync(source.target, modified, 'utf8');

  process.stdout.write(`${JSON.stringify({
    ok: true,
    schema: 'ui-forge-direct-ast-edit-v2',
    dry_run: dryRun,
    file: source.relative,
    source: `${source.relative}:${source.line}:${source.column}`,
    tag: matched.tag,
    operation: { type: built.type, ...(built.name ? { name: built.name } : {}), ...built.result },
    patch: {
      start: built.patch.start,
      end: built.patch.end,
      replacement_bytes: Buffer.byteLength(built.patch.replacement),
      changed_span_bytes: built.patch.end - built.patch.start,
    },
    bytes_before: Buffer.byteLength(original),
    bytes_after: Buffer.byteLength(modified),
    syntax_reparse_passed: true,
    verification_required: [
      'rerender application',
      'reselect or re-probe the same UI Forge element',
      'check surrounding layout and critical behavior',
      'check console/runtime errors',
    ],
  }, null, 2)}\n`);
}

main();
