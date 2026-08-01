// Synapse Electron main process (Milestone C).
//
// Responsibilities:
//   1. Spawn the Python daemon as a detached child (Contract #6 — daemon
//      survives Electron crashes; Contract #15 — no network calls of our own).
//   2. Wait for /api/v1/health before opening the renderer so the UI never
//      sees a "WS connect failed" flash on cold boot.
//   3. Tray icon with Show / Quit Synapse — closing the window hides to
//      tray, only "Quit Synapse" actually exits.
//   4. Refuse to run elevated unless --allow-admin is passed (Contract #16).

import { app, BrowserWindow, Menu, Tray, ipcMain, nativeImage, shell } from 'electron';
import { ChildProcess, spawn, spawnSync } from 'node:child_process';
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import {
  RestartProgress,
  RestartStageKey,
  RestartStageState,
  createRestartProgress,
  restartProgressHtml,
  updateRestartStage,
} from './restart-progress';

const isDev = !app.isPackaged;
const daemonHost = '127.0.0.1';
const daemonPort = 7878;
const daemonUrl = `http://${daemonHost}:${daemonPort}`;
const FULL_DEV_RESTART_EXIT_CODE = 75;

const ALLOW_ADMIN = process.argv.includes('--allow-admin');

// Renderer inspection (Contract: E2E verification, AGENTS.md Rule #6).
// When --inspect-renderer is passed (or SYNAPSE_INSPECT=1), Electron exposes
// a Chrome DevTools Protocol endpoint so scripts/inspect-electron.js (or any
// CDP client) can attach to the real window: screenshot it, read its console,
// click elements. OFF by default — a CDP port lets any local process drive
// the app, so it's an opt-in dev/CI affordance only.
const INSPECT_RENDERER =
  process.argv.includes('--inspect-renderer') || process.env.SYNAPSE_INSPECT === '1';
const INSPECT_PORT = process.env.SYNAPSE_INSPECT_PORT || '9222';
if (INSPECT_RENDERER) {
  app.commandLine.appendSwitch('remote-debugging-port', INSPECT_PORT);
  app.commandLine.appendSwitch('remote-allow-origins', 'http://localhost:' + INSPECT_PORT);
}

// ── single-instance lock ──────────────────────────────────────────────────
// Synapse hides to tray on close, so we must guard against a second copy
// being launched by the Windows shell.
if (!app.requestSingleInstanceLock()) {
  app.quit();
  process.exit(0);
}

// ── module-level state ────────────────────────────────────────────────────
let mainWindow: BrowserWindow | null = null;
let tray: Tray | null = null;
let daemonProc: ChildProcess | null = null;
let isQuitting = false;
// True only when *this* Electron spawned the daemon. If we attached to a
// daemon that was already running, we must not kill it on quit.
let spawnedDaemon = false;
let trayRefreshTimer: ReturnType<typeof setInterval> | null = null;
// Projects last fetched for the tray submenu.
let trayProjects: Array<{ id: string; name: string; status: string }> = [];
let daemonAuthToken: string | null = null;
let daemonAuthTokenPromise: Promise<string> | null = null;
let daemonOutputTail: string[] = [];
let daemonLastExit: { code: number | null; signal: NodeJS.Signals | null } | null = null;
let restartInFlight = false;
let restartWindow: BrowserWindow | null = null;
let restartWindowReady = false;
let currentRestartProgress: RestartProgress | null = null;
let restartRequestPollTimer: ReturnType<typeof setInterval> | null = null;
let handledRestartOperationId: string | null = null;

const repoRoot = path.resolve(__dirname, '..');

const iconPath = path.join(__dirname, '..', 'electron', 'icons', 'synapse.ico');
const iconPathPackaged = path.join(process.resourcesPath ?? '', 'electron', 'icons', 'synapse.ico');
const CHATGPT_EMBED_ALLOWED_HOSTS = new Set([
  'chatgpt.com',
  'chat.openai.com',
  'auth.openai.com',
  'openai.com',
  'appleid.apple.com',
  'accounts.google.com',
]);

function resolveIconPath(): string {
  // In dev, __dirname is .../dist-electron, so the icons folder is at ../electron/icons/.
  // In packaged builds, electron-builder copies electron/icons/ into resources/.
  return app.isPackaged ? iconPathPackaged : iconPath;
}

function runtimeDataDir(): string {
  return app.isPackaged
    ? path.join(app.getPath('userData'), 'data')
    : path.join(repoRoot, 'data');
}

function restartMarkerPath(): string {
  return path.join(runtimeDataDir(), 'restart-progress.json');
}

function saveRestartMarker(progress: RestartProgress): void {
  if (progress.kind !== 'restart') return;
  const target = restartMarkerPath();
  fs.mkdirSync(path.dirname(target), { recursive: true });
  const temp = `${target}.tmp`;
  fs.writeFileSync(temp, JSON.stringify(progress, null, 2), 'utf-8');
  fs.renameSync(temp, target);
}

function clearRestartMarker(): void {
  try {
    fs.unlinkSync(restartMarkerPath());
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== 'ENOENT') {
      console.error('[synapse] could not clear restart progress:', error);
    }
  }
}

