import type { AiBundleCatalogItem } from './ai-bundles-client';
import { apiFetch } from './api-client';

export interface AiFactoryComponent {
  id: string;
  family: string;
  name: string;
  description: string;
  tags: string[];
  metadata: Record<string, unknown>;
  content_md: string;
  builtin: boolean;
  source_id?: string | null;
}

export interface AiFactoryRecipe {
  id: string;
  name: string;
  description: string;
  archetype: string;
  nav_model: string;
  interaction_model: string;
  visual_language: string;
  data_behavior: string;
  density_rule: string;
  component_ids: string[];
  default_directives: Record<string, unknown>;
  tags: string[];
  builtin: boolean;
}

export interface AiFactorySource {
  id: string;
  label: string;
  source_type: string;
  url?: string | null;
  reuse_posture: string;
  provenance_summary: string;
  metadata: Record<string, unknown>;
  notes_md: string;
  builtin: boolean;
}

export interface AiFactoryCatalogResponse {
  catalog: {
    components: AiFactoryComponent[];
    recipes: AiFactoryRecipe[];
    sources: AiFactorySource[];
  };
  counts: {
    components: number;
    recipes: number;
    sources: number;
    installed_bundles: number;
  };
  bundles: AiBundleCatalogItem[];
  mission_profiles: Array<{
    id: string;
    title: string;
    summary: string;
    case_mode: string;
    tags: string[];
  }>;
  recent_cases: any[];
}

export async function getAiFactoryCatalog(): Promise<AiFactoryCatalogResponse> {
  return apiFetch<AiFactoryCatalogResponse>('/ai-factory/catalog', { method: 'GET' });
}
