import { spawn } from 'node:child_process';
import { createHash } from 'node:crypto';
import { existsSync, writeSync } from 'node:fs';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const TOOL_DIR = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(TOOL_DIR, '..', '..');
const DATA_ROOT = path.join(REPO_ROOT, 'data', 'ui-demo-studio');
const LATEST_PATH = path.join(DATA_ROOT, 'latest.json');
const WORKER_PATH = path.join(TOOL_DIR, 'worker.mjs');
const BENCHMARK_PATH = path.join(TOOL_DIR, 'benchmark-runner.mjs');
const JSON_READ_RETRIES = 3;

function parseArgs(argv) {
  const out = { command: argv[2] || 'status' };
  for (let i = 3; i < argv.length; i += 1) {
    const token = argv[i];
    if (!token.startsWith('--')) continue;
    const key = token.slice(2);
    const next = argv[i + 1];
    if (next === undefined || next.startsWith('--')) {
      out[key] = 'true';
      continue;
    }
    out[key] = next;
    i += 1;
  }
  return out;
}

function parseDuration(value) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return 30;
  return Math.max(8, Math.min(60, Math.round(parsed)));
}

function parseViewport(value) {
  const match = String(value || '1280x720').trim().match(/^(\d{2,4})\s*x\s*(\d{2,4})$/i);
  if (!match) return '1280x720';
  const width = Math.max(320, Math.min(2560, Number(match[1])));
  const height = Math.max(480, Math.min(1600, Number(match[2])));
  return `${width}x${height}`;
}

function parseBoolean(value, fallback = true) {
  if (value === undefined || value === null || value === '') return fallback;
  return !['false', '0', 'no', 'off'].includes(String(value).trim().toLowerCase());
}

function makeRunId(target) {
  const stamp = new Date().toISOString().replace(/[-:]/g, '').replace(/\.\d{3}Z$/, 'Z');
  const suffix = createHash('sha1').update(`${target}:${process.pid}:${Date.now()}`).digest('hex').slice(0, 6);
  return `${stamp}-${suffix}`;
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function readJson(filePath) {
  let lastError;
  for (let attempt = 0; attempt < JSON_READ_RETRIES; attempt += 1) {
    try {
      const raw = await readFile(filePath, 'utf8');
      return JSON.parse(raw.replace(/^\uFEFF/, ''));
    } catch (error) {
      lastError = error;
      if (attempt + 1 < JSON_READ_RETRIES) await sleep(20 * (attempt + 1));
    }
  }
  throw lastError;
}

async function writeJson(filePath, value) {
  await writeFile(filePath, JSON.stringify(value, null, 2), 'utf8');
}

async function patchStatus(statusPath, patch) {
  const current = existsSync(statusPath) ? await readJson(statusPath) : {};
  const next = { ...current, ...patch, updated_at: new Date().toISOString() };
  await writeJson(statusPath, next);
  return next;
}

function isHttpUrl(value) {
  return /^https?:\/\//i.test(String(value || '').trim());
}

function spawnDetachedNode(scriptPath, argv, { windowsHide = true } = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(process.execPath, [scriptPath, ...argv], {
      cwd: REPO_ROOT,
      detached: true,
      stdio: ['ignore', 'ignore', 'ignore'],
      windowsHide,
      shell: false,
    });
    let settled = false;
    child.once('error', (error) => {
      if (!settled) {
        settled = true;
        reject(error);
      }
    });
    child.once('spawn', () => {
      settled = true;
      const pid = child.pid;
      child.unref();
      resolve(pid);
    });
  });
}

async function record(args) {
  const targetInput = String(args.target || '').trim();
  if (!targetInput) throw new Error('record requires --target <project-id-or-url>.');

  await mkdir(DATA_ROOT, { recursive: true });
  const runId = makeRunId(targetInput);
  const runDir = path.join(DATA_ROOT, runId);
  const statusPath = path.join(runDir, 'status.json');
  const duration = parseDuration(args.duration);
  const viewport = parseViewport(args.viewport);
  const headless = parseBoolean(args.headless, true);
  const journey = String(args.journey || '').trim();
  const directTarget = isHttpUrl(targetInput) ? targetInput : null;

  await mkdir(runDir, { recursive: true });
  const queued = {
    run_id: runId,
    status: 'queued',
    target_input: targetInput,
    target_url: directTarget,
    duration_seconds: duration,
    viewport,
    headless,
    journey,
    created_at: new Date().toISOString(),
    run_dir: runDir,
    status_file: statusPath,
    message: directTarget
      ? 'Recording pipeline queued.'
      : 'Recording pipeline queued; detached worker will resolve the Synapse project target.',
  };
  await writeJson(statusPath, queued);
  await writeJson(LATEST_PATH, { run_id: runId, run_dir: runDir, status_file: statusPath });

  let workerPid;
  try {
    workerPid = await spawnDetachedNode(
      WORKER_PATH,
      [
        '--run-dir',
        runDir,
        '--run-id',
        runId,
        '--target',
        targetInput,
        '--target-input',
        targetInput,
        '--duration',
        String(duration),
        '--journey',
        journey,
        '--viewport',
        viewport,
        '--headless',
        headless ? 'true' : 'false',
      ],
      { windowsHide: true }
    );
  } catch (error) {
    await patchStatus(statusPath, {
      status: 'launch_error',
      failed_at: new Date().toISOString(),
      message: 'Could not start the detached UI Demo Studio worker.',
      error: error instanceof Error ? error.message : String(error),
    }).catch(() => undefined);
    throw error;
  }

  const starting = await patchStatus(statusPath, {
    status: 'starting',
    worker_pid: workerPid,
    worker_started_at: new Date().toISOString(),
    message: directTarget
      ? 'Detached recording worker started.'
      : 'Detached recording worker started; resolving Synapse project target.',
  });

  return {
    ...starting,
    message: `${starting.message} Use “Check latest” in Synapse for progress.`,
  };
}

