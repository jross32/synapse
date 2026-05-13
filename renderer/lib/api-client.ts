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
