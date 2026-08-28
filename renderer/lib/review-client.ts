// Client for human review plus the durable proposal backlog.

import { apiFetch } from './api-client';

export type ReviewKind = 'handoff' | 'blocked';

export interface ReviewItem {
  id: string;
  kind: ReviewKind;
  title: string;
  squad_id: string;
  squad_name: string;
  project_id: string;
  project_name: string | null;
  summary_md: string | null;
  blockers_md: string | null;
  files_touched: string[];
  suggested_next_role: string | null;
  assigned_role_id: string | null;
  pty_session_id: string | null;
  updated_at: string;
}

export type ProposalStatus = 'proposed' | 'in_progress' | 'done';
export type ProposalDecision = 'pending' | 'accepted' | 'declined';

export interface ProposalLifecycleEvidence {
  source: string;
  observed_at: string;
  detail: string;
  ref_id?: string | null;
  status?: string | null;
}

export interface Proposal {
  id: string;
  title: string;
  rationale_md: string;
  project_id: string | null;
  source_runtime: string;
  kind: string;
  est_effort: string;
  est_token_cost: number;
  status: ProposalStatus;
  decision: ProposalDecision;
  resolution_note: string;
  lifecycle_source: string;
  lifecycle_evidence: ProposalLifecycleEvidence[];
  created_at: string;
  updated_at: string;
  decision_at: string | null;
  started_at: string | null;
  done_at: string | null;
  resolved_at: string | null;
  metadata: Record<string, unknown>;
}

export interface ReviewInbox {
  items: ReviewItem[];
  count: number;
  quality_gates: Array<{ id: string; title: string; opened_at?: string }>;
  // Pending proposal decisions only. Use listProposals() for the complete backlog.
  proposals: Proposal[];
}

export interface ProposalListQuery {
  status?: ProposalStatus;
  decision?: ProposalDecision;
  kind?: string;
  project_id?: string;
  sort_by?: 'created_at' | 'updated_at' | 'title' | 'kind' | 'status' | 'decision';
  sort_dir?: 'asc' | 'desc';
}

const p = encodeURIComponent;

export function getReviewInbox(): Promise<ReviewInbox> {
  return apiFetch<ReviewInbox>('/review/inbox', { method: 'GET' });
}

export function listProposals(query: ProposalListQuery = {}): Promise<Proposal[]> {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== null && value !== '') params.set(key, String(value));
  }
  const suffix = params.size > 0 ? `?${params.toString()}` : '';
  return apiFetch<Proposal[]>(`/review/proposals${suffix}`, { method: 'GET' });
}

export function approveProposal(id: string, note = ''): Promise<Proposal> {
  return apiFetch<Proposal>(`/review/proposals/${p(id)}/approve`, { method: 'POST', body: { note } });
}

export function rejectProposal(id: string, note = ''): Promise<Proposal> {
  return apiFetch<Proposal>(`/review/proposals/${p(id)}/reject`, { method: 'POST', body: { note } });
}

export function updateProposalLifecycle(id: string, status: ProposalStatus, note = ''): Promise<Proposal> {
  return apiFetch<Proposal>(`/review/proposals/${p(id)}/lifecycle`, {
    method: 'PATCH',
    body: { status, note },
  });
}

// Accept + create an actionable project backlog item + mark implementation in progress.
export function promoteProposal(id: string): Promise<unknown> {
  return apiFetch(`/review/proposals/${p(id)}/promote`, { method: 'POST' });
}

export function reconcileProposals(): Promise<{ changed: Proposal[]; count: number }> {
  return apiFetch('/review/proposals/reconcile', { method: 'POST' });
}

export function approveReview(id: string): Promise<unknown> {
  return apiFetch(`/review/items/${p(id)}/approve`, { method: 'POST' });
}

export function reviseReview(id: string, note: string): Promise<unknown> {
  return apiFetch(`/review/items/${p(id)}/revise`, { method: 'POST', body: { note } });
}

export function rejectReview(id: string, note: string): Promise<unknown> {
  return apiFetch(`/review/items/${p(id)}/reject`, { method: 'POST', body: { note } });
}
