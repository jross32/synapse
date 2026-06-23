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

export interface PairResult {
  token: string;
  device: PairedDevice;
  computer_name: string;
}

export interface HandoffClaim {
  claim: string;
  claim_id: string;
  expires_at: string;
  device: PairedDevice;
  computer_name: string;
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

export async function redeemPairingCode(
  code: string,
  deviceName: string,
  deviceId?: string | null
): Promise<PairResult> {
  return apiFetch<PairResult>('/pair', {
    method: 'POST',
    body: { code, device_name: deviceName, device_id: deviceId ?? null },
  });
}

export async function resumeDeviceSession(): Promise<PairResult> {
  return apiFetch<PairResult>('/pair/resume', {
    method: 'POST',
  });
}

export async function createHandoffClaim(deviceId?: string): Promise<HandoffClaim> {
  return apiFetch<HandoffClaim>('/pair/handoff', {
    method: 'POST',
    body: { device_id: deviceId ?? null },
  });
}

export async function redeemHandoffClaim(claim: string): Promise<PairResult> {
  return apiFetch<PairResult>('/pair/claim', {
    method: 'POST',
    body: { claim },
  });
}
