// Typed REST client for snapshot / restore (Contract #28 · v0.1.10.5).

import { apiFetch } from './api-client';
import type { RestoreReport, SnapshotPayload } from './generated-types';

/** Export the whole project registry as a portable snapshot. */
export async function exportSnapshot(): Promise<SnapshotPayload> {
  return apiFetch<SnapshotPayload>('/snapshot', { method: 'GET' });
}

/** Merge a snapshot back into the registry (create new, update existing). */
export async function restoreSnapshot(payload: SnapshotPayload): Promise<RestoreReport> {
  return apiFetch<RestoreReport>('/restore', { method: 'POST', body: payload });
}
