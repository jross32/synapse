// Typed client for the daemon's system-level routes (v0.1.35).
//
// Today: network bind toggle (LAN exposure). Add more knobs to
// /api/v1/system as they get a UI.

import { apiFetch } from './api-client';

export interface NetworkStatus {
  bind_lan_persisted: boolean;
  wan_auto_start: boolean;
  mcp_writes_enabled: boolean;
  bound_host: string;
  bound_port: number;
  lan_ips: string[];
  mobile_urls: string[];
  loopback_url: string;
  restart_required: boolean;
}

export async function getNetworkStatus(): Promise<NetworkStatus> {
  return apiFetch<NetworkStatus>('/system/network', { method: 'GET' });
}

export async function patchNetworkBindLan(
  bindLan: boolean
): Promise<{ bind_lan_persisted: boolean; bound_host: string; restart_required: boolean }> {
  return apiFetch<{
    bind_lan_persisted: boolean;
    bound_host: string;
    restart_required: boolean;
  }>('/system/network', { method: 'PATCH', body: { bind_lan: bindLan } });
}

// Auto-open the Cloudtap WAN tunnel on daemon start (ADR-0026). Persisted server-side;
// takes effect on the next daemon start (no live restart needed to change the setting).
export async function patchNetworkWanAutoStart(
  wanAutoStart: boolean
): Promise<{ wan_auto_start: boolean }> {
  return apiFetch<{ wan_auto_start: boolean }>('/system/network', {
    method: 'PATCH',
    body: { wan_auto_start: wanAutoStart },
  });
}

/** Turn the MCP connector's write/dispatch tools on or off. Persisted, so it survives a
 *  restart - unlike the environment variable this replaced, which depended on whichever
 *  shell happened to launch the app. */
export function patchMcpWrites(enabled: boolean): Promise<{ mcp_writes_enabled: boolean }> {
  return apiFetch<{ mcp_writes_enabled: boolean }>('/system/network', {
    method: 'PATCH',
    body: JSON.stringify({ mcp_writes_enabled: enabled }),
  });
}
