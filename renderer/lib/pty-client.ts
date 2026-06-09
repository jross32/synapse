// Typed REST client for PTY sessions (v0.1.26 · ADR-0002 Phase A step 2).
//
// Live output rides the WebSocket bus (v1.pty.session_output) — see
// SessionTerminal.tsx. These calls are the control plane: spawn, list,
// keystrokes, resize, close.

import { apiFetch } from './api-client';
import type {
  PtySessionDetail,
  PtySessionListResponse,
  PtySessionSummary,
  PtySpawnRequest,
} from './generated-types';

export async function listSessions(): Promise<PtySessionSummary[]> {
  const res = await apiFetch<PtySessionListResponse>('/pty', { method: 'GET' });
  return res.sessions;
}

export interface PtyProbeResult {
  cmd: string;
  available: boolean;
  resolved: string | null;
}

/** Cheap check before spawning so we can offer an Install dialog if the
 *  binary isn't on PATH yet. */
export async function probeCommand(cmd: string): Promise<PtyProbeResult> {
  const params = new URLSearchParams({ cmd });
  return apiFetch<PtyProbeResult>(`/pty/probe?${params}`, { method: 'GET' });
}

export async function spawnSession(req: PtySpawnRequest): Promise<PtySessionSummary> {
  return apiFetch<PtySessionSummary>('/pty', { method: 'POST', body: req });
}

export async function getSession(id: string): Promise<PtySessionDetail> {
  return apiFetch<PtySessionDetail>(`/pty/${encodeURIComponent(id)}`, { method: 'GET' });
}

/** Send keystrokes / paste content. Either `text` or base64-encoded `data`. */
export async function writeInput(
  id: string,
  body: { text?: string; data?: string }
): Promise<{ ok: boolean; bytes: number }> {
  return apiFetch(`/pty/${encodeURIComponent(id)}/input`, { method: 'POST', body });
}

export async function resizeSession(
  id: string,
  rows: number,
  cols: number
): Promise<PtySessionSummary> {
  return apiFetch<PtySessionSummary>(`/pty/${encodeURIComponent(id)}/resize`, {
    method: 'POST',
    body: { rows, cols },
  });
}

export async function closeSession(id: string): Promise<void> {
  await apiFetch<void>(`/pty/${encodeURIComponent(id)}`, { method: 'DELETE' });
}
