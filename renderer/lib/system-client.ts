// Typed client for the daemon's system-level routes (v0.1.35).
//
// Today: network bind toggle (LAN exposure). Add more knobs to
// /api/v1/system as they get a UI.

import { apiFetch } from './api-client';

export interface NetworkStatus {
  bind_lan_persisted: boolean;
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
