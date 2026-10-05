import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import { readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const toolDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(toolDir, '..', '..');
const recorder = path.join(toolDir, 'recorder.mjs');
const benchmark = path.join(toolDir, 'benchmark-runner.mjs');

function parseArgs(argv) {
  const out = {};
  for (let i = 2; i < argv.length; i += 1) {
    const token = argv[i];
    if (!token.startsWith('--')) continue;
    const next = argv[i + 1];
    out[token.slice(2)] = next === undefined || next.startsWith('--') ? 'true' : next;
    if (next !== undefined && !next.startsWith('--')) i += 1;
  }
  return out;
}

function isHttpUrl(value) {
  return /^https?:\/\//i.test(String(value || '').trim());
}

async function readJson(filePath) {
  const raw = await readFile(filePath, 'utf8');
  return JSON.parse(raw.replace(/^\uFEFF/, ''));
}

async function patchStatus(filePath, patch) {
  const current = existsSync(filePath) ? await readJson(filePath).catch(() => ({})) : {};
  const next = { ...current, ...patch, updated_at: new Date().toISOString() };
  await writeFile(filePath, JSON.stringify(next, null, 2), 'utf8');
  return next;
}

function replaceArg(argv, flag, value) {
  const next = [...argv];
  const index = next.indexOf(flag);
  if (index >= 0) {
    if (index + 1 < next.length && !next[index + 1].startsWith('--')) next[index + 1] = value;
    else next.splice(index + 1, 0, value);
  } else {
    next.push(flag, value);
  }
  return next;
}

async function resolveProjectTarget(targetInput) {
  if (isHttpUrl(targetInput)) return targetInput;

  const tokenPath = path.join(repoRoot, 'data', 'auth-token');
  if (!existsSync(tokenPath)) {
    throw new Error(`'${targetInput}' is not a URL and Synapse auth-token was not found. Use a full http(s) URL.`);
  }

  const token = (await readFile(tokenPath, 'utf8')).trim();
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 4000);
  timer.unref?.();
  let response;
  try {
    response = await fetch('http://127.0.0.1:7878/api/v1/projects', {
      headers: { 'X-Synapse-Token': token },
      signal: controller.signal,
    });
  } catch (error) {
    if (error?.name === 'AbortError') {
      throw new Error(`Timed out resolving Synapse project '${targetInput}'.`);
    }
    throw error;
  } finally {
    clearTimeout(timer);
  }

  if (!response.ok) {
    throw new Error(`Could not resolve project '${targetInput}' through Synapse (HTTP ${response.status}).`);
  }
  const payload = await response.json();
  const projects = Array.isArray(payload) ? payload : payload.projects || [];
  const needle = targetInput.trim().toLowerCase();
  const project = projects.find((item) => {
    const id = String(item?.id || '').toLowerCase();
    const name = String(item?.name || '').toLowerCase();
    return id === needle || name === needle;
  });
  if (!project) {
    throw new Error(`Synapse project '${targetInput}' was not found. Use a registered project id or a full URL.`);
  }

  const directUrl =
    project.url ||
    project.local_url ||
    project.localUrl ||
    project.launch_url ||
    project.launchUrl ||
    project.preview_url ||
    project.previewUrl;
  if (typeof directUrl === 'string' && isHttpUrl(directUrl)) return directUrl;

  const healthTarget = project.health?.target;
  if (typeof healthTarget === 'string' && isHttpUrl(healthTarget)) {
    try {
      const parsed = new URL(healthTarget);
      return parsed.origin;
    } catch {
      // Fall through to explicit port candidates.
    }
  }

  const portCandidates = [
    project.port,
    project.expected_port,
    project.local_port,
    project.localPort,
    project.launch_port,
    project.launchPort,
    project.runtime?.port,
    project.launch?.port,
    project.process?.port,
  ];
  const port = portCandidates.map(Number).find((candidate) => Number.isInteger(candidate) && candidate > 0);
  if (port) return `http://127.0.0.1:${port}`;

  throw new Error(
    `Project '${project.name || project.id}' has no discoverable local URL/port. Launch it first or enter its URL directly.`
  );
}

function run(script, argv) {
  return new Promise((resolve, reject) => {
    const child = spawn(process.execPath, [script, ...argv], {
      cwd: repoRoot,
      stdio: ['ignore', 'ignore', 'ignore'],
      windowsHide: true,
      shell: false,
    });
    child.once('error', reject);
    child.once('exit', (code) => {
      if (code === 0) resolve();
      else reject(new Error(path.basename(script) + ' exited with code ' + code));
    });
  });
}

const parsed = parseArgs(process.argv);
const runDir = path.resolve(String(parsed['run-dir'] || '.'));
const statusPath = path.join(runDir, 'status.json');
const targetInput = String(parsed['target-input'] || parsed.target || '').trim();
let argv = process.argv.slice(2);

try {
  await patchStatus(statusPath, {
    status: isHttpUrl(targetInput) ? 'recorder_queued' : 'resolving_target',
    worker_pid: process.pid,
    worker_started_at: new Date().toISOString(),
    message: isHttpUrl(targetInput)
      ? 'Detached worker is starting the recorder.'
      : 'Detached worker is resolving the Synapse project target.',
  });

  const resolvedTarget = await resolveProjectTarget(targetInput);
  argv = replaceArg(argv, '--target', resolvedTarget);
  argv = replaceArg(argv, '--target-input', targetInput);
  await patchStatus(statusPath, {
    status: 'recorder_queued',
    target_url: resolvedTarget,
    target_resolved_at: new Date().toISOString(),
    message: 'Target resolved. Starting recorder.',
  });

  await run(recorder, argv);
  await patchStatus(statusPath, {
    status: 'benchmark_queued',
    benchmark_queued_at: new Date().toISOString(),
    message: 'Recording complete. Starting detailed benchmark.',
  });
  await run(benchmark, argv);
  process.exit(0);
} catch (error) {
  const message = error instanceof Error ? error.message : String(error);
  const current = await readJson(statusPath).catch(() => ({}));
  const workerOwnedStates = new Set([
    'queued',
    'starting',
    'resolving_target',
    'recorder_queued',
    'benchmark_queued',
  ]);
  if (!current.status || workerOwnedStates.has(current.status)) {
    await patchStatus(statusPath, {
      status: 'worker_error',
      failed_at: new Date().toISOString(),
      error: message,
      message: 'UI Demo Studio detached worker failed before the active stage could record its own error status.',
    }).catch(() => undefined);
  }
  process.exit(1);
}
