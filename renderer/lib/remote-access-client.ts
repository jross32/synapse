import { apiFetch } from './api-client';

export interface RemoteAccessNetwork {
  bind_lan_persisted: boolean;
  bound_host: string;
  bound_port: number;
  lan_ips: string[];
  mobile_urls: string[];
  loopback_url: string;
  restart_required: boolean;
}

export interface RemoteAccessPairingCode {
  active: boolean;
  code: string | null;
  expires_at: string | null;
}

export interface RemoteAccessDevice {
  id: string;
  name: string;
  created_at: string;
  last_seen_at: string | null;
}

export interface RemoteAccessWanVerification {
  status: string;
  checked_at: string | null;
  health_url: string | null;
  mobile_url: string | null;
  health_ok: boolean;
  mobile_ok: boolean;
  failure_code: string | null;
  failure_message: string | null;
}

export interface RemoteAccessWan {
  available: boolean;
  active: boolean;
  tunnel_id: string | null;
  public_url: string | null;
  local_port: number | null;
  label: string | null;
  verification: RemoteAccessWanVerification;
}

export interface RemoteAccessStatus {
  computer_name: string;
  network: RemoteAccessNetwork;
  pairing_code: RemoteAccessPairingCode;
  paired_devices: RemoteAccessDevice[];
  wan: RemoteAccessWan;
}

export async function getRemoteAccessStatus(): Promise<RemoteAccessStatus> {
  return apiFetch<RemoteAccessStatus>('/remote-access', { method: 'GET' });
}
