#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const DIRECT_EDIT = path.join(HERE, 'direct_ast_edit.mjs');
const SOURCE_RE = /^(.*):(\d+):(\d+)$/;

function emit(payload, code = 0) {
  process.stdout.write(`${JSON.stringify(payload, null, 2)}\n`);
  process.exitCode = code;
}

function readJson(raw) {
  if (!raw) throw new Error('batch edit JSON/path is required');
  const maybePath = path.resolve(raw);
  const text = fs.existsSync(maybePath) && fs.statSync(maybePath).isFile()
    ? fs.readFileSync(maybePath, 'utf8')
    : raw;
  const parsed = JSON.parse(text);
  const edits = Array.isArray(parsed) ? parsed : parsed?.edits;
  if (!Array.isArray(edits) || edits.length === 0) throw new Error('batch edit must contain a non-empty edits array');
  if (edits.length > 100) throw new Error('batch edit is limited to 100 edits');
  return edits;
}

function sourceInfo(projectRoot, edit) {
  const source = String(edit?.source || edit?.ui_forge_source || '').replace(/\\/g, '/');
  const match = SOURCE_RE.exec(source);
  if (!match) throw new Error(`invalid source pointer: ${source || '<empty>'}`);
  const relative = match[1].replace(/^\/+/, '');
  const root = path.resolve(projectRoot);
  const target = path.resolve(root, relative);
  const relCheck = path.relative(root, target);
  if (relCheck.startsWith('..') || path.isAbsolute(relCheck)) throw new Error(`source pointer escapes project root: ${source}`);
  if (!fs.existsSync(target) || !fs.statSync(target).isFile()) throw new Error(`source file does not exist: ${relative}`);
  return {
    source,
    relative: relative.replace(/\\/g, '/'),
    target,
    line: Number(match[2]),
    column: Number(match[3]),
  };
}

function invokeDirect(projectRoot, edit, dryRun) {
  const args = [DIRECT_EDIT, projectRoot, JSON.stringify(edit)];
  if (dryRun) args.push('--dry-run');
  const result = spawnSync(process.execPath, args, {
    encoding: 'utf8',
    timeout: 30_000,
    windowsHide: true,
  });
  let payload = null;
  try { payload = JSON.parse(result.stdout || '{}'); } catch { /* reported by caller */ }
  return {
    ok: result.status === 0 && payload?.ok === true,
    status: result.status,
    stdout: result.stdout,
    stderr: result.stderr,
    payload,
  };
}

function main() {
  const args = process.argv.slice(2);
  if (args.length < 2) {
    emit({ ok: false, error: 'usage: batch_ast_edit.mjs <project-root> <batch-json-or-path> [--dry-run]' }, 2);
    return;
  }
  const projectRoot = path.resolve(args[0]);
  const dryRun = args.includes('--dry-run');

  let entries;
  try {
    const edits = readJson(args[1]);
    entries = edits.map((edit, index) => ({ index, edit, ...sourceInfo(projectRoot, edit) }));
  } catch (error) {
    emit({ ok: false, error: error.message }, 2);
    return;
  }

  const sourceKeys = entries.map((entry) => entry.source);
  if (new Set(sourceKeys).size !== sourceKeys.length) {
    emit({ ok: false, error: 'batch edit refuses duplicate source pointers; combine operations for one element explicitly' }, 2);
    return;
  }

  // Validate every edit against the untouched source tree before mutating anything.
  const validation = [];
  for (const entry of entries) {
    const result = invokeDirect(projectRoot, entry.edit, true);
    validation.push({ index: entry.index, source: entry.source, ok: result.ok, result: result.payload, stderr: result.stderr });
    if (!result.ok) {
      emit({
        ok: false,
        error: 'batch validation failed; nothing was written',
        schema: 'ui-forge-batch-ast-edit-v1',
        atomic: true,
        failed_index: entry.index,
        failed_source: entry.source,
        validation,
      }, 1);
      return;
    }
  }

  const touchedFiles = [...new Set(entries.map((entry) => entry.target))];
  const backups = new Map(touchedFiles.map((target) => [target, fs.readFileSync(target, 'utf8')]));

  // Later source positions are applied first so earlier line/column pointers remain valid.
  const ordered = [...entries].sort((a, b) => {
    const file = a.relative.localeCompare(b.relative);
    if (file !== 0) return file;
    if (a.line !== b.line) return b.line - a.line;
    return b.column - a.column;
  });

  if (dryRun) {
    emit({
      ok: true,
      schema: 'ui-forge-batch-ast-edit-v1',
      dry_run: true,
      atomic: true,
      edit_count: entries.length,
      file_count: touchedFiles.length,
      apply_order: ordered.map((entry) => entry.source),
      validation: validation.map(({ index, source, result }) => ({ index, source, result })),
    });
    return;
  }

  const applied = [];
  try {
    for (const entry of ordered) {
      const result = invokeDirect(projectRoot, entry.edit, false);
      if (!result.ok) {
        const error = new Error(`direct edit failed during atomic apply at ${entry.source}`);
        error.detail = { entry: { index: entry.index, source: entry.source }, result };
        throw error;
      }
      applied.push({ index: entry.index, source: entry.source, result: result.payload });
    }
  } catch (error) {
    for (const [target, contents] of backups.entries()) fs.writeFileSync(target, contents, 'utf8');
    emit({
      ok: false,
      error: 'batch apply failed; every touched file was restored',
      schema: 'ui-forge-batch-ast-edit-v1',
      atomic: true,
      rolled_back: true,
      applied_before_failure: applied,
      detail: error.detail || { message: error.message },
    }, 1);
    return;
  }

  emit({
    ok: true,
    schema: 'ui-forge-batch-ast-edit-v1',
    dry_run: false,
    atomic: true,
    rolled_back: false,
    edit_count: entries.length,
    file_count: touchedFiles.length,
    files: touchedFiles.map((target) => path.relative(projectRoot, target).replace(/\\/g, '/')),
    apply_order: ordered.map((entry) => entry.source),
    applied: applied.sort((a, b) => a.index - b.index),
    verification_required: [
      'rerender application',
      're-probe every selected UI Forge source id',
      'run affected desktop/mobile browser proof',
      'check console/runtime errors',
    ],
  });
}

main();