function loadRestartMarker(): RestartProgress | null {
  const target = restartMarkerPath();
  if (!fs.existsSync(target)) return null;
  try {
    const value = JSON.parse(fs.readFileSync(target, 'utf-8')) as RestartProgress;
    if (
      value.kind !== 'restart' ||
      typeof value.operationId !== 'string' ||
      !Array.isArray(value.stages) ||
      !Number.isFinite(Date.parse(value.updatedAt)) ||
      Date.now() - Date.parse(value.updatedAt) > 10 * 60 * 1000
    ) {
      throw new Error('The restart progress record is incomplete or more than 10 minutes old.');
    }
    return value;
  } catch (error) {
    const fallback = createRestartProgress('restart', `invalid-${Date.now()}`, 'startup');
    return updateRestartStage(
      fallback,
      'desktop',
      'error',
      'The saved restart record could not be read.',
      'SYN-BOOT-301',
      error instanceof Error ? error.message : String(error)
    );
  }
}

function pushRestartProgressToWindow(): void {
  if (!restartWindow || restartWindow.isDestroyed() || !restartWindowReady || !currentRestartProgress) {
    return;
  }
  const payload = JSON.stringify(currentRestartProgress);
  void restartWindow.webContents
    .executeJavaScript(`window.updateRestartProgress(${payload})`, true)
    .catch((error) => console.error('[synapse] restart window update failed:', error));
}

function showRestartWindow(progress: RestartProgress): void {
  currentRestartProgress = progress;
  if (progress.kind === 'restart') saveRestartMarker(progress);
  if (restartWindow && !restartWindow.isDestroyed()) {
    restartWindow.setClosable(Boolean(progress.errorCode));
    restartWindow.show();
    restartWindow.focus();
    pushRestartProgressToWindow();
    return;
  }

  restartWindowReady = false;
  restartWindow = new BrowserWindow({
    width: 680,
    height: progress.kind === 'restart' ? 590 : 460,
    minWidth: 560,
    minHeight: 420,
    resizable: false,
    maximizable: false,
    minimizable: true,
    closable: Boolean(progress.errorCode),
    show: false,
    alwaysOnTop: true,
    autoHideMenuBar: true,
    backgroundColor: '#07110c',
    title: progress.kind === 'restart' ? 'Restarting Synapse' : 'Starting Synapse',
    icon: resolveIconPath(),
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });
  restartWindow.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  restartWindow.webContents.on('did-finish-load', () => {
    restartWindowReady = true;
    pushRestartProgressToWindow();
    restartWindow?.show();
    restartWindow?.focus();
  });
  restartWindow.on('closed', () => {
    restartWindow = null;
    restartWindowReady = false;
  });
  const html = restartProgressHtml(progress);
  void restartWindow.loadURL(`data:text/html;charset=UTF-8,${encodeURIComponent(html)}`).catch((error) => {
    console.error('[synapse] restart window failed to load:', error);
  });
}

function setRestartStage(
  key: RestartStageKey,
  state: RestartStageState,
  detail: string,
  errorCode?: string,
  errorMessage?: string
): void {
  if (!currentRestartProgress) return;
  currentRestartProgress = updateRestartStage(
    currentRestartProgress,
    key,
    state,
    detail,
    errorCode,
    errorMessage
  );
  if (currentRestartProgress.kind === 'restart') saveRestartMarker(currentRestartProgress);
  restartWindow?.setClosable(state === 'error');
  pushRestartProgressToWindow();
  if (currentRestartProgress.kind === 'restart') {
    void reportRestartStage(currentRestartProgress.operationId, key, state, detail, errorCode, errorMessage)
      .catch(() => undefined);
  }
}

function finishRestartWindow(): void {
  if (!currentRestartProgress) return;
  const progress = currentRestartProgress;
  if (!progress.stages.every((stage) => stage.state === 'success')) return;
  const timer = setTimeout(() => {
    if (progress.kind === 'restart') clearRestartMarker();
    const completedWindow = restartWindow;
    if (completedWindow && !completedWindow.isDestroyed()) {
      // Keep the progress window protected from accidental user closure while
      // work is active, then explicitly permit the successful auto-close.
      completedWindow.setClosable(true);
      completedWindow.close();
      if (!completedWindow.isDestroyed()) completedWindow.destroy();
    }
    const completedMainWindow = mainWindow;
    if (completedMainWindow && !completedMainWindow.isDestroyed()) {
      completedMainWindow.show();
      completedMainWindow.focus();
    }
    currentRestartProgress = null;
  // Leave the all-green result visible long enough for a person to actually
  // read it before handing focus back to the main Synapse window.
  }, 3200);
  timer.unref();
}

function isBrokenPipeError(error: unknown): error is NodeJS.ErrnoException {
  return (
    error instanceof Error &&
    'code' in error &&
    (error as NodeJS.ErrnoException).code === 'EPIPE'
  );
}

function protectConsolePipe(stream: NodeJS.WriteStream): void {
  stream.on('error', (error) => {
    if (isBrokenPipeError(error)) return;
    console.error('[synapse] console stream failed:', error);
  });
}

function forwardDaemonOutput(stream: NodeJS.WriteStream, prefix: string, chunk: Buffer): void {
  const text = chunk.toString();
  const lines = text.replace(/\r/g, '').split('\n').filter((line) => line.length > 0);
  if (lines.length > 0) {
    daemonOutputTail = [...daemonOutputTail, ...lines].slice(-40);
  }
  if (stream.destroyed || !stream.writable) return;
  try {
    stream.write(`${prefix}${text}`);
  } catch (error) {
    if (isBrokenPipeError(error)) return;
    throw error;
  }
}

protectConsolePipe(process.stdout);
protectConsolePipe(process.stderr);

