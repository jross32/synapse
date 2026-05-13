// Milestone A — minimal preload. Expanded in Milestone C with real daemon RPC bridge.

import { contextBridge } from 'electron';

contextBridge.exposeInMainWorld('synapse', {
  version: (): string => '0.1.0-alpha.1',
});
