// Synapse preload bridge.
//
// Exposes a minimal, typed surface to the renderer over contextBridge.
// Everything goes through `window.synapse.*`; raw Node APIs are NOT exposed.

import { contextBridge } from 'electron';

// Must match the host whitelisted in renderer/index.html's CSP connect-src.
// Use "localhost" (not 127.0.0.1) so the REST + WS origins line up with the
// CSP; a mismatch here silently CSP-blocks every fetch with "Failed to fetch".
const DAEMON_BASE = 'http://localhost:7878';

contextBridge.exposeInMainWorld('synapse', {
  /** UI version string baked into the Electron bundle. */
  version: (): string => process.env.npm_package_version ?? '0.1.4',

  /** Base URL of the local daemon. The renderer's api-client uses this. */
  daemonBase: (): string => DAEMON_BASE,

  /** Where to point the renderer's WS client at. */
  daemonWsBase: (): string => DAEMON_BASE.replace(/^http/, 'ws'),

  /** Platform info for the renderer's About dialog (Milestone F). */
  platform: (): NodeJS.Platform => process.platform,
});

declare global {
  interface Window {
    synapse: {
      version: () => string;
      daemonBase: () => string;
      daemonWsBase: () => string;
      platform: () => NodeJS.Platform;
    };
  }
}