// ── admin refusal (Contract #16) ──────────────────────────────────────────
function refuseAdminIfNeeded(): void {
  if (process.platform !== 'win32') return;
  // The reliable way to detect elevation on Windows is to try writing to a
  // privileged registry path; here we use a cheaper heuristic that matches
  // most realistic launches without spinning up a separate executable.
  // Final hardening lands in Milestone J's installer.
  if (process.env.IS_ELEVATED === '1' && !ALLOW_ADMIN) {
    console.error(
      'Synapse refuses to run as Administrator. Re-launch without elevation, ' +
        'or pass --allow-admin if you are sure. See docs/security.md.'
    );
    app.quit();
    process.exit(2);
  }
}

// ── daemon spawn + health wait ────────────────────────────────────────────
function resolvePackagedDaemonPath(): string {
  const candidates = [
    path.join(process.resourcesPath, 'daemon', 'synapse-daemon.exe'),
    path.join(process.resourcesPath, 'daemon', 'synapsed.exe'),
  ];
  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) return candidate;
  }
  throw new Error(
    `Bundled daemon executable not found. Checked: ${candidates.join(', ')}`
  );
}

function buildDaemonLaunch(): { command: string; args: string[]; cwd: string } {
  if (app.isPackaged) {
    return {
      command: resolvePackagedDaemonPath(),
      args: [
        '--port',
        String(daemonPort),
        '--data-dir',
        path.join(app.getPath('userData'), 'data'),
        '--tools-dir',
        path.join(process.resourcesPath, 'tools'),
      ],
      cwd: process.resourcesPath,
    };
  }
  return {
    command: 'python',
    args: ['-m', 'synapse_daemon', '--port', String(daemonPort), '--data-dir', 'data'],
    cwd: repoRoot,
  };
}

function shouldKeepPopupInApp(rawUrl: string): boolean {
  try {
    const url = new URL(rawUrl);
    const host = url.hostname.toLowerCase();
    if (CHATGPT_EMBED_ALLOWED_HOSTS.has(host)) return true;
    return Array.from(CHATGPT_EMBED_ALLOWED_HOSTS).some(
      (allowedHost) => host === allowedHost || host.endsWith(`.${allowedHost}`)
    );
  } catch {
    return false;
  }
}

function shouldAllowEmbeddedChatgptUrl(rawUrl: string): boolean {
  try {
    const url = new URL(rawUrl);
    return url.protocol === 'https:' && shouldKeepPopupInApp(rawUrl);
  } catch {
    return false;
  }
}

function spawnDaemon(): ChildProcess {
  const launch = buildDaemonLaunch();
  daemonOutputTail = [];
  daemonLastExit = null;
  daemonAuthToken = null;
  daemonAuthTokenPromise = null;

  console.log(
    `[synapse] spawning daemon: ${launch.command} ${launch.args.join(' ')}  (cwd=${launch.cwd})`
  );

  const proc = spawn(launch.command, launch.args, {
    cwd: launch.cwd,
    stdio: ['ignore', 'pipe', 'pipe'],
    // detached: false in dev so the daemon dies with us cleanly.
    // Milestone J flips this so the daemon survives UI death.
    detached: false,
    windowsHide: true,
  });

  proc.stdout?.on('data', (chunk: Buffer) => {
    forwardDaemonOutput(process.stdout, '[daemon] ', chunk);
  });
  proc.stderr?.on('data', (chunk: Buffer) => {
    forwardDaemonOutput(process.stderr, '[daemon] ', chunk);
  });
  proc.on('exit', (code, signal) => {
    console.log(`[synapse] daemon exited (code=${code}, signal=${signal})`);
    daemonLastExit = { code, signal };
    daemonProc = null;
    if (!isQuitting) {
      // The daemon should outlive the UI; if it died unexpectedly, surface
      // the failure in the tray tooltip rather than silently broken state.
      tray?.setToolTip('Synapse · daemon stopped');
    }
  });

  return proc;
}

function formatDaemonStartupError(prefix: string): Error {
  const exitInfo =
    daemonLastExit !== null
      ? ` Last exit: code=${daemonLastExit.code}, signal=${daemonLastExit.signal}.`
      : '';
  const tail =
    daemonOutputTail.length > 0
      ? `\nRecent daemon output:\n${daemonOutputTail.join('\n')}`
      : '\nRecent daemon output: (none)';
  return new Error(`${prefix}${exitInfo}${tail}`);
}

async function waitForDaemon(timeoutMs = 15_000): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await probeHealth()) return;
    if (spawnedDaemon && daemonLastExit !== null) {
      throw formatDaemonStartupError('Daemon exited before /api/v1/health became ready.');
    }
    await new Promise((r) => setTimeout(r, 250));
  }
  throw formatDaemonStartupError(
    `Daemon did not respond to ${daemonUrl}/api/v1/health within ${timeoutMs}ms.`
  );
}

function probeHealth(): Promise<boolean> {
  return new Promise((resolve) => {
    const req = http.get(
      `${daemonUrl}/api/v1/health`,
      { timeout: 1000 },
      (res) => {
        res.resume();
        resolve(res.statusCode === 200);
      }
    );
    req.on('error', () => resolve(false));
    req.on('timeout', () => {
      req.destroy();
      resolve(false);
    });
  });
}

