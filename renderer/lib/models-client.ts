// Client for the local-model marketplace (ADR-0014 Phase M). Types mirror
// daemon/synapse_daemon/model_market.py.

import { apiFetch } from './api-client';

export type PullStatus = 'queued' | 'downloading' | 'success' | 'error' | 'canceled';

export interface ModelCatalogEntry {
  id: string;
  name: string;
  publisher: string | null;
  description: string;
  parameter_size: string | null;
  size_label: string | null;
  tags: string[];
  recommended: boolean;
  installed: boolean;
}

export interface ModelCatalog {
  version: number;
  generated_at: string | null;
  models: ModelCatalogEntry[];
}

export interface ModelPullState {
  name: string;
  status: PullStatus;
  completed: number;
  total: number;
  percent: number;
  detail: string | null;
  error: string | null;
  updated_at: string;
}

export interface ModelPullList {
  pulls: ModelPullState[];
}

export function getModelRegistry(): Promise<ModelCatalog> {
  return apiFetch<ModelCatalog>('/models/registry', { method: 'GET' });
}

export function listModelPulls(): Promise<ModelPullList> {
  return apiFetch<ModelPullList>('/models/pulls', { method: 'GET' });
}

export function pullModel(name: string): Promise<ModelPullState> {
  return apiFetch<ModelPullState>('/models/pull', { method: 'POST', body: { name } });
}

export function cancelModelPull(name: string): Promise<{ canceled: boolean }> {
  return apiFetch<{ canceled: boolean }>('/models/pull/cancel', { method: 'POST', body: { name } });
}

export function removeModel(name: string): Promise<{ deleted: boolean }> {
  return apiFetch<{ deleted: boolean }>('/models/remove', { method: 'POST', body: { name } });
}
