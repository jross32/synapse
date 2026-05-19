// Typed REST client for the tool plugin endpoints (Milestone F · v0.1.9).
//
// One thin function per endpoint in routes_tools.py. Errors surface as
// `SynapseApiError` carrying an `ErrorEnvelope` (Contract #4).

import { apiFetch } from './api-client';
import type { AuditSource } from './projects-client';
import type { ToolEntry, ToolListResponse } from './generated-types';

export async function listTools(): Promise<ToolEntry[]> {
  const res = await apiFetch<ToolListResponse>('/tools', { method: 'GET' });
  return res.tools;
}

export async function getTool(id: string): Promise<ToolEntry> {
  return apiFetch<ToolEntry>(`/tools/${encodeURIComponent(id)}`, { method: 'GET' });
}

/**
 * Run one manifest action. `itemId` targets a single live instance for
 * item-scoped actions (e.g. close one Cloudtap tunnel); omit it for
 * tool-scoped actions. Returns the tool's new entry.
 */
export async function runToolAction(
  toolId: string,
  actionId: string,
  fields: Record<string, unknown>,
  itemId?: string,
  source: AuditSource = 'desktop'
): Promise<ToolEntry> {
  return apiFetch<ToolEntry>(
    `/tools/${encodeURIComponent(toolId)}/actions/${encodeURIComponent(actionId)}`,
    { method: 'POST', body: { fields, item_id: itemId ?? null, source } }
  );
}
