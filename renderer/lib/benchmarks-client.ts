import { apiFetch } from './api-client';

export interface BenchmarkScenario {
  id: string;
  spec_id: string;
  name: string;
  description: string;
  version: string;
  prompt_md: string;
  time_budget_seconds: number;
  objective_weight: number;
  rubric_weight: number;
}

export interface BenchmarkSpecBundle {
  spec: {
    id: string;
    name: string;
    description: string;
    primary_surface: string;
    default_repeat_count: number;
  };
  scenarios: BenchmarkScenario[];
}

export interface BenchmarkRunSummary {
  id: string;
  spec_id: string;
  project_id?: string | null;
  title: string;
  status: string;
  execution_mode: string;
  repeat_count: number;
  updated_at: string;
}

export interface BenchmarkRunDetail {
  run: BenchmarkRunSummary;
  report: {
    run: BenchmarkRunSummary;
    official_quality_ranking: Array<Record<string, unknown>>;
    efficiency_frontier: Array<Record<string, unknown>>;
    composite_score: Array<Record<string, unknown>>;
    strict_comparable_attempt_ids: string[];
    comparisons: Array<Record<string, unknown>>;
    all_attempts: Array<Record<string, unknown>>;
    lessons: Record<string, unknown>;
  };
  artifacts: Record<string, Array<Record<string, unknown>>>;
}

export interface BenchmarkRunCreatePayload {
  spec_id: string;
  project_id?: string | null;
  title: string;
  execution_mode?: 'serial' | 'concurrent';
  repeat_count?: number;
  notes_md?: string;
  matrix: Array<{
    scenario_id: string;
    runtime_id: string;
    provider?: string;
    model?: string;
    surface_kind: 'direct_cli' | 'synapse_coder_thread' | 'synapse_workbench' | 'synapse_raw_pty';
    argv?: string[];
    metadata?: Record<string, unknown>;
  }>;
  metadata?: Record<string, unknown>;
}

export async function listBenchmarkSpecs(): Promise<{ specs: BenchmarkSpecBundle[] }> {
  return apiFetch<{ specs: BenchmarkSpecBundle[] }>('/benchmarks/specs', { method: 'GET' });
}

export async function listBenchmarkRuns(): Promise<{ runs: BenchmarkRunSummary[] }> {
  return apiFetch<{ runs: BenchmarkRunSummary[] }>('/benchmarks/runs', { method: 'GET' });
}

export async function createBenchmarkRun(payload: BenchmarkRunCreatePayload): Promise<BenchmarkRunSummary> {
  return apiFetch<BenchmarkRunSummary>('/benchmarks/runs', { method: 'POST', body: payload });
}

export async function getBenchmarkRun(runId: string): Promise<BenchmarkRunDetail> {
  return apiFetch<BenchmarkRunDetail>(`/benchmarks/runs/${encodeURIComponent(runId)}`, { method: 'GET' });
}

export async function launchBenchmarkRun(runId: string, body: Record<string, unknown> = {}): Promise<any> {
  return apiFetch(`/benchmarks/runs/${encodeURIComponent(runId)}/launch`, { method: 'POST', body });
}

export async function rescoreBenchmarkRun(runId: string): Promise<any> {
  return apiFetch(`/benchmarks/runs/${encodeURIComponent(runId)}/rescore`, { method: 'POST' });
}

export async function exportBenchmarkRun(runId: string): Promise<{
  json_path: string;
  md_path: string;
  lessons_path: string;
}> {
  return apiFetch(`/benchmarks/runs/${encodeURIComponent(runId)}/export`, { method: 'POST' });
}
