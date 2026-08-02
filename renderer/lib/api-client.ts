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
let localTokenRefresh: Promise<string> | null = null;

export function setAuthToken(token: string | null): void {
  authToken = token;
}

export function getAuthToken(): string | null {
  return authToken;
}

function canAttemptLocalTokenBootstrap(base: string): boolean {
  try {
    const url = new URL(base);
    const host = url.hostname.toLowerCase();
    return host === 'localhost' || host === '127.0.0.1' || host === '::1';
  } catch {
    return false;
  }
}

/**
 * Fetch the daemon's local token (works from this machine only) and remember
 * it for every later request. Call once at startup before any protected call.
 */
export async function bootstrapLocalToken(): Promise<void> {
  if (!canAttemptLocalTokenBootstrap(baseUrl)) {
    throw new Error('The local auth token is only available on this computer.');
  }
  authToken = await fetchLocalToken(baseUrl);
}

/**
 * Best-effort token refresh for desktop / trusted-local callers.
 *
 * Returns false when the current origin is not allowed to read the local token
 * (for example a paired phone over LAN/WAN) or when the daemon is unavailable.
 */
export async function tryRefreshLocalToken(base: string = baseUrl): Promise<boolean> {
  if (!canAttemptLocalTokenBootstrap(base)) return false;
  try {
    authToken = await fetchLocalToken(base);
    return true;
  } catch {
    return false;
  }
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
  /**
   * Abort the request after this many ms. `0` disables the timeout entirely.
   * Defaults to {@link DEFAULT_GET_TIMEOUT_MS} for reads and to no timeout for
   * anything that mutates -- see the note on that constant.
   */
  timeoutMs?: number;
}

/**
 * How long a read may hang before we call it a failure (Design Contract #13:
 * "no spinner that never resolves").
 *
 * When the daemon wedged, every panel sat on "Loading..." indefinitely with no
 * way to tell what was wrong -- the failure was silent rather than actionable.
 *
 * This deliberately applies to **GET only**. Reads are idempotent, so aborting
 * one is safe and re-running it is free. Mutating calls are left untimed on
 * purpose: several are legitimately slow (an MCP marketplace install allows
 * 600s server-side, a Cloudtap tunnel waits up to 25s for its URL, an antivirus
 * scan 30s), and aborting a POST mid-flight tells you nothing about whether the
 * side effect already happened. A generous 30s still never fires on a healthy
 * daemon -- typical panel reads return in well under a second -- so in practice
 * it only trips when something is genuinely wrong.
 */
export const DEFAULT_GET_TIMEOUT_MS = 30_000;

/** Thrown when a request exceeded its timeout rather than failing on the wire. */
export class SynapseTimeoutError extends Error {
  readonly timeoutMs: number;

  constructor(path: string, timeoutMs: number) {
    // Render sub-second budgets as ms -- rounding them to seconds prints
    // "did not respond within 0s", which reads like a bug in the message itself.
    const budget = timeoutMs < 1000 ? `${timeoutMs}ms` : `${Math.round(timeoutMs / 1000)}s`;
    super(
      `Synapse did not respond within ${budget} (${path}). ` +
        'The daemon may be busy, restarting, or another Synapse may be running on this port.'
    );
    this.name = 'SynapseTimeoutError';
    this.timeoutMs = timeoutMs;
  }
}

export async function apiFetch<T = unknown>(
  path: string,
  options: ApiFetchOptions = {}
): Promise<T> {
  return apiFetchInternal(path, options, true);
}

async function apiFetchInternal<T = unknown>(
  path: string,
  options: ApiFetchOptions,
  allowLocalRefresh: boolean
): Promise<T> {
  const { body, base, headers, timeoutMs, ...rest } = options;
  const url = `${base ?? baseUrl}${API_PREFIX}${path.startsWith('/') ? path : `/${path}`}`;

  // Reads time out; writes do not. See DEFAULT_GET_TIMEOUT_MS for why.
  const method = (rest.method ?? 'GET').toUpperCase();
  const effectiveTimeout = timeoutMs ?? (method === 'GET' ? DEFAULT_GET_TIMEOUT_MS : 0);

  const controller = effectiveTimeout > 0 ? new AbortController() : null;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let timedOut = false;
  if (controller) {
    timer = setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, effectiveTimeout);
    // Respect a caller's own signal too -- ours must add a deadline, not replace it.
    const callerSignal = rest.signal;
    if (callerSignal) {
      if (callerSignal.aborted) controller.abort();
      else callerSignal.addEventListener('abort', () => controller.abort(), { once: true });
    }
  }

  const init: RequestInit = {
    ...rest,
    credentials: rest.credentials ?? 'include',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
      ...(authToken ? { [TOKEN_HEADER]: authToken } : {}),
      ...(headers ?? {}),
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
    ...(controller ? { signal: controller.signal } : {}),
  };

  let res: Response;
  try {
    res = await fetch(url, init);
  } catch (err) {
    // Distinguish "we gave up waiting" from "the caller cancelled" and from a
    // genuine network error, so the UI can say something true.
    if (timedOut) throw new SynapseTimeoutError(path, effectiveTimeout);
    throw err;
  } finally {
    if (timer !== undefined) clearTimeout(timer);
  }
  const text = await res.text();
  const parsed = text ? safeJson(text) : null;

  if (!res.ok) {
    if (res.status === 401 && allowLocalRefresh && path !== '/auth/local-token') {
      const refreshed = await tryRefreshLocalToken(base ?? baseUrl);
      if (refreshed) {
        return apiFetchInternal<T>(path, options, false);
      }
    }
    // Auth-bootstrap probes (`/pair/resume`, `/auth/local-token`) return 401 to
    // mean "no resumable session", NOT "your session was lost". Dispatching the
    // global unauthorized event for them creates a feedback loop: the handler
    // re-attempts resume, that 401s, which dispatches again, ~90x/sec. Skip them.
    const isAuthBootstrapPath = path === '/auth/local-token' || path === '/pair/resume';
    if (res.status === 401 && typeof window !== 'undefined' && !isAuthBootstrapPath) {
      window.dispatchEvent(
        new CustomEvent('synapse:unauthorized', { detail: { status: res.status } })
      );
    }
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

async function fetchLocalToken(base: string): Promise<string> {
  if (localTokenRefresh) return localTokenRefresh;

  localTokenRefresh = (async () => {
    const res = await fetch(`${base}${API_PREFIX}/auth/local-token`, {
      method: 'GET',
      credentials: 'include',
      headers: { Accept: 'application/json' },
    });
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

    if (
      typeof parsed !== 'object' ||
      parsed === null ||
      typeof (parsed as { token?: unknown }).token !== 'string' ||
      !(parsed as { token: string }).token
    ) {
      throw new Error('The daemon did not return a local auth token.');
    }

    return (parsed as { token: string }).token;
  })();

  try {
    return await localTokenRefresh;
  } finally {
    localTokenRefresh = null;
  }
}

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}
