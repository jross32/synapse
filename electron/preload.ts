// Synapse preload bridge.
//
// Exposes a minimal, typed surface to the renderer over contextBridge.
// Everything goes through `window.synapse.*`; raw Node APIs are NOT exposed.

import { contextBridge } from 'electron';

const DAEMON_BASE = 'http://127.0.0.1:7878';

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
