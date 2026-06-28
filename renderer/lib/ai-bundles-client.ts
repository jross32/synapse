import { apiFetch } from './api-client';

export interface AiBundleAssetRef {
  kind: string;
  id: string;
  label: string;
  summary: string;
}

export interface AiBundleOverlap {
  bundle_id: string;
  similarity_percent: number;
  summary: string;
  complementary: boolean;
}

export interface AiBundleEfficiency {
  quality_gain_summary: string;
  token_savings_summary: string;
  speed_gain_summary: string;
  best_for: string[];
  caveats: string[];
}

export interface AiBundleQuickAction {
  id: string;
  name: string;
  description: string;
  prompt: string;
  icon?: string | null;
  category?: string | null;
  tags: string[];
  default_argv: string[];
}

export interface AiBundleCatalogItem {
  id: string;
  name: string;
  publisher: string;
  version: string;
  description: string;
  featured: boolean;
  verified: boolean;
  sort_rank: number;
  tags: string[];
  recommended_case_modes: string[];
  recommended_mission_profiles: string[];
  asset_refs: AiBundleAssetRef[];
  overlap_report: AiBundleOverlap[];
  efficiency: AiBundleEfficiency;
  roles: Array<{ id: string; name: string }>;
  personalities: Array<{ id?: string | null; name: string }>;
  components: Array<{ id: string; name: string }>;
  recipes: Array<{ id: string; name: string }>;
  sources: Array<{ id: string; label: string }>;
  quick_actions: AiBundleQuickAction[];
  notes_md: string;
  installed: boolean;
}

export interface AiBundleCatalogResponse {
  catalog: AiBundleCatalogItem[];
  installed_ids: string[];
  installed: Record<string, unknown>;
}

export async function fetchAiBundles(): Promise<AiBundleCatalogResponse> {
  return apiFetch<AiBundleCatalogResponse>('/ai-bundles', { method: 'GET' });
}

export async function installAiBundle(bundleId: string, force = false): Promise<unknown> {
  const params = force ? '?force=true' : '';
  return apiFetch(`/ai-bundles/install/${encodeURIComponent(bundleId)}${params}`, {
    method: 'POST',
  });
}

export async function uninstallAiBundle(bundleId: string): Promise<unknown> {
  return apiFetch(`/ai-bundles/install/${encodeURIComponent(bundleId)}`, {
    method: 'DELETE',
  });
}
