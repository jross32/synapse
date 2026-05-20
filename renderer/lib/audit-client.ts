// Typed REST client for the audit log (Contract #11 · v0.1.17).

import { apiFetch } from './api-client';
import type { AuditListResponse } from './generated-types';

export async function listAudit(limit = 100, offset = 0): Promise<AuditListResponse> {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  return apiFetch<AuditListResponse>(`/audit?${params}`, { method: 'GET' });
}
