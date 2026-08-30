import { apiFetch } from './api-client';

export type TraceEvent = {
  id: string;
  occurred_at: string;
  source: string;
  category: string;
  action: string;
  status: string;
  severity: string;
  summary: string;
  project_id: string | null;
  session_id: string | null;
  correlation_id: string | null;
  duration_ms: number | null;
  error_code: string | null;
  details: Record<string, unknown>;
};

export type TraceEventsResponse = {
  items: TraceEvent[];
  runtime_imported: Record<string, number>;
};

export type TraceRecommendation = {
  kind: string;
  priority: string;
  message: string;
};

export type TraceAnalysis = {
  window_hours: number;
  since: string;
  totals: {
    events: number;
    errors_warnings: number;
    recoveries: number;
    slow_operations: number;
  };
  status_counts: Record<string, number>;
  top_sources: Array<{ source: string; count: number }>;
  top_actions: Array<{ action: string; count: number }>;
  repeated_patterns: Array<{ source: string; action: string; summary: string; count: number }>;
  slow_operations: TraceEvent[];
  recent_incidents: TraceEvent[];
  recent_recoveries: TraceEvent[];
  recommendations: TraceRecommendation[];
  runtime_imported: Record<string, number>;
};

export async function fetchTraceEvents(params?: {
  limit?: number;
  category?: string;
  project_id?: string;
  source?: string;
  status?: string;
  sync_runtime?: boolean;
}): Promise<TraceEventsResponse> {
  const q = new URLSearchParams();
  if (params?.limit) q.set('limit', String(params.limit));
  if (params?.category) q.set('category', params.category);
  if (params?.project_id) q.set('project_id', params.project_id);
  if (params?.source) q.set('source', params.source);
  if (params?.status) q.set('status', params.status);
  if (params?.sync_runtime === false) q.set('sync_runtime', 'false');
  return apiFetch<TraceEventsResponse>('/trace/events' + (q.size ? '?' + q.toString() : ''), {
    method: 'GET',
    timeoutMs: 20_000,
  });
}

export async function fetchTraceAnalysis(windowHours = 24): Promise<TraceAnalysis> {
  return apiFetch<TraceAnalysis>(
    '/trace/analysis?window_hours=' + Math.max(1, Math.min(720, windowHours)),
    {
      method: 'GET',
      timeoutMs: 20_000,
    }
  );
}
