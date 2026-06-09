// Typed REST client for the tool marketplace (v0.1.23 / v0.1.24 · ADR-0001).

import { apiFetch } from './api-client';
import type {
  InstallReport,
  MarketplaceResponse,
  UninstallReport,
} from './generated-types';

/** Fetch the registry index + installed-ids overlay. */
export async function fetchMarketplace(refresh = false): Promise<MarketplaceResponse> {
  const params = refresh ? '?refresh=true' : '';
  return apiFetch<MarketplaceResponse>(`/marketplace${params}`, { method: 'GET' });
}

/** Install a tool by id. The daemon writes the manifest + hot reload fires. */
export async function installTool(id: string, force = false): Promise<InstallReport> {
  const params = force ? '?force=true' : '';
  return apiFetch<InstallReport>(
    `/marketplace/install/${encodeURIComponent(id)}${params}`,
    { method: 'POST' }
  );
}

/** Uninstall a tool by id. Removes its manifest; built-in handlers stay. */
export async function uninstallTool(id: string): Promise<UninstallReport> {
  return apiFetch<UninstallReport>(
    `/marketplace/install/${encodeURIComponent(id)}`,
    { method: 'DELETE' }
  );
}
