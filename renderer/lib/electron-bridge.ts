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
}

function bridge(): SynapseBridge | null {
  return (window as unknown as { synapse?: SynapseBridge }).synapse ?? null;
}

export function hasElectronBridge(): boolean {
  return bridge() !== null;
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
