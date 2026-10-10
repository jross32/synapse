import { apiFetch } from './api-client';
import { openClaudeLogin } from './electron-bridge';
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

export async function startClaudeLogin(): Promise<{started:boolean;message:string}> {
  const result = await openClaudeLogin();
  if (!result.ok) throw new Error(result.error || 'Could not open Claude sign-in.');
  return {started:true,message:'Finish Claude sign-in in the terminal/browser, then click Verify connection.'};
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

export interface DeviceAccessPolicy {
  device_id: string;
  remote_write_enabled: boolean;
  enrolled: boolean;
}

export async function getDeviceAccessPolicies(): Promise<DeviceAccessPolicy[]> {
  const response = await apiFetch<{ devices: DeviceAccessPolicy[] }>('/profile/devices/access');
  return response.devices;
}

export async function setDeviceRemoteWrite(deviceId: string, enabled: boolean): Promise<DeviceAccessPolicy> {
  return apiFetch<DeviceAccessPolicy>(`/profile/devices/${encodeURIComponent(deviceId)}/access`, {
    method: 'PUT', body: { remote_write_enabled: enabled },
  });
}
export interface AccountMcpLink {
  url: string;
  rotated: boolean;
  selected_device_id: string | null;
  note: string;
}

export async function getAccountMcpLink(): Promise<AccountMcpLink> {
  return apiFetch<AccountMcpLink>('/profile/mcp-link');
}

export async function rotateAccountMcpLink(): Promise<AccountMcpLink> {
  return apiFetch<AccountMcpLink>('/profile/mcp-link/rotate', { method: 'POST' });
}

export async function selectAccountMcpDevice(deviceId: string): Promise<void> {
  await apiFetch('/profile/mcp-link/device', { method: 'PUT', body: { device_id: deviceId } });
}

export interface McpConnections {
  primary: {configured:boolean; local_url:string|null; remote_url:string|null};
  device: {id:string; enabled:boolean; endpoint:string|null};
}
export async function getMcpConnections(): Promise<McpConnections> {
  return apiFetch<McpConnections>('/profile/mcp-connections', {method:'GET'});
}
export async function setMcpPreference(enabled:boolean): Promise<McpConnections> {
  return apiFetch<McpConnections>('/profile/mcp-connections', {method:'PATCH',body:{enabled}});
}
