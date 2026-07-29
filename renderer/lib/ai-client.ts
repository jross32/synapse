import { apiFetch } from './api-client';

export interface AiHealthAuditEntry {
  id: number;
  at: string;
  entity_type: string;
  entity_id: string;
  action: string;
  source: string;
  result: string;
  error_code: string | null;
  details: Record<string, unknown> | null;
}

export interface AiHealthBrowserProof {
  id: string;
  subject_type: string;
  subject_id: string;
  evidence_kind: string;
  label: string;
  route: string | null;
  verdict: string;
  artifact_path: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface AiHealthLatestReviewPass {
  id: string;
  thread_id: string;
  thread_title: string;
  project_id: string | null;
  title: string;
  summary_md: string;
  updated_at: string;
}

export interface AiHealthReport {
  version: string;
  uptime_s: number;
  daemon: {
    schema_migration: number;
    contracts_honoured: number[];
  };
  projects: {
    total: number;
    launched: number;
    errored: number;
  };
  audit_tail: AiHealthAuditEntry[];
  tests: {
    last_run_ok: boolean | null;
    last_run_at: string | null;
    passed: number;
    failed: number;
    skipped: number;
    mode: string | null;
  };
  git: {
    branch?: string;
    head?: string;
    ahead?: number;
    behind?: number;
    repo_path?: string;
    synapse_dev_enabled?: boolean;
  };
  quality: {
    open_count: number;
    blocking_count: number;
    open_gates: Array<Record<string, unknown>>;
    failing_contracts: Array<Record<string, unknown>>;
    latest_browser_proof: AiHealthBrowserProof[];
  };
  review: {
    latest_successful_pass: AiHealthLatestReviewPass | null;
  };
}

export function getAiHealthReport(): Promise<AiHealthReport> {
  return apiFetch<AiHealthReport>('/ai/health-report', { method: 'GET' });
}
