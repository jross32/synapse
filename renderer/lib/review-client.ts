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

export interface ReviewInbox {
  items: ReviewItem[];
  count: number;
}

const p = encodeURIComponent;

export function getReviewInbox(): Promise<ReviewInbox> {
  return apiFetch<ReviewInbox>('/review/inbox', { method: 'GET' });
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