function waitForChildExit(proc: ChildProcess, timeoutMs: number): Promise<void> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      cleanup();
      reject(new Error(`Process ${proc.pid ?? 'unknown'} did not exit within ${timeoutMs}ms`));
    }, timeoutMs);

    const cleanup = (): void => {
      clearTimeout(timer);
      proc.removeListener('exit', onExit);
    };

    const onExit = (): void => {
      cleanup();
      resolve();
    };

    if (proc.exitCode !== null || proc.killed) {
      cleanup();
      resolve();
      return;
    }

    proc.once('exit', onExit);
  });
}

async function shutdownSpawnedDaemon(timeoutMs = 5_000): Promise<void> {
  if (!spawnedDaemon || daemonProc === null) return;

  const proc = daemonProc;
  if (proc.exitCode !== null) return;

  console.log('[synapse] terminating daemon child before restart/quit');
  try {
    proc.kill();
    await waitForChildExit(proc, timeoutMs);
  } catch (error) {
    console.error('[synapse] graceful daemon shutdown timed out, forcing kill:', error);
    if (process.platform === 'win32' && proc.pid) {
      spawnSync('taskkill', ['/PID', String(proc.pid), '/T', '/F'], { windowsHide: true });
      await waitForChildExit(proc, timeoutMs).catch(() => undefined);
    }
  }
}

// ── authenticated daemon requests (Milestone H/I) ─────────────────────────
// The daemon requires X-Synapse-Token on every data route. The main process
// now asks the daemon it's actually attached to for the trusted-local token
// instead of assuming the repo's data/auth-token file still matches.
function httpTextRequest(
  url: string,
  init: { method: string; timeout?: number; headers?: Record<string, string>; body?: string }
): Promise<{ statusCode: number; body: string }> {
  return new Promise((resolve, reject) => {
    const req = http.request(
      url,
      {
        method: init.method,
        timeout: init.timeout ?? 4000,
        headers: init.headers,
      },
      (res) => {
        let body = '';
        res.setEncoding('utf-8');
        res.on('data', (c) => (body += c));
        res.on('end', () => resolve({ statusCode: res.statusCode ?? 0, body }));
      }
    );
    req.on('error', reject);
    req.on('timeout', () => {
      req.destroy();
      reject(new Error('daemon request timed out'));
    });
    if (init.body) req.write(init.body);
    req.end();
  });
}

async function fetchDaemonLocalToken(forceRefresh = false): Promise<string> {
  if (!forceRefresh && daemonAuthToken) return daemonAuthToken;
  if (daemonAuthTokenPromise) return daemonAuthTokenPromise;

  daemonAuthTokenPromise = (async () => {
    const { statusCode, body } = await httpTextRequest(`${daemonUrl}/api/v1/auth/local-token`, {
      method: 'GET',
      headers: { Accept: 'application/json' },
    });
    if (statusCode >= 400) {
      throw new Error(`HTTP ${statusCode} on /auth/local-token`);
    }
    const parsed = body ? (JSON.parse(body) as { token?: unknown }) : {};
    if (typeof parsed.token !== 'string' || !parsed.token) {
      throw new Error('The daemon did not return a local auth token.');
    }
    daemonAuthToken = parsed.token;
    return parsed.token;
  })();

  try {
    return await daemonAuthTokenPromise;
  } finally {
    daemonAuthTokenPromise = null;
  }
}

async function daemonRequest<T = unknown>(
  method: string,
  apiPath: string,
  allowRefresh = true,
  payload?: unknown
): Promise<T> {
  let token: string | null = daemonAuthToken;
  if (!token) {
    try {
      token = await fetchDaemonLocalToken();
    } catch {
      token = null;
    }
  }

  const serialized = payload === undefined ? undefined : JSON.stringify(payload);
  const headers: Record<string, string> = token
    ? { 'X-Synapse-Token': token, Accept: 'application/json' }
    : { Accept: 'application/json' };
  if (serialized !== undefined) {
    headers['Content-Type'] = 'application/json';
    headers['Content-Length'] = String(Buffer.byteLength(serialized));
  }
  const { statusCode, body } = await httpTextRequest(`${daemonUrl}/api/v1${apiPath}`, {
    method,
    headers,
    body: serialized,
  });

  if (statusCode === 401 && allowRefresh) {
    daemonAuthToken = null;
    await fetchDaemonLocalToken(true);
    return daemonRequest<T>(method, apiPath, false, payload);
  }
  if (statusCode >= 400) {
    throw new Error(`HTTP ${statusCode} on ${apiPath}`);
  }

  return body ? (JSON.parse(body) as T) : (null as T);
}

interface DaemonRestartOperation {
  operation_id: string;
  source: string;
  status: 'requested' | 'restarting' | 'complete' | 'error';
}

async function registerRestartOperation(operationId: string, source: string): Promise<void> {
  await daemonRequest('POST', '/system/restart', true, {
    operation_id: operationId,
    source,
  });
}

async function reportRestartStage(
  operationId: string,
  stage: RestartStageKey,
  state: RestartStageState,
  detail: string,
  errorCode?: string,
  errorMessage?: string
): Promise<void> {
  await daemonRequest('POST', `/system/restart/${encodeURIComponent(operationId)}/stage`, true, {
    stage,
    state,
    detail,
    error_code: errorCode,
    error_message: errorMessage,
  });
}

async function syncRestartProgressToDaemon(progress: RestartProgress): Promise<void> {
  for (const stage of progress.stages) {
    if (stage.state === 'pending') continue;
    await reportRestartStage(
      progress.operationId,
      stage.key,
      stage.state,
      stage.detail,
      stage.errorCode,
      progress.errorMessage
    );
  }
}

