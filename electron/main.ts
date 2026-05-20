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

const repoRoot = path.resolve(__dirname, '..');

const iconPath = path.join(__dirname, '..', 'electron', 'icons', 'synapse.png');
const iconPathPackaged = path.join(process.resourcesPath ?? '', 'electron', 'icons', 'synapse.png');

function resolveIconPath(): string {
  // In dev, __dirname is .../dist-electron, so the icons folder is at ../electron/icons/.
  // In packaged builds, electron-builder copies electron/icons/ into resources/.
  return app.isPackaged ? iconPathPackaged : iconPath;
}

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
function spawnDaemon(): ChildProcess {
  const cwd = path.resolve(__dirname, '..');
  const args = ['-m', 'synapse_daemon', '--port', String(daemonPort), '--data-dir', 'data'];

  console.log(`[synapse] spawning daemon: python ${args.join(' ')}  (cwd=${cwd})`);

  const proc = spawn('python', args, {
    cwd,
    stdio: ['ignore', 'pipe', 'pipe'],
    // detached: false in dev so the daemon dies with us cleanly.
    // Milestone J flips this so the daemon survives UI death.
    detached: false,
    windowsHide: true,
  });

  proc.stdout?.on('data', (chunk: Buffer) => {
    process.stdout.write(`[daemon] ${chunk.toString()}`);
  });
  proc.stderr?.on('data', (chunk: Buffer) => {
    process.stderr.write(`[daemon] ${chunk.toString()}`);
  });
  proc.on('exit', (code, signal) => {
    console.log(`[synapse] daemon exited (code=${code}, signal=${signal})`);
    daemonProc = null;
    if (!isQuitting) {
      // The daemon should outlive the UI; if it died unexpectedly, surface
      // the failure in the tray tooltip rather than silently broken state.
      tray?.setToolTip('Synapse · daemon stopped');
    }
  });

  return proc;
}

async function waitForDaemon(timeoutMs = 15_000): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await probeHealth()) return;
    await new Promise((r) => setTimeout(r, 250));
  }
  throw new Error(`Daemon did not respond to ${daemonUrl}/api/v1/health within ${timeoutMs}ms`);
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

// ── authenticated daemon requests (Milestone H/I) ─────────────────────────
// The daemon requires X-Synapse-Token on every data route. The main process
// reads the local token straight off disk — it lives on the same machine.
function readAuthToken(): string | null {
  try {
    const token = fs.readFileSync(path.join(repoRoot, 'data', 'auth-token'), 'utf-8').trim();
    return token || null;
  } catch {
    return null;
  }
}

function daemonRequest<T = unknown>(
  method: string,
  apiPath: string
): Promise<T> {
  return new Promise((resolve, reject) => {
    const token = readAuthToken();
    const req = http.request(
      `${daemonUrl}/api/v1${apiPath}`,
      {
        method,
        timeout: 4000,
        headers: token ? { 'X-Synapse-Token': token, Accept: 'application/json' } : {},
      },
      (res) => {
        let body = '';
        res.setEncoding('utf-8');
        res.on('data', (c) => (body += c));
        res.on('end', () => {
          if (res.statusCode && res.statusCode >= 400) {
            reject(new Error(`HTTP ${res.statusCode} on ${apiPath}`));
            return;
          }
          try {
            resolve(body ? (JSON.parse(body) as T) : (null as T));
          } catch (err) {
            reject(err instanceof Error ? err : new Error(String(err)));
          }
        });
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
      label: 'Quit Synapse',
      click: () => {
        isQuitting = true;
        app.quit();
      },
    },
  ]);
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

// ── IPC: auto-start on Windows login (Milestone I) ────────────────────────
ipcMain.handle('synapse:get-autostart', () => app.getLoginItemSettings().openAtLogin);

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

  // Attach to a daemon that's already running (e.g. one that survived an
  // Electron crash, or was launched by synapse.cmd); otherwise spawn our own.
  if (await probeHealth()) {
    console.log('[synapse] a daemon is already running — attaching to it');
    spawnedDaemon = false;
  } else {
    daemonProc = spawnDaemon();
    spawnedDaemon = true;
  }
  createTray();

  try {
    await waitForDaemon();
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
