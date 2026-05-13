// Universal search client (Contract #21).
//
// Wraps `GET /api/v1/search?q=...` for the Ctrl+K command palette.
// Daemon endpoint lands in Milestone B; the client interface ships now so
// the palette UI can be built against a typed API.

import { apiFetch } from './api-client';

export type SearchEntityType = 'project' | 'tool' | 'action' | 'setting';

export interface SearchHit {
  entity_type: SearchEntityType;
  entity_id: string;
  name: string;
  description?: string | null;
  score: number;
  /** Optional UI route the palette navigates to on Enter. */
  href?: string | null;
  /** Optional category badge ("Tools", "Apps", "Settings"). */
  badge?: string | null;
}

export interface SearchResponse {
  query: string;
  hits: SearchHit[];
  took_ms: number;
}

export async function search(query: string, limit = 20): Promise<SearchResponse> {
  const trimmed = query.trim();
  if (!trimmed) {
    return { query: trimmed, hits: [], took_ms: 0 };
  }
  const params = new URLSearchParams({ q: trimmed, limit: String(limit) });
  return apiFetch<SearchResponse>(`/search?${params.toString()}`, { method: 'GET' });
}

/** Lower-cased alphanumeric token splitter — identical to the daemon. */
const TOKEN_PATTERN = /[a-z0-9]+/g;

export function tokenise(text: string): string[] {
  return text.toLowerCase().match(TOKEN_PATTERN) ?? [];
}
