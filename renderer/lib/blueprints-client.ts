/**
 * Blueprint catalog client.
 *
 * Mirrors `daemon/synapse_daemon/blueprints.py`. The manifest is deliberately readable by
 * both audiences — `guarantees` and `whatYouGet` are the fields a human scans, `provides`
 * and `requires` are the fields an AI queries — so the gallery and `/ai/context` describe
 * the same thing rather than drifting apart.
 */
import { apiFetch } from './api-client';

export interface BlueprintScore {
  total: number;
  max: number;
  percent: number;
  categories: Record<string, number>;
  measured_at: string;
  local_tokens: number;
  claude_tokens: number;
  seconds: number;
  escalations: string[];
}

export interface BlueprintPiece {
  name: string;
  spec: string;
  module: string;
  checks: string[];
  depends_on: string[];
  suggested_skill: string;
}

export interface Blueprint {
  id: string;
  name: string;
  kind: string;
  summary: string;
  what_you_get: string[];
  guarantees: string[];
  tags: string[];
  stack: string[];
  est_minutes: number;
  provides: string[];
  requires: string[];
  pieces: BlueprintPiece[];
  preview: string[];
  score: BlueprintScore | null;
  provenance: Record<string, unknown>;
  draft: boolean;
}

export interface Compatibility {
  satisfies_my_needs: string[];
  i_satisfy: string[];
  universal: string[];
}

export interface BuildPieceOutcome {
  name: string;
  passed: boolean;
  escalated: boolean;
  repairs: number;
  seconds: number;
  stop_reason: string;
  checks: Record<string, string>;
  escalation_packet: string;
}

export interface BuildResult {
  blueprint_id: string;
  workspace: string;
  pieces: BuildPieceOutcome[];
  passed: boolean;
  seconds: number;
  local_tokens: number;
  escalations: string[];
  notes: string[];
}

export async function listBlueprints(kind = ''): Promise<Blueprint[]> {
  const q = kind ? `?kind=${encodeURIComponent(kind)}` : '';
  return apiFetch<Blueprint[]>(`/blueprints${q}`, { method: 'GET' });
}

export async function getBlueprint(id: string): Promise<Blueprint> {
  return apiFetch<Blueprint>(`/blueprints/${encodeURIComponent(id)}`, { method: 'GET' });
}

export async function getCompatibility(id: string): Promise<Compatibility> {
  return apiFetch<Compatibility>(`/blueprints/${encodeURIComponent(id)}/compatible`, {
    method: 'GET',
  });
}

export async function buildBlueprint(
  id: string,
  body: { workspace?: string; model?: string; max_repairs?: number },
): Promise<BuildResult> {
  return apiFetch<BuildResult>(`/blueprints/${encodeURIComponent(id)}/build`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
}
