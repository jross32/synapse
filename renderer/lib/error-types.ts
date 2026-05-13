// Error types mirroring `daemon/synapse_daemon/errors.py` (Contract #4).
//
// This file is HAND-WRITTEN today; from Milestone B onwards it is regenerated
// by `scripts/gen-types.ps1`. Any drift between this file and the Pydantic
// model fails CI.

export interface ErrorEnvelope {
  /** Machine-readable code, namespaced by entity. e.g. "project.not_found". */
  code: string;
  /** Human-readable explanation; UI renders this directly. */
  message: string;
  /** Optional structured payload (validation errors, stack hash, etc.). */
  details?: Record<string, unknown> | null;
  /** If true, UI may offer a Retry button. */
  retryable?: boolean;
}

/** Type guard: does this object look like an ErrorEnvelope? */
export function isErrorEnvelope(value: unknown): value is ErrorEnvelope {
  if (typeof value !== 'object' || value === null) return false;
  const v = value as Record<string, unknown>;
  return typeof v.code === 'string' && typeof v.message === 'string';
}

/** Extract a readable line for logs/toasts. */
export function formatError(err: ErrorEnvelope): string {
  return `[${err.code}] ${err.message}`;
}
