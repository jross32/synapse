// Typed REST client for external-data imports (ADR-0003 Phase E · v0.1.33).
//
// Mirrors files-client's multipart upload path -- `apiFetch` JSON-encodes
// every body, which won't work for the export zip.

import {
  API_PREFIX,
  SynapseApiError,
  daemonBase,
  getAuthToken,
} from './api-client';
import type { ErrorEnvelope } from './error-types';

const TOKEN_HEADER = 'X-Synapse-Token';

export interface ChatgptImportFile {
  id: string;
  original_name: string;
  title: string;
  size_bytes: number;
  duplicate_of: string | null;
}

export interface ChatgptImportResponse {
  imported: number;
  duplicates: number;
  skipped_empty: number;
  project_id: string;
  files: ChatgptImportFile[];
  duplicate_names: string[];
  skipped_titles: string[];
  /** Set when the zip parsed but contained zero conversations. */
  note?: string;
}

function isErrorEnvelope(value: unknown): value is ErrorEnvelope {
  if (!value || typeof value !== 'object') return false;
  const v = value as Record<string, unknown>;
  return typeof v.code === 'string' && typeof v.message === 'string';
}

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

/**
 * POST a ChatGPT ``export.zip`` to the daemon. The daemon lazy-creates the
 * ``imported-chatgpt`` project on the first call and lands every conversation
 * inside it as a Markdown file (source='chatgpt-import').
 */
export async function importChatgpt(file: File): Promise<ChatgptImportResponse> {
  const url = `${daemonBase()}${API_PREFIX}/imports/chatgpt`;
  const form = new FormData();
  form.append('file', file, file.name);

  const token = getAuthToken();
  const headers: Record<string, string> = { Accept: 'application/json' };
  if (token) headers[TOKEN_HEADER] = token;

  const res = await fetch(url, { method: 'POST', headers, body: form });
  const text = await res.text();
  const parsed = text ? safeJson(text) : null;
  if (!res.ok) {
    if (isErrorEnvelope(parsed)) throw new SynapseApiError(parsed, res.status);
    throw new SynapseApiError(
      {
        code: 'http.unexpected',
        message: `HTTP ${res.status} ${res.statusText}`,
        retryable: res.status >= 500,
      },
      res.status
    );
  }
  return parsed as ChatgptImportResponse;
}