async function pollForApiRestartRequest(): Promise<void> {
  if (restartInFlight) return;
  try {
    const response = await daemonRequest<{ operation: DaemonRestartOperation | null }>(
      'GET',
      '/system/restart'
    );
    const operation = response.operation;
    if (!operation || operation.status !== 'requested') return;
    if (handledRestartOperationId === operation.operation_id) return;
    handledRestartOperationId = operation.operation_id;
    await restartApp(operation.source || 'api', operation.operation_id);
  } catch {
    // The daemon can be between shutdown and startup; the visible restart
    // window owns that state, so polling simply resumes on the next tick.
  }
}

function bundleBootstrapFilePath(): string {
  return path.join(app.getPath('userData'), 'bootstrap-ai-bundles.json');
}

async function applyBootstrapAiBundles(): Promise<void> {
  const target = bundleBootstrapFilePath();
  if (!fs.existsSync(target)) return;

  let bundleIds: string[] = [];
  try {
    const raw = JSON.parse(fs.readFileSync(target, 'utf-8')) as { bundle_ids?: unknown };
    if (Array.isArray(raw.bundle_ids)) {
      bundleIds = raw.bundle_ids.filter((value): value is string => typeof value === 'string' && value.length > 0);
    }
  } catch (error) {
    console.error('[synapse] could not read bootstrap AI bundles file:', error);
  }

  try {
    for (const bundleId of bundleIds) {
      try {
        await daemonRequest('POST', `/ai-bundles/install/${encodeURIComponent(bundleId)}?force=true`);
      } catch (error) {
        console.error(`[synapse] failed to bootstrap AI bundle ${bundleId}:`, error);
      }
    }
  } finally {
    try {
      fs.unlinkSync(target);
    } catch (error) {
      console.error('[synapse] failed to remove bootstrap AI bundles file:', error);
    }
  }
}

// ── window + tray ─────────────────────────────────────────────────────────
function createWindow(): void {
  let interfaceReady = false;
  // A cold development restart may need to rebuild the renderer before the
  // first document can load. Keep the packaged-app diagnostic tight, but do
  // not flash a false SYN-BOOT-202 while Vite is still legitimately warming.
  const interfaceReadyTimeoutMs = isDev ? 45_000 : 20_000;
  const interfaceReadyTimer = setTimeout(() => {
    if (interfaceReady || !currentRestartProgress) return;
    setRestartStage(
      'interface',
      'error',
      `The interface did not become ready within ${interfaceReadyTimeoutMs / 1000} seconds.`,
      'SYN-BOOT-202'
    );
  }, interfaceReadyTimeoutMs);
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 960,
    minHeight: 600,
    show: false,
    backgroundColor: '#0b1020',
    autoHideMenuBar: true,
    icon: resolveIconPath(),
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
      webviewTag: true,
    },
  });

  // Contract #2 — hide-to-tray, only the tray menu's Quit actually exits.
  mainWindow.on('close', (event) => {
    if (!isQuitting) {
      event.preventDefault();
      mainWindow?.hide();
    }
  });
  mainWindow.on('closed', () => {
    mainWindow = null;
    clearTimeout(interfaceReadyTimer);
  });

  // External links open in the user's browser, not in an Electron window.
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    void shell.openExternal(url);
    return { action: 'deny' };
  });

  mainWindow.webContents.on('did-fail-load', (_event, code, description) => {
    if (code === -3) return; // navigation superseded/aborted
    setRestartStage(
      'interface',
      'error',
      `Interface load failed (${code}).`,
      'SYN-BOOT-201',
      description
    );
  });

  const markInterfaceReady = (): void => {
    if (interfaceReady) return;
    interfaceReady = true;
    clearTimeout(interfaceReadyTimer);
    mainWindow?.show();
    setRestartStage('interface', 'success', 'The Synapse interface is loaded and visible.');
    finishRestartWindow();
  };
  // `ready-to-show` is the preferred first-paint signal. Development restarts
  // can occasionally finish navigation without emitting it while the window is
  // initially hidden, so a successful document load is an idempotent fallback.
  // Register both before navigation begins so neither event can be missed.
  mainWindow.once('ready-to-show', markInterfaceReady);
  mainWindow.webContents.once('did-finish-load', markInterfaceReady);

  const loadPromise = isDev
    ? mainWindow.loadURL('http://localhost:5173')
    : mainWindow.loadFile(path.join(__dirname, '..', 'dist', 'index.html'));
  void loadPromise.catch((error) => {
    console.error('Failed to load Synapse interface:', error);
    setRestartStage(
      'interface',
      'error',
      'The Synapse interface could not be loaded.',
      'SYN-BOOT-201',
      error instanceof Error ? error.message : String(error)
    );
  });
}

function createTray(): void {
  const image = nativeImage.createFromPath(resolveIconPath());
  tray = new Tray(image);
  tray.setToolTip('Synapse · The WhatIf Company');
  tray.setContextMenu(buildTrayMenu());
  tray.on('click', () => showWindow());
  tray.on('double-click', () => showWindow());
}