async function status() {
  if (!existsSync(LATEST_PATH)) {
    return { status: 'none', message: 'No UI Demo Studio runs yet.' };
  }
  const latest = await readJson(LATEST_PATH);
  if (!latest.status_file || !existsSync(latest.status_file)) {
    return { ...latest, status: 'missing', message: 'Latest run status file is missing.' };
  }
  return await readJson(latest.status_file);
}

function openPath(filePath) {
  if (process.platform === 'win32') {
    const child = spawn('cmd.exe', ['/d', '/s', '/c', 'start', '', filePath], {
      detached: true,
      stdio: ['ignore', 'ignore', 'ignore'],
      windowsHide: true,
      shell: false,
    });
    child.on('error', () => undefined);
    child.unref();
    return;
  }
  const opener = process.platform === 'darwin' ? 'open' : 'xdg-open';
  const child = spawn(opener, [filePath], {
    detached: true,
    stdio: ['ignore', 'ignore', 'ignore'],
    shell: false,
  });
  child.on('error', () => undefined);
  child.unref();
}

async function benchmarkLatest() {
  if (!existsSync(LATEST_PATH)) throw new Error('No UI Demo Studio runs yet.');
  const latest = await readJson(LATEST_PATH);
  if (!latest.run_dir || !existsSync(latest.run_dir)) throw new Error('Latest run directory is missing.');

  const statusPath = latest.status_file || path.join(latest.run_dir, 'status.json');
  if (!existsSync(statusPath)) throw new Error('Latest run status file is missing.');
  const auditPath = path.join(latest.run_dir, 'ux-audit.json');
  if (!existsSync(auditPath)) {
    const current = await readJson(statusPath).catch(() => ({}));
    throw new Error(
      `Latest run is not ready to benchmark yet (status: ${current.status || 'unknown'}; ux-audit.json is missing).`
    );
  }

  const current = await readJson(statusPath);
  await writeJson(statusPath, current);
  await patchStatus(statusPath, {
    status: 'rebenchmark_queued',
    rebenchmark_requested_at: new Date().toISOString(),
    message: 'Re-benchmark queued in a detached worker.',
  });

  const workerPid = await spawnDetachedNode(
    BENCHMARK_PATH,
    ['--run-dir', latest.run_dir],
    { windowsHide: true }
  );

  return {
    status: 'starting',
    run_id: latest.run_id,
    run_dir: latest.run_dir,
    worker_pid: workerPid,
    message: 'Re-benchmark worker started. Use Check latest for the refreshed scorecard.',
  };
}

async function openLatest() {
  if (!existsSync(LATEST_PATH)) throw new Error('No UI Demo Studio runs yet.');
  const latest = await readJson(LATEST_PATH);
  if (!latest.status_file || !existsSync(latest.status_file)) {
    throw new Error('Latest run status file is missing.');
  }
  const statusRecord = await readJson(latest.status_file);
  const reportPath = statusRecord.report_html || path.join(latest.run_dir, 'report.html');
  if (!existsSync(reportPath)) {
    throw new Error(`Latest report is not ready yet (status: ${statusRecord.status || 'unknown'}).`);
  }
  openPath(reportPath);
  return {
    status: 'opened',
    run_id: statusRecord.run_id,
    report_html: reportPath,
    report_url: pathToFileURL(reportPath).href,
  };
}

async function dispatch() {
  const args = parseArgs(process.argv);
  if (args.command === 'record') return await record(args);
  if (args.command === 'status') return await status();
  if (args.command === 'open-latest') return await openLatest();
  if (args.command === 'benchmark-latest') return await benchmarkLatest();
  throw new Error(`Unknown command '${args.command}'. Expected record, status, benchmark-latest, or open-latest.`);
}

function emitJson(payload, fd = 1) {
  const text = `${JSON.stringify(payload)}\n`;
  try {
    writeSync(fd, text, null, 'utf8');
  } catch {
    if (fd === 2) console.error(text.trimEnd());
    else console.log(text.trimEnd());
  }
}

try {
  const result = await dispatch();
  emitJson(result, 1);
  process.exit(0);
} catch (error) {
  const message = error instanceof Error ? error.message : String(error);
  emitJson({ status: 'error', message, platform: os.platform() }, 2);
  process.exit(1);
}
