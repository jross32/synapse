// Typed REST client for the tool marketplace (v0.1.23 · ADR-0001 step 3).

import { apiFetch } from './api-client';
import type { MarketplaceResponse } from './generated-types';

/** Fetch the registry index + installed-ids overlay. */
export async function fetchMarketplace(refresh = false): Promise<MarketplaceResponse> {
  const params = refresh ? '?refresh=true' : '';
  return apiFetch<MarketplaceResponse>(`/marketplace${params}`, { method: 'GET' });
}
