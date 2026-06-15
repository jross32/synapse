// Typed REST client for project files (ADR-0003 Phase A · v0.1.31).
//
// `apiFetch` always sets Content-Type: application/json and JSON.stringifys
// the body, which doesn't work for multipart uploads. We bypass it for the
// POST and reuse the same daemon base + auth token machinery.

import {
  API_PREFIX,
  SynapseApiError,
  apiFetch,
  daemonBase,
  getAuthToken,
} from './api-client';
import type {
  ErrorEnvelope,
  ProjectFile,
  ProjectFilesListResponse,
  UploadFilesResponse,
} from './generated-types';

const TOKEN_HEADER = 'X-Synapse-Token';

function isErrorEnvelope(value: unknown): value is ErrorEnvelope {
  if (!value || typeof value !== 'object') return false;
  const v = value as Record<string, unknown>;
  return typeof v.code === 'string' && typeof v.message === 'string';
}

/** Per-project list (project_id !== null). */
export async function listProjectFiles(projectId: string): Promise<ProjectFile[]> {
  const res = await apiFetch<ProjectFilesListResponse>(
    `/projects/${encodeURIComponent(projectId)}/files`,
    { method: 'GET' }
  );
  return res.files;
}

/** Shared scope (project_id IS NULL on the daemon side). */
export async function listSharedFiles(): Promise<ProjectFile[]> {
  const res = await apiFetch<ProjectFilesListResponse>('/files', { method: 'GET' });
  return res.files;
}

/**
 * Upload one or more files. Per-project unless ``projectId`` is null, in
 * which case the daemon stores them under the shared workspace.
 *
 * The daemon's POST takes multipart/form-data with field name ``files``
 * (repeated for batches). We stream each File object through directly --
 * no extra in-memory copy here.
 */
export async function uploadFiles(
  projectId: string | null,
  files: File[],
  opts: { onProgress?: (loaded: number, total: number) => void } = {}
): Promise<UploadFilesResponse> {
  const path = projectId
    ? `/projects/${encodeURIComponent(projectId)}/files`
    : '/files';
  const url = `${daemonBase()}${API_PREFIX}${path}`;

  const form = new FormData();
  for (const f of files) form.append('files', f, f.name);

  // We use XHR (not fetch) so the renderer can drive a real progress bar
  // -- fetch has no upload-progress event.
  if (opts.onProgress) {
    return await uploadViaXhr(url, form, opts.onProgress);
  }

  const token = getAuthToken();
  const headers: Record<string, string> = { Accept: 'application/json' };
  if (token) headers[TOKEN_HEADER] = token;

  const res = await fetch(url, { method: 'POST', headers, body: form });
  const text = await res.text();
  const parsed = text ? safeJson(text) : null;
  if (!res.ok) {
    if (isErrorEnvelope(parsed)) throw new SynapseApiError(parsed, res.status);
    throw new SynapseApiError(
      {
        code: 'http.unexpected',
        message: `HTTP ${res.status} ${res.statusText}`,
        retryable: res.status >= 500,
      },
      res.status
    );
  }
  return parsed as UploadFilesResponse;
}

function uploadViaXhr(
  url: string,
  form: FormData,
  onProgress: (loaded: number, total: number) => void
): Promise<UploadFilesResponse> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', url);
    const token = getAuthToken();
    if (token) xhr.setRequestHeader(TOKEN_HEADER, token);
    xhr.setRequestHeader('Accept', 'application/json');
    xhr.upload.addEventListener('progress', (e) => {
      if (e.lengthComputable) onProgress(e.loaded, e.total);
    });
    xhr.onload = () => {
      const parsed = xhr.responseText ? safeJson(xhr.responseText) : null;
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(parsed as UploadFilesResponse);
      } else if (isErrorEnvelope(parsed)) {
        reject(new SynapseApiError(parsed, xhr.status));
      } else {
        reject(
          new SynapseApiError(
            {
              code: 'http.unexpected',
              message: `HTTP ${xhr.status} ${xhr.statusText}`,
              retryable: xhr.status >= 500,
            },
            xhr.status
          )
        );
      }
    };
    xhr.onerror = () =>
      reject(
        new SynapseApiError(
          { code: 'http.network', message: 'Upload network error.', retryable: true },
          0
        )
      );
    xhr.send(form);
  });
}

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

/** Soft-delete a file. */
export async function deleteFile(
  projectId: string | null,
  fileId: string
): Promise<void> {
  const path = projectId
    ? `/projects/${encodeURIComponent(projectId)}/files/${encodeURIComponent(fileId)}`
    : `/files/${encodeURIComponent(fileId)}`;
  await apiFetch<void>(path, { method: 'DELETE' });
}

/** Build the download URL (used by `<a href>` / openExternal). The browser
 *  / Electron handles the auth header via XHR or the cookie isn't needed --
 *  for now we emit a URL with the token in a query param the daemon would
 *  need to support. For v0.1.31 we drive downloads by fetching and creating
 *  an object URL on the renderer side so the auth header rides cleanly. */
export async function downloadFileBlob(
  projectId: string | null,
  fileId: string
): Promise<Blob> {
  const path = projectId
    ? `/projects/${encodeURIComponent(projectId)}/files/${encodeURIComponent(fileId)}`
    : `/files/${encodeURIComponent(fileId)}`;
  const url = `${daemonBase()}${API_PREFIX}${path}`;
  const token = getAuthToken();
  const headers: Record<string, string> = {};
  if (token) headers[TOKEN_HEADER] = token;
  const res = await fetch(url, { headers });
  if (!res.ok) {
    throw new SynapseApiError(
      {
        code: 'http.unexpected',
        message: `Download failed: HTTP ${res.status}`,
        retryable: res.status >= 500,
      },
      res.status
    );
  }
  return await res.blob();
}

/** Trigger a browser download for a file. */
export async function downloadFile(
  projectId: string | null,
  fileId: string,
  filename: string
): Promise<void> {
  const blob = await downloadFileBlob(projectId, fileId);
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
