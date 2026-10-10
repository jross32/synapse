import { apiFetch, daemonBase, getAuthToken } from './api-client';

export interface ReleaseArtifact {
  platform: string;
  label: string;
  status: string;
  format: string;
  filename: string | null;
  size_bytes: number | null;
  sha256: string | null;
  download_url: string | null;
}

export interface ReleaseManifest {
  version: string;
  channel: string;
  artifacts: ReleaseArtifact[];
}

export function getReleaseManifest(): Promise<ReleaseManifest> {
  return apiFetch<ReleaseManifest>('/about/releases', { method: 'GET' });
}

/**
 * Desktop release downloads must carry the local daemon token. Passing an
 * unauthenticated localhost URL to Electron shell.openExternal gives a 401,
 * and passing a relative URL isn't a valid external navigation.
 *
 * Download only the authenticated, same-daemon allowlisted release route.
 * The server is authoritative about which filenames are actually published.
 */
export async function downloadReleaseArtifact(artifact: ReleaseArtifact): Promise<void> {
  const base = new URL(daemonBase());
  const path = artifact.download_url;
  const filename = artifact.filename;
  const token = getAuthToken();

  if (artifact.status !== 'ready' || !path || !filename || !token) {
    throw new Error('Release is unavailable or Synapse is not authenticated.');
  }
  if (filename !== filename.split(/[\\/]/).pop()) {
    throw new Error('Invalid release filename.');
  }

  const url = new URL(path, base);
  if (url.origin !== base.origin || !url.pathname.startsWith('/api/v1/about/download/')) {
    throw new Error('Untrusted release URL.');
  }

  const response = await fetch(url.href, {
    method: 'GET',
    headers: { 'X-Synapse-Token': token },
  });
  if (!response.ok) throw new Error(`Release download failed (HTTP ${response.status}).`);

  const blob = await response.blob();
  const blobUrl = URL.createObjectURL(blob);
  try {
    const anchor = document.createElement('a');
    anchor.href = blobUrl;
    anchor.download = filename;
    anchor.style.display = 'none';
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
  } finally {
    // Allow Electron/browser time to start reading the object URL.
    window.setTimeout(() => URL.revokeObjectURL(blobUrl), 120000);
  }
}
