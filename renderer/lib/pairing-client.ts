// Typed REST client for device pairing (Milestone H · v0.1.11).

import { apiFetch } from './api-client';

export interface PairedDevice {
  id: string;
  name: string;
  created_at: string;
  last_seen_at: string | null;
}

export interface PairingCode {
  code: string;
  expires_at: string; // ISO 8601 UTC
}

/** Mint a fresh pairing code for a phone to redeem. */
export async function issuePairingCode(): Promise<PairingCode> {
  return apiFetch<PairingCode>('/pair/code', { method: 'POST' });
}

export async function listPairedDevices(): Promise<PairedDevice[]> {
  const res = await apiFetch<{ devices: PairedDevice[] }>('/pair/devices', {
    method: 'GET',
  });
  return res.devices;
}

export async function revokePairedDevice(id: string): Promise<void> {
  await apiFetch<void>(`/pair/devices/${encodeURIComponent(id)}`, { method: 'DELETE' });
}
