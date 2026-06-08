// Thin wrapper over the Electron preload bridge (window.synapse).
//
// Everything here degrades gracefully when running in a plain browser
// (Vite dev / Playwright), where window.synapse is undefined.

interface SynapseBridge {
  version: () => string;
  daemonBase: () => string;
  daemonWsBase: () => string;
  platform: () => string;
  openExternal?: (target: string) => Promise<{ ok: boolean; error?: string }>;
  openInVscode?: (target: string) => Promise<{ ok: boolean; error?: string }>;
  openInTerminal?: (target: string) => Promise<{ ok: boolean; error?: string }>;
  getAutostart?: () => Promise<boolean>;
  setAutostart?: (enabled: boolean) => Promise<boolean>;
}

function bridge(): SynapseBridge | null {
  return (window as unknown as { synapse?: SynapseBridge }).synapse ?? null;
}

export function hasElectronBridge(): boolean {
  return bridge() !== null;
}

/** True if this build can manage the Windows login item (Electron only). */
export function canManageAutostart(): boolean {
  return typeof bridge()?.getAutostart === 'function';
}

/** True if the build can launch VS Code via the `code` CLI (Electron only). */
export function canOpenInVscode(): boolean {
  return typeof bridge()?.openInVscode === 'function';
}

/** True if the build can open a folder in a terminal (Electron only). */
export function canOpenInTerminal(): boolean {
  return typeof bridge()?.openInTerminal === 'function';
}

export async function openInTerminal(
  target: string
): Promise<{ ok: boolean; error?: string }> {
  const b = bridge();
  if (!b?.openInTerminal) {
    return { ok: false, error: 'Terminal launching is only available in the desktop app.' };
  }
  return b.openInTerminal(target);
}

/**
 * Open a folder in VS Code. Returns the IPC result so callers can surface
 * "code CLI not found" hints to the user.
 */
export async function openInVscode(
  target: string
): Promise<{ ok: boolean; error?: string }> {
  const b = bridge();
  if (!b?.openInVscode) {
    return { ok: false, error: 'VS Code launching is only available in the desktop app.' };
  }
  return b.openInVscode(target);
}

/** Read whether Synapse starts at login. Returns null outside Electron. */
export async function getAutostart(): Promise<boolean | null> {
  const b = bridge();
  return b?.getAutostart ? b.getAutostart() : null;
}

/** Enable/disable start-at-login; resolves to the resulting state. */
export async function setAutostart(enabled: boolean): Promise<boolean | null> {
  const b = bridge();
  return b?.setAutostart ? b.setAutostart(enabled) : null;
}

/**
 * Open a path (in the OS file manager) or a URL (in the default browser).
 * In Electron this goes through the main process; in a browser, only URLs
 * are honoured (via window.open).
 */
export async function openExternal(target: string): Promise<void> {
  const b = bridge();
  if (b?.openExternal) {
    await b.openExternal(target);
    return;
  }
  if (/^https?:\/\//i.test(target)) {
    window.open(target, '_blank', 'noopener');
  }
}
