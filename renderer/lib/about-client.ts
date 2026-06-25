// Client for the What's New + Roadmap surface (ADR-0019). Types mirror
// daemon/synapse_daemon/about.py.

import { apiFetch } from './api-client';

export interface ChangelogSection {
  title: string;
  items: string[];
}

export interface ChangelogVersion {
  version: string;
  date: string | null;
  summary: string;
  sections: ChangelogSection[];
}

export interface Changelog {
  versions: ChangelogVersion[];
}

export type RoadmapStatus = 'shipped' | 'in_progress' | 'coming';

export interface RoadmapItem {
  id: string;
  title: string;
  status: RoadmapStatus;
  summary: string;
  phase: string | null;
  adr: string | null;
}

export interface Roadmap {
  generated_at: string | null;
  items: RoadmapItem[];
}

export function getChangelog(): Promise<Changelog> {
  return apiFetch<Changelog>('/about/changelog', { method: 'GET' });
}

export function getRoadmap(): Promise<Roadmap> {
  return apiFetch<Roadmap>('/about/roadmap', { method: 'GET' });
}
