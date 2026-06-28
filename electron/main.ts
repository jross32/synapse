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

const repoRoot = path.resolve(__dirname, '..');

const iconPath = path.join(__dirname, '..', 'electron', 'icons', 'synapse.ico');
const iconPathPackaged = path.join(process.resourcesPath ?? '', 'electron', 'icons', 'synapse.ico');

function resolveIconPath(): string {
  // In dev, __dirname is .../dist-electron, so the icons folder is at ../electron/icons/.
  // In packaged builds, electron-builder copies electron/icons/ into resources/.
  return app.isPackaged ? iconPathPackaged : iconPath;
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
  init: { method: string; timeout?: number; headers?: Record<string, string> }
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
  allowRefresh = true
): Promise<T> {
  let token: string | null = daemonAuthToken;
  if (!token) {
    try {
      token = await fetchDaemonLocalToken();
    } catch {
      token = null;
    }
  }

  const { statusCode, body } = await httpTextRequest(`${daemonUrl}/api/v1${apiPath}`, {
    method,
    headers: token ? { 'X-Synapse-Token': token, Accept: 'application/json' } : { Accept: 'application/json' },
  });

  if (statusCode === 401 && allowRefresh) {
    daemonAuthToken = null;
    await fetchDaemonLocalToken(true);
    return daemonRequest<T>(method, apiPath, false);
  }
  if (statusCode >= 400) {
    throw new Error(`HTTP ${statusCode} on ${apiPath}`);
  }

  return body ? (JSON.parse(body) as T) : (null as T);
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
    },
  });

  // Contract #2 — hide-to-tray, only the tray menu's Quit actually exits.
  mainWindow.on('close', (event) => {
    if (!isQuitting) {
      event.preventDefault();
      mainWindow?.hide();
    }
  });

  // External links open in the user's browser, not in an Electron window.
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    void shell.openExternal(url);
    return { action: 'deny' };
  });

  if (isDev) {
    mainWindow.loadURL('http://localhost:5173').catch((err) => {
      console.error('Failed to load Vite dev server:', err);
    });
  } else {
    mainWindow.loadFile(path.join(__dirname, '..', 'dist', 'index.html')).catch((err) => {
      console.error('Failed to load packaged renderer:', err);
    });
  }

  mainWindow.once('ready-to-show', () => mainWindow?.show());
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
      click: () => restartApp(),
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
function restartApp(): void {
  if (restartInFlight) return;
  restartInFlight = true;

  if (isDev && process.env.SYNAPSE_DEV_WRAPPER === '1') {
    console.log('[synapse] requesting full wrapper restart');
    isQuitting = true;
    app.exit(FULL_DEV_RESTART_EXIT_CODE);
    return;
  }

  console.log('[synapse] restarting app');
  isQuitting = true;
  void (async () => {
    try {
      await shutdownSpawnedDaemon();
      app.relaunch();
      app.exit(0);
    } catch (error) {
      console.error('[synapse] restart failed:', error);
      app.exit(1);
    }
  })();
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
ipcMain.handle('synapse:restart', () => {
  restartApp();
  return true;
});
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
  refuseAdminIfNeeded();
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
    // Populate the tray's Projects submenu + keep it fresh.
    void refreshTrayMenu();
    trayRefreshTimer = setInterval(() => void refreshTrayMenu(), 20_000);
  } catch (err) {
    console.error('[synapse] daemon failed to start:', err);
    tray?.setToolTip('Synapse | daemon failed to start');
    // Still open the window so the user can see the error state.
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
