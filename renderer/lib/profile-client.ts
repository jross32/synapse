import { apiFetch } from './api-client';
import type {
  CatalogPreferenceItem,
  CatalogPreferenceState,
  HostPresence,
  ProfilePreferences,
  ProfileSummary,
  ServiceConnection,
} from './generated-types';

export interface ProfileConfigPayload {
  sync_enabled?: boolean | null;
}

export interface ProfileAuthPayload {
  login: string;
  password: string;
}

export interface ProfileSignUpPayload {
  username: string;
  email: string;
  password: string;
  display_name?: string | null;
}

export interface ProfileSignUpResponse {
  profile: ProfileSummary;
  notice: string | null;
}

export interface ProfileAuthStartResponse {
  url: string;
}

export interface ServiceConnectionsResponse {
  connections: ServiceConnection[];
}

export interface HostsResponse {
  hosts: HostPresence[];
}

export async function getProfile(): Promise<ProfileSummary> {
  return apiFetch<ProfileSummary>('/profile', { method: 'GET' });
}

export async function updateProfileConfig(payload: ProfileConfigPayload): Promise<ProfileSummary> {
  return apiFetch<ProfileSummary>('/profile', { method: 'PATCH', body: payload });
}

export async function getProfilePreferences(): Promise<ProfilePreferences> {
  return apiFetch<ProfilePreferences>('/profile/preferences', { method: 'GET' });
}

export async function updateProfilePreferences(
  payload: Partial<ProfilePreferences>
): Promise<ProfilePreferences> {
  return apiFetch<ProfilePreferences>('/profile/preferences', { method: 'PATCH', body: payload });
}

export async function signInProfile(payload: ProfileAuthPayload): Promise<ProfileSummary> {
  return apiFetch<ProfileSummary>('/profile/signin', { method: 'POST', body: payload });
}

export async function signUpProfile(payload: ProfileSignUpPayload): Promise<ProfileSignUpResponse> {
  return apiFetch<ProfileSignUpResponse>('/profile/signup', { method: 'POST', body: payload });
}

export async function startProfileAuth(provider: 'google' | 'github'): Promise<ProfileAuthStartResponse> {
  return apiFetch<ProfileAuthStartResponse>(`/profile/auth/start/${encodeURIComponent(provider)}`, {
    method: 'POST',
  });
}

export async function linkProfileAuth(provider: 'google' | 'github'): Promise<ProfileAuthStartResponse> {
  return apiFetch<ProfileAuthStartResponse>(
    `/profile/auth/start/${encodeURIComponent(provider)}?mode=link`,
    { method: 'POST' }
  );
}

export async function signOutProfile(): Promise<ProfileSummary> {
  return apiFetch<ProfileSummary>('/profile/signout', { method: 'POST' });
}

export async function unlinkProfileProvider(provider: string): Promise<ProfileSummary> {
  return apiFetch<ProfileSummary>(`/profile/providers/${encodeURIComponent(provider)}`, {
    method: 'DELETE',
  });
}

export async function getCatalogState(): Promise<CatalogPreferenceState> {
  return apiFetch<CatalogPreferenceState>('/profile/catalog-state', { method: 'GET' });
}

export async function setFavorite(
  kind: 'tool' | 'quick-action',
  itemId: string,
  favorite?: boolean
): Promise<CatalogPreferenceItem> {
  return apiFetch<CatalogPreferenceItem>(
    `/profile/favorites/${encodeURIComponent(kind)}/${encodeURIComponent(itemId)}`,
    { method: 'POST', body: { favorite } }
  );
}

export async function getServiceConnections(): Promise<ServiceConnection[]> {
  const res = await apiFetch<ServiceConnectionsResponse>('/profile/service-connections', { method: 'GET' });
  return res.connections;
}

export async function connectService(provider: string): Promise<ServiceConnection> {
  return apiFetch<ServiceConnection>(
    `/profile/service-connections/${encodeURIComponent(provider)}/connect`,
    { method: 'POST' }
  );
}

export async function verifyService(provider: string): Promise<ServiceConnection> {
  return apiFetch<ServiceConnection>(
    `/profile/service-connections/${encodeURIComponent(provider)}/verify`,
    { method: 'POST' }
  );
}

export async function deleteServiceConnection(connectionId: string): Promise<void> {
  await apiFetch<void>(
    `/profile/service-connections/${encodeURIComponent(connectionId)}`,
    { method: 'DELETE' }
  );
}

export async function getProfileHosts(): Promise<HostPresence[]> {
  const res = await apiFetch<HostsResponse>('/profile/hosts', { method: 'GET' });
  return res.hosts;
}
