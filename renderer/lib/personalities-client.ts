// Client for AI personalities (ADR-0018 MW3). Types mirror
// daemon/synapse_daemon/personalities.py.

import { apiFetch } from './api-client';

export interface Personality {
  id: string;
  name: string;
  blurb: string;
  traits: string[];
  prompt_preamble_md: string;
  voice: string | null;
  builtin: boolean;
  sort_order: number;
  created_at: string;
  updated_at: string;
}

export interface PersonalityCreate {
  id?: string | null;
  name: string;
  blurb?: string;
  traits?: string[];
  prompt_preamble_md?: string;
  voice?: string | null;
  sort_order?: number;
}

export type PersonalityUpdate = Partial<Omit<PersonalityCreate, 'id'>>;

interface PersonalityListResponse {
  personalities: Personality[];
}

export function listPersonalities(): Promise<Personality[]> {
  return apiFetch<PersonalityListResponse>('/personalities', { method: 'GET' }).then((r) => r.personalities);
}

export function createPersonality(body: PersonalityCreate): Promise<Personality> {
  return apiFetch<Personality>('/personalities', { method: 'POST', body });
}

export function updatePersonality(id: string, body: PersonalityUpdate): Promise<Personality> {
  return apiFetch<Personality>(`/personalities/${id}`, { method: 'PATCH', body });
}

export function deletePersonality(id: string): Promise<void> {
  return apiFetch<void>(`/personalities/${id}`, { method: 'DELETE' });
}