// Build the tray context menu from the latest project snapshot (Milestone I).
function buildTrayMenu(): Electron.Menu {
  const projectItems: Electron.MenuItemConstructorOptions[] = trayProjects.length
    ? trayProjects.map((p) => ({
        label: p.name,
        type: 'checkbox',
        checked: p.status === 'launched' || p.status === 'stopping',
        click: () => onTrayProjectClick(p),
      }))
    : [{ label: 'No projects yet', enabled: false }];

  return Menu.buildFromTemplate([
    { label: 'Show Synapse', click: () => showWindow() },
    { label: 'Open mobile UI', click: () => void shell.openExternal(`${daemonUrl}/mobile`) },
    { type: 'separator' },
    { label: 'Projects', submenu: projectItems },
    { type: 'separator' },
    {
      label: 'Start with Windows',
      type: 'checkbox',
      checked: app.getLoginItemSettings().openAtLogin,
      click: (item) => setAutostart(item.checked),
    },
    {
      label: 'Daemon health',
      click: () => void shell.openExternal(`${daemonUrl}/api/v1/health`),
    },
    { type: 'separator' },
    {
      label: 'Restart Synapse',
      click: () => {
        void restartApp('tray');
      },
    },
    {
      label: 'Exit Synapse',
      click: () => {
        isQuitting = true;
        app.quit();
      },
    },
  ]);
}

/**
 * Clean restart: signal we're quitting (so will-quit kills the daemon child),
 * schedule a relaunch, then exit. The relaunched process picks up any
 * boot-config changes (e.g. the LAN-exposure toggle the user just flipped in
 * Settings → Network).
 */
async function restartApp(source = 'desktop', requestedOperationId?: string): Promise<boolean> {
  if (restartInFlight) {
    restartWindow?.show();
    restartWindow?.focus();
    console.warn('[synapse] SYN-RST-001: restart already in progress');
    return false;
  }
  restartInFlight = true;
  const operationId = requestedOperationId ?? `restart-${Date.now().toString(36)}-${process.pid}`;
  handledRestartOperationId = operationId;
  const progress = createRestartProgress('restart', operationId, source);
  showRestartWindow(progress);

  if (!requestedOperationId) {
    try {
      await registerRestartOperation(operationId, source);
    } catch (error) {
      let liveOperation: DaemonRestartOperation | null = null;
      try {
        const response = await daemonRequest<{ operation: DaemonRestartOperation | null }>(
          'GET',
          '/system/restart'
        );
        liveOperation = response.operation;
      } catch {
        // If the daemon itself is unavailable, continuing the local restart is
        // the recovery path. A reachable live operation is the only hard stop.
      }
      if (liveOperation?.status === 'requested' || liveOperation?.status === 'restarting') {
        setRestartStage(
          'request',
          'error',
          'Another Synapse restart is already in progress.',
          'SYN-RST-001',
          `Existing operation: ${liveOperation.operation_id}`
        );
        clearRestartMarker();
        restartInFlight = false;
        tray?.setToolTip('Synapse · restart already in progress (SYN-RST-001)');
        return false;
      }
      console.warn('[synapse] restart API registration unavailable; continuing locally:', error);
    }
  }
  setRestartStage('request', 'success', `Restart accepted from ${source}.`);
  setRestartStage('stop', 'active', 'Stopping the previous Synapse services…');
  await new Promise((resolve) => setTimeout(resolve, 400));

  if (isDev && process.env.SYNAPSE_DEV_WRAPPER === '1') {
    console.log('[synapse] requesting full wrapper restart');
    setRestartStage(
      'desktop',
      'active',
      'The development wrapper is restarting the daemon, interface server, and desktop process…'
    );
    isQuitting = true;
    await new Promise((resolve) => setTimeout(resolve, 650));
    app.exit(FULL_DEV_RESTART_EXIT_CODE);
    return true;
  }

  console.log('[synapse] restarting app');
  try {
    await shutdownSpawnedDaemon();
    if (spawnedDaemon && (await probeHealth())) {
      throw new Error('The previous daemon is still answering after the shutdown sequence.');
    }
    setRestartStage(
      'stop',
      'success',
      spawnedDaemon
        ? 'The previous Synapse daemon stopped cleanly.'
        : 'The shared Synapse daemon is healthy and did not require replacement.'
    );
    setRestartStage('desktop', 'active', 'Scheduling the new Synapse desktop process…');
    const relaunchArgs = process.argv
      .slice(1)
      .filter((value) => !value.startsWith('--synapse-restart='));
    relaunchArgs.push(`--synapse-restart=${operationId}`);
    app.relaunch({ args: relaunchArgs });
    isQuitting = true;
    await new Promise((resolve) => setTimeout(resolve, 650));
    app.exit(0);
    return true;
  } catch (error) {
    console.error('[synapse] restart failed:', error);
    const stage: RestartStageKey = currentRestartProgress?.stages.find(
      (item) => item.state === 'active'
    )?.key ?? 'desktop';
    const code = stage === 'stop' ? 'SYN-RST-101' : 'SYN-RST-201';
    setRestartStage(
      stage,
      'error',
      stage === 'stop' ? 'The previous services could not be stopped.' : 'The relaunch could not be scheduled.',
      code,
      error instanceof Error ? error.message : String(error)
    );
    clearRestartMarker();
    restartInFlight = false;
    isQuitting = false;
    tray?.setToolTip(`Synapse · restart failed (${code})`);
    restartWindow?.setClosable(true);
    return false;
  }
}

// A tray project click: launch it if idle, otherwise just surface the window.
function onTrayProjectClick(p: { id: string; status: string }): void {
  const running = p.status === 'launched' || p.status === 'stopping';
  if (running) {
    showWindow();
    return;
  }
  daemonRequest('POST', `/projects/${encodeURIComponent(p.id)}/launch`)
    .then(() => refreshTrayMenu())
    .catch((err) => console.error('[synapse] tray launch failed:', err));
}

