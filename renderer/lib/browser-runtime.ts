import {
  bootstrapLocalToken,
  getAuthToken,
  setAuthToken,
  setDaemonBase,
} from './api-client';
import { hasElectronBridge } from './electron-bridge';

const MOBILE_TOKEN_KEY = 'synapse.deviceToken';
const MOBILE_DEVICE_KEY = 'synapse.deviceIdentity';

let pendingClaim: string | null = null;

export type RuntimeAuthMode =
  | 'local'
  | 'paired-device'
  | 'pair-required'
  | 'reconnect-required'
  | 'claiming';

export interface StoredDeviceIdentity {
  id: string;
  name: string;
  computerName: string | null;
  lastConnectedAt: string;
}

export function isMobileRoute(): boolean {
  if (typeof window === 'undefined') return false;
  return window.location.pathname.startsWith('/mobile');
}

export function isTunnelOrigin(): boolean {
  if (typeof window === 'undefined') return false;
  return /\.trycloudflare\.com$/i.test(window.location.hostname);
}

export function currentBrowserBaseUrl(): string {
  if (typeof window === 'undefined' || hasElectronBridge()) return 'http://localhost:7878';
  if (window.location.protocol !== 'http:' && window.location.protocol !== 'https:') {
    return 'http://localhost:7878';
  }
  const host = window.location.hostname.toLowerCase();
  const isLocalDevHost = host === 'localhost' || host === '127.0.0.1' || host === '::1';
  if (isLocalDevHost && window.location.port === '5173') {
    return `${window.location.protocol}//${window.location.hostname}:7878`;
  }
  return window.location.origin;
}

function sameOrigin(url: string): boolean {
  if (typeof window === 'undefined') return false;
  try {
    return new URL(url).origin === window.location.origin;
  } catch {
    return false;
  }
}

function consumeAuthHandoff(): { token: string | null; claim: string | null } {
  if (typeof window === 'undefined') return { token: null, claim: null };
  const hash = window.location.hash.startsWith('#')
    ? window.location.hash.slice(1)
    : window.location.hash;
  if (!hash) return { token: null, claim: null };
  const params = new URLSearchParams(hash);
  const token = params.get('synapseToken');
  const claim = params.get('synapseClaim');
  if (!token && !claim) return { token: null, claim: null };
  if (window.history?.replaceState) {
    window.history.replaceState(null, '', window.location.pathname + window.location.search);
  } else {
    window.location.hash = '';
  }
  if (claim) pendingClaim = claim;
  return { token, claim };
}

export function getStoredDeviceToken(): string | null {
  if (typeof window === 'undefined') return null;
  try {
    return window.localStorage.getItem(MOBILE_TOKEN_KEY);
  } catch {
    return null;
  }
}

export function getStoredDeviceIdentity(): StoredDeviceIdentity | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = window.localStorage.getItem(MOBILE_DEVICE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<StoredDeviceIdentity>;
    if (
      typeof parsed.id !== 'string' ||
      typeof parsed.name !== 'string' ||
      typeof parsed.lastConnectedAt !== 'string'
    ) {
      return null;
    }
    return {
      id: parsed.id,
      name: parsed.name,
      computerName:
        typeof parsed.computerName === 'string' && parsed.computerName ? parsed.computerName : null,
      lastConnectedAt: parsed.lastConnectedAt,
    };
  } catch {
    return null;
  }
}

export function rememberDeviceToken(
  token: string,
  identity?: { id: string; name: string; computerName?: string | null }
): void {
  setAuthToken(token);
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(MOBILE_TOKEN_KEY, token);
    if (identity) {
      window.localStorage.setItem(
        MOBILE_DEVICE_KEY,
        JSON.stringify({
          id: identity.id,
          name: identity.name,
          computerName: identity.computerName ?? null,
          lastConnectedAt: new Date().toISOString(),
        } satisfies StoredDeviceIdentity)
      );
    }
  } catch {
    /* storage blocked -- keep the in-memory token */
  }
}

export function clearDeviceToken(): void {
  setAuthToken(null);
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.removeItem(MOBILE_TOKEN_KEY);
  } catch {
    /* storage blocked */
  }
}

export function forgetDeviceToken(): void {
  clearDeviceToken();
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.removeItem(MOBILE_DEVICE_KEY);
  } catch {
    /* storage blocked */
  }
}

export function getPendingPairClaim(): string | null {
  return pendingClaim;
}

export function clearPendingPairClaim(): void {
  pendingClaim = null;
}

export async function bootstrapRuntimeAuth(): Promise<RuntimeAuthMode> {
  if (hasElectronBridge()) {
    await bootstrapLocalToken();
    return 'local';
  }

  const handoff = consumeAuthHandoff();
  const claimReady = !!handoff.claim || !!pendingClaim;

  if (isMobileRoute()) {
    setDaemonBase(currentBrowserBaseUrl());
    if (claimReady) return 'claiming';
    const token = handoff?.token ?? getStoredDeviceToken();
    if (!token) {
      return getStoredDeviceIdentity() ? 'reconnect-required' : 'pair-required';
    }
    rememberDeviceToken(token);
    return 'paired-device';
  }

  try {
    await bootstrapLocalToken();
    return 'local';
  } catch {
    if (claimReady) return 'claiming';
    const token = handoff?.token ?? getStoredDeviceToken();
    if (!token) return getStoredDeviceIdentity() ? 'reconnect-required' : 'pair-required';
    setDaemonBase(currentBrowserBaseUrl());
    rememberDeviceToken(token);
    return 'paired-device';
  }
}

export function mobileTunnelUrl(
  publicUrl: string,
  localPort: number | string | null | undefined
): string | null {
  if (Number(localPort) !== 7878 || sameOrigin(publicUrl)) return null;
  const base = String(publicUrl).replace(/\/+$/, '');
  return `${base}/mobile`;
}

export function projectBrowserUrl(port: number | null | undefined): string | null {
  if (port === null || port === undefined) return null;
  if (hasElectronBridge()) return `http://localhost:${port}`;
  if (typeof window === 'undefined') return `http://localhost:${port}`;
  if (isTunnelOrigin()) return null;
  return `${window.location.protocol}//${window.location.hostname}:${port}`;
}
