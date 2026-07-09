// Client for the Needs-Review / approval inbox (ADR-0016 Phase R). Types mirror
// daemon/synapse_daemon/review.py.

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

export type ProposalStatus = 'open' | 'approved' | 'rejected';

// AI-filed improvement idea awaiting your approve/reject (ADR-0025). Mirrors
// daemon/synapse_daemon/proposals.py::Proposal.
export interface Proposal {
  id: string;
  title: string;
  rationale_md: string;
  project_id: string | null;
  source_runtime: string;
  est_effort: string;
  est_token_cost: number;
  status: ProposalStatus;
  resolution_note: string;
  created_at: string;
  updated_at: string;
  resolved_at: string | null;
  metadata: Record<string, unknown>;
}

export interface ReviewInbox {
  items: ReviewItem[];
  count: number;
  proposals: Proposal[];
}

const p = encodeURIComponent;

export function getReviewInbox(): Promise<ReviewInbox> {
  return apiFetch<ReviewInbox>('/review/inbox', { method: 'GET' });
}

export function approveProposal(id: string, note = ''): Promise<unknown> {
  return apiFetch(`/review/proposals/${p(id)}/approve`, { method: 'POST', body: { note } });
}

export function rejectProposal(id: string, note = ''): Promise<unknown> {
  return apiFetch(`/review/proposals/${p(id)}/reject`, { method: 'POST', body: { note } });
}

// Approve + turn a project-scoped idea into an actionable backlog item.
export function promoteProposal(id: string): Promise<unknown> {
  return apiFetch(`/review/proposals/${p(id)}/promote`, { method: 'POST' });
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