// Pull the project list for the tray submenu, then rebuild the menu.
async function refreshTrayMenu(): Promise<void> {
  try {
    const res = await daemonRequest<{ projects: Array<{ id: string; name: string; status: string }> }>(
      'GET',
      '/projects'
    );
    trayProjects = (res?.projects ?? []).map((p) => ({
      id: p.id,
      name: p.name,
      status: p.status,
    }));
  } catch {
    // Daemon not ready / unreachable — keep the last snapshot.
  }
  tray?.setContextMenu(buildTrayMenu());
}

// Toggle the Windows login item (Milestone I — auto-start on login).
function setAutostart(enabled: boolean): void {
  app.setLoginItemSettings({ openAtLogin: enabled, args: [] });
}

function showWindow(): void {
  if (!mainWindow) {
    createWindow();
    return;
  }
  if (mainWindow.isMinimized()) mainWindow.restore();
  mainWindow.show();
  mainWindow.focus();
}

// ── IPC: open a path or URL from the renderer ─────────────────────────────
// The renderer's tile quick-actions call window.synapse.openExternal(target).
// A URL opens in the default browser; anything else is treated as a path and
// opened in the OS file manager.
ipcMain.handle('synapse:open-external', async (_event, target: unknown) => {
  if (typeof target !== 'string' || target.length === 0) {
    return { ok: false, error: 'No target provided.' };
  }
  try {
    if (/^[a-z]+:\/\//i.test(target)) {
      await shell.openExternal(target);
    } else {
      const err = await shell.openPath(target);
      if (err) return { ok: false, error: err };
    }
    return { ok: true };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : String(err) };
  }
});

// ── IPC: open a project in VS Code (v0.1.16) ──────────────────────────────
// Probe for the `code` CLI synchronously so the user gets a meaningful error
// when VS Code isn't installed instead of a silent no-op. Then spawn detached
// so it outlives Electron.
ipcMain.handle('synapse:open-in-vscode', async (_event, target: unknown) => {
  if (typeof target !== 'string' || !target) {
    return { ok: false, error: 'No path provided.' };
  }
  const cmd = process.platform === 'win32' ? 'code.cmd' : 'code';
  const useShell = process.platform === 'win32';

  // Quick existence probe -- "code --version" is fast (~50ms).
  const probe = spawnSync(cmd, ['--version'], {
    shell: useShell,
    windowsHide: true,
    timeout: 3000,
  });
  if (probe.error || probe.status !== 0) {
    return {
      ok: false,
      error:
        'VS Code CLI ("code") not found on PATH. Open VS Code, run ' +
        '"Shell Command: Install \'code\' command in PATH", then try again.',
    };
  }

  try {
    const child = spawn(cmd, [target], {
      detached: true,
      stdio: 'ignore',
      shell: useShell,
      windowsHide: true,
    });
    child.on('error', () => {
      /* probe passed, so this is unusual -- ignore silently */
    });
    child.unref();
    return { ok: true };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : String(err) };
  }
});

// ── IPC: open a project's folder in a terminal (v0.1.20) ──────────────────
// On Windows we prefer Windows Terminal (`wt.exe`, lands on a clean tab in the
// project folder); fall back to `cmd /K cd` if `wt` isn't on PATH.
ipcMain.handle('synapse:open-in-terminal', async (_event, target: unknown) => {
  if (typeof target !== 'string' || !target) {
    return { ok: false, error: 'No path provided.' };
  }

  if (process.platform === 'win32') {
    const wt = spawnSync('where', ['wt'], { shell: true, windowsHide: true, timeout: 1500 });
    const hasWt = wt.status === 0;
    try {
      if (hasWt) {
        spawn('wt.exe', ['-d', target], {
          detached: true, stdio: 'ignore', shell: false, windowsHide: true,
        }).unref();
      } else {
        // Fall back to a hidden parent that pops a regular cmd window in cwd.
        spawn('cmd.exe', ['/c', 'start', '""', 'cmd.exe', '/K', `cd /d "${target}"`], {
          detached: true, stdio: 'ignore', shell: false, windowsHide: true,
        }).unref();
      }
      return { ok: true };
    } catch (err) {
      return { ok: false, error: err instanceof Error ? err.message : String(err) };
    }
  }

  // macOS / Linux fall-through: shell out to the OS via `open -a Terminal`.
  const bin = process.platform === 'darwin' ? 'open' : 'x-terminal-emulator';
  const args = process.platform === 'darwin' ? ['-a', 'Terminal', target] : [];
  try {
    spawn(bin, args, { detached: true, stdio: 'ignore', cwd: target }).unref();
    return { ok: true };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : String(err) };
  }
});

// ── IPC: auto-start on Windows login (Milestone I) ────────────────────────
ipcMain.handle('synapse:get-autostart', () => app.getLoginItemSettings().openAtLogin);
ipcMain.handle('synapse:restart', () => restartApp('desktop'));
ipcMain.handle('synapse:exit', () => {
  isQuitting = true;
  app.quit();
  return true;
});

ipcMain.handle('synapse:set-autostart', (_event, enabled: unknown) => {
  setAutostart(enabled === true);
  // Reflect the change in the tray's checkbox too.
  tray?.setContextMenu(buildTrayMenu());
  return app.getLoginItemSettings().openAtLogin;
});

// ── app lifecycle ─────────────────────────────────────────────────────────
app.on('second-instance', () => {
  // Another launch attempt → focus the existing window.
  showWindow();
});

