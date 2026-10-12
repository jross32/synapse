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

export interface DeviceParityResult {
  source_host_id: string;
  destination_host_id: string;
  items: Array<{item_key: string; kind: string; item_id: string; status: string; installed_here: boolean}>;
  complete_inventory: boolean;
  automatic_install_available: boolean;
  limitations: string[];
}
export async function getDeviceParity(sourceHostId: string): Promise<DeviceParityResult> {
  return apiFetch<DeviceParityResult>(`/profile/device-parity/${encodeURIComponent(sourceHostId)}`, { method: 'GET' });
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

export interface McpConnections {
  primary: {configured:boolean; local_url:string|null; remote_url:string|null; remote_hostname?:string|null};
  device: {id:string; enabled:boolean; endpoint:string|null; remote_endpoint?:string|null};
}
export interface McpProbeResult {ok:boolean; status:number|null; ms:number|null; server_version:string|null; error:string|null}
export interface McpConnectionCheck {account:McpProbeResult; local:McpProbeResult; remote:McpProbeResult; checked_at:string}
/** The account-wide MCP URL hosted by Synapse accounts (Railway); same on every signed-in computer. */
export interface AccountMcpConnector {url:string|null; selected_device_id:string|null; this_device_id:string|null; error:string|null}
export async function getAccountMcpConnector(): Promise<AccountMcpConnector> {
  return apiFetch<AccountMcpConnector>('/profile/mcp-connections/account', {method:'GET'});
}
export async function routeAccountMcpToDevice(deviceId?:string): Promise<AccountMcpConnector> {
  return apiFetch<AccountMcpConnector>('/profile/mcp-connections/account/selection', {method:'PUT', body:{device_id: deviceId ?? null}});
}
export async function rotateAccountMcpConnector(): Promise<AccountMcpConnector> {
  return apiFetch<AccountMcpConnector>('/profile/mcp-connections/account/rotate', {method:'POST'});
}
export async function getMcpConnections(): Promise<McpConnections> {
  return apiFetch<McpConnections>('/profile/mcp-connections', {method:'GET'});
}
export async function checkMcpConnections(): Promise<McpConnectionCheck> {
  return apiFetch<McpConnectionCheck>('/profile/mcp-connections/check', {method:'POST'});
}
/** Show an MCP URL with its bearer token masked: the token is the only credential. */
export function maskMcpUrl(url:string): string {
  return url.replace(/\/([A-Za-z0-9_-]{16,})$/, (_m, token:string) => `/${token.slice(0, 4)}…`);
}
export async function setMcpPreference(enabled:boolean): Promise<McpConnections> {
  return apiFetch<McpConnections>('/profile/mcp-connections', {method:'PATCH',body:{enabled}});
}
