// REST client for the Synapse daemon (Contract #7).
//
// All requests go through `apiFetch`, which:
//   • prefixes paths with `/api/v1`
//   • parses JSON
//   • turns 4xx/5xx responses into thrown `ErrorEnvelope` objects
//
// Milestone B replaces the placeholder base URL with the value Electron
// passes through the preload bridge (so it works in packaged builds too).

import type { ErrorEnvelope } from './error-types';
import { isErrorEnvelope } from './error-types';

export const API_VERSION = 'v1' as const;
export const DEFAULT_DAEMON_BASE = 'http://localhost:7878' as const;
export const API_PREFIX = `/api/${API_VERSION}` as const;

let baseUrl: string = DEFAULT_DAEMON_BASE;

/** Override the daemon base URL (set by preload bridge once Electron is up). */
export function setDaemonBase(url: string): void {
  baseUrl = url.replace(/\/+$/, '');
}

export function daemonBase(): string {
  return baseUrl;
}

// ── auth token (Milestone H) ──────────────────────────────────────────────
//
// Every protected /api/v1 route needs an X-Synapse-Token. The desktop + dev
// browser bootstrap it from /auth/local-token (open to this machine only);
// a paired mobile device gets its own token via the pairing flow.

const TOKEN_HEADER = 'X-Synapse-Token';
let authToken: string | null = null;

export function setAuthToken(token: string | null): void {
  authToken = token;
}

export function getAuthToken(): string | null {
  return authToken;
}

/**
 * Fetch the daemon's local token (works from this machine only) and remember
 * it for every later request. Call once at startup before any protected call.
 */
export async function bootstrapLocalToken(): Promise<void> {
  const res = await apiFetch<{ token: string }>('/auth/local-token', { method: 'GET' });
  authToken = res.token;
}

export class SynapseApiError extends Error {
  public readonly envelope: ErrorEnvelope;
  public readonly status: number;

  constructor(envelope: ErrorEnvelope, status: number) {
    super(envelope.message);
    this.envelope = envelope;
    this.status = status;
  }
}

export interface ApiFetchOptions extends Omit<RequestInit, 'body'> {
  body?: unknown;
  /** Override the base URL for one request. Rarely needed. */
  base?: string;
}

export async function apiFetch<T = unknown>(
  path: string,
  options: ApiFetchOptions = {}
): Promise<T> {
  const { body, base, headers, ...rest } = options;
  const url = `${base ?? baseUrl}${API_PREFIX}${path.startsWith('/') ? path : `/${path}`}`;

  const init: RequestInit = {
    ...rest,
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
      ...(authToken ? { [TOKEN_HEADER]: authToken } : {}),
      ...(headers ?? {}),
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  };

  const res = await fetch(url, init);
  const text = await res.text();
  const parsed = text ? safeJson(text) : null;

  if (!res.ok) {
    if (isErrorEnvelope(parsed)) {
      throw new SynapseApiError(parsed, res.status);
    }
    throw new SynapseApiError(
      {
        code: 'http.unexpected',
        message: `HTTP ${res.status} ${res.statusText}`,
        details: parsed === null ? undefined : { body: parsed },
        retryable: res.status >= 500,
      },
      res.status
    );
  }

  return parsed as T;
}

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}