app.whenReady().then(async () => {
  app.on('web-contents-created', (_event, contents) => {
    contents.on('will-attach-webview', (event, webPreferences, params) => {
      delete webPreferences.preload;
      webPreferences.nodeIntegration = false;
      webPreferences.contextIsolation = true;
      webPreferences.sandbox = true;
      webPreferences.webSecurity = true;

      const src = typeof params.src === 'string' ? params.src : '';
      const partition =
        typeof params.partition === 'string' ? params.partition : '';
      if (
        partition !== 'persist:synapse-chatgpt' ||
        !shouldAllowEmbeddedChatgptUrl(src)
      ) {
        event.preventDefault();
      }
    });

    contents.setWindowOpenHandler(({ url }) => {
      if (contents.getType() === 'webview' && shouldKeepPopupInApp(url)) {
        return {
          action: 'allow',
          overrideBrowserWindowOptions: {
            autoHideMenuBar: true,
            width: 1200,
            height: 800,
            minWidth: 960,
            minHeight: 640,
            backgroundColor: '#0b1020',
            icon: resolveIconPath(),
            webPreferences: {
              contextIsolation: true,
              nodeIntegration: false,
              sandbox: false,
            },
          },
        };
      }
      void shell.openExternal(url);
      return { action: 'deny' };
    });
  });

  refuseAdminIfNeeded();
  const restoredRestart = loadRestartMarker();
  if (restoredRestart) {
    showRestartWindow(restoredRestart);
    if (restoredRestart.errorCode) {
      clearRestartMarker();
    } else {
      setRestartStage('stop', 'success', 'The previous Synapse processes have exited.');
      setRestartStage('desktop', 'success', 'The new Synapse desktop process is running.');
      setRestartStage('daemon', 'active', 'Checking the restarted Synapse services…');
    }
  } else {
    const startupProgress = createRestartProgress(
      'startup',
      `startup-${Date.now().toString(36)}-${process.pid}`,
      'startup'
    );
    showRestartWindow(startupProgress);
    setRestartStage('desktop', 'success', 'The Synapse desktop process is running.');
    setRestartStage('daemon', 'active', 'Starting Synapse services…');
  }
  let daemonBootError: Error | null = null;

  // Attach to a daemon that's already running (e.g. one that survived an
  // Electron crash, or was launched by synapse.cmd); otherwise spawn our own.
  if (await probeHealth()) {
    console.log('[synapse] a daemon is already running — attaching to it');
    spawnedDaemon = false;
  } else {
    try {
      daemonProc = spawnDaemon();
      spawnedDaemon = true;
    } catch (error) {
      daemonBootError = error instanceof Error ? error : new Error(String(error));
      console.error('[synapse] daemon failed to spawn:', daemonBootError);
      setRestartStage(
        'daemon',
        'error',
        'The Synapse daemon process could not be started.',
        'SYN-BOOT-101',
        daemonBootError.message
      );
    }
  }
  createTray();

  try {
    if (daemonBootError) {
      throw daemonBootError;
    }
    await waitForDaemon();
    await applyBootstrapAiBundles();
    console.log('[synapse] daemon ready');
    setRestartStage('daemon', 'success', 'Health check passed; Synapse services are running.');
    if (currentRestartProgress?.kind === 'restart') {
      await syncRestartProgressToDaemon(currentRestartProgress).catch((error) => {
        console.warn('[synapse] could not sync restart progress to daemon:', error);
      });
    }
    // Populate the tray's Projects submenu + keep it fresh.
    void refreshTrayMenu();
    trayRefreshTimer = setInterval(() => void refreshTrayMenu(), 20_000);
    void pollForApiRestartRequest();
    restartRequestPollTimer = setInterval(() => void pollForApiRestartRequest(), 1000);
  } catch (err) {
    console.error('[synapse] daemon failed to start:', err);
    if (!daemonBootError) {
      setRestartStage(
        'daemon',
        'error',
        'The Synapse daemon did not become healthy in time.',
        'SYN-BOOT-102',
        err instanceof Error ? err.message : String(err)
      );
    }
    tray?.setToolTip(
      `Synapse | daemon failed to start (${daemonBootError ? 'SYN-BOOT-101' : 'SYN-BOOT-102'})`
    );
    // Still open the window so the user can see the error state.
  }

  if (currentRestartProgress?.stages.some((stage) => stage.state === 'pending' && stage.key === 'interface')) {
    setRestartStage('interface', 'active', 'Loading the Synapse interface…');
  }
  createWindow();

  if (INSPECT_RENDERER) {
    console.log(
      `[synapse] renderer inspection enabled — CDP on http://localhost:${INSPECT_PORT}`
    );
  }
});

app.on('window-all-closed', () => {
  // Stay alive — the tray is the persistent surface. Only Quit Synapse exits.
});

app.on('before-quit', () => {
  isQuitting = true;
});

app.on('will-quit', () => {
  if (trayRefreshTimer) {
    clearInterval(trayRefreshTimer);
    trayRefreshTimer = null;
  }
  if (restartRequestPollTimer) {
    clearInterval(restartRequestPollTimer);
    restartRequestPollTimer = null;
  }
  // Only stop the daemon if *we* started it. If we attached to one that was
  // already running, leave it alone — something else owns its lifecycle.
  if (spawnedDaemon && daemonProc && !daemonProc.killed) {
    console.log('[synapse] terminating daemon child');
    try {
      daemonProc.kill();
    } catch (err) {
      console.error('[synapse] failed to kill daemon:', err);
    }
  }
});
