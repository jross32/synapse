import { app, ipcMain } from 'electron';
import publisherConfig from './update-publisher.json';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import https from 'node:https';
import http from 'node:http';
import { spawn } from 'node:child_process';

/** The feed URL is an explicit HTTPS publisher setting, never a URL from the renderer.
 * Set SYNAPSE_UPDATE_FEED_URL in builds to a trusted HTTPS JSON manifest URL.
 * Sign manifests using Ed25519; embed SYNAPSE_UPDATE_PUBLIC_KEY (SPKI PEM).
 */
export interface DesktopUpdateInfo {
  status: 'disabled' | 'current' | 'available' | 'error';
  currentVersion: string;
  version?: string;
  notes?: string;
  error?: string;
}
type Manifest = {
  version: string;
  notes?: string;
  windows?: { url: string; sha256: string; size: number };
  signature: string;
};
const feedUrl = process.env.SYNAPSE_UPDATE_FEED_URL ?? publisherConfig.feedUrl;
const publicKey = process.env.SYNAPSE_UPDATE_PUBLIC_KEY ?? publisherConfig.publicKey;
let cachedManifest: Manifest | null = null;
let installing = false;

function parseVersion(version: string): number[] {
  if (!/^\d+\.\d+\.\d+(?:[-+][a-zA-Z0-9.-]+)?$/.test(version)) throw new Error('Invalid version');
  return version.split(/[-+]/)[0].split('.').map(Number);
}
export function versionIsNewer(candidate: string, current: string): boolean {
  const a = parseVersion(candidate), b = parseVersion(current);
  for (let i = 0; i < 3; i++) { if (a[i] !== b[i]) return a[i] > b[i]; }
  return false;
}
export function openPublisherResponse(url: string, timeout: number, redirects = 0): Promise<http.IncomingMessage> {
  return new Promise((resolve, reject) => {
    let parsed: URL;
    try { parsed = new URL(url); } catch { reject(new Error('Invalid publisher URL')); return; }
    if (parsed.protocol !== 'https:' || parsed.username || parsed.password || (parsed.port && parsed.port !== '443')) {
      reject(new Error('Publisher downloads require credential-free HTTPS on port 443')); return;
    }
    const request = https.get(parsed, { timeout }, response => {
      if ([301, 302, 303, 307, 308].includes(response.statusCode ?? 0)) {
        const location = response.headers.location;
        response.resume();
        if (!location || redirects >= 5) { reject(new Error('Publisher redirect limit exceeded')); return; }
        let redirected: string;
        try { redirected = new URL(location, parsed).href; } catch { reject(new Error('Invalid publisher redirect')); return; }
        void openPublisherResponse(redirected, timeout, redirects + 1).then(resolve, reject);
        return;
      }
      if (response.statusCode !== 200) { response.resume(); reject(new Error('Publisher HTTP ' + response.statusCode)); return; }
      resolve(response);
    });
    request.on('timeout', () => request.destroy(new Error('Publisher request timed out')));
    request.on('error', reject);
  });
}
async function getJson(url: string): Promise<string> {
  const response = await openPublisherResponse(url, 10000);
  return new Promise((resolve, reject) => {
    const parts: Buffer[] = []; let total = 0;
    response.on('data', (part: Buffer) => {
      total += part.length;
      if (total > 128 * 1024) response.destroy(new Error('Update manifest too large'));
      else parts.push(part);
    });
    response.on('end', () => resolve(Buffer.concat(parts).toString('utf8')));
    response.on('error', reject);
  });
}
function trustedManifest(raw: string): Manifest {
  const candidate = JSON.parse(raw) as Manifest;
  if (!candidate || typeof candidate.version !== 'string' || !candidate.windows || typeof candidate.signature !== 'string') throw new Error('Invalid update manifest');
  parseVersion(candidate.version);
  const artifact = candidate.windows;
  const url = new URL(artifact.url);
  if (url.protocol !== 'https:' || url.username || url.password || (url.port && url.port !== '443') || !/^[a-f0-9]{64}$/i.test(artifact.sha256) || !Number.isSafeInteger(artifact.size) || artifact.size <= 0) throw new Error('Invalid update artifact');
  if (!publicKey) throw new Error('Publisher verification key is not configured');
  const signedPayload = JSON.stringify({ version: candidate.version, notes: candidate.notes ?? '', windows: artifact });
  const verified = crypto.verify(null, Buffer.from(signedPayload), publicKey, Buffer.from(candidate.signature, 'base64'));
  if (!verified) throw new Error('Update signature verification failed');
  return candidate;
}
export async function checkDesktopUpdate(): Promise<DesktopUpdateInfo> {
  const currentVersion = app.getVersion();
  if (!app.isPackaged || !feedUrl || !publicKey || process.platform !== 'win32') return { status: 'disabled', currentVersion };
  try {
    const manifest = trustedManifest(await getJson(feedUrl));
    if (!versionIsNewer(manifest.version, currentVersion)) { cachedManifest = null; return { status: 'current', currentVersion }; }
    cachedManifest = manifest;
    return { status: 'available', currentVersion, version: manifest.version, notes: manifest.notes };
  } catch (error) {
    cachedManifest = null;
    return { status: 'error', currentVersion, error: error instanceof Error ? error.message : String(error) };
  }
}
async function downloadVerified(manifest: Manifest): Promise<string> {
  const artifact = manifest.windows!;
  const targetDir = path.join(app.getPath('userData'), 'updates', manifest.version);
  fs.mkdirSync(targetDir, { recursive: true });
  const destination = path.join(targetDir, 'Synapse-verified-update.exe');
  const temporary = destination + '.partial';
  try {
    const response = await openPublisherResponse(artifact.url, 30000);
    await new Promise<void>((resolve, reject) => {
      const output = fs.createWriteStream(temporary, { flags: 'w' });
      const hash = crypto.createHash('sha256'); let received = 0;
      response.on('data', (chunk: Buffer) => {
        received += chunk.length;
        if (received > artifact.size) { response.destroy(new Error('Installer exceeds declared size')); return; }
        hash.update(chunk);
      });
      response.pipe(output);
      output.on('finish', () => {
        output.close(() => {
          if (received !== artifact.size || hash.digest('hex').toLowerCase() !== artifact.sha256.toLowerCase()) reject(new Error('Installer integrity check failed'));
          else resolve();
        });
      });
      output.on('error', error => { response.destroy(); reject(error); });
      response.on('error', error => { output.destroy(); reject(error); });
      response.on('aborted', () => { output.destroy(); reject(new Error('Installer download was interrupted')); });
    });
    fs.renameSync(temporary, destination);
    return destination;
  } catch (error) {
    try { fs.unlinkSync(temporary); } catch {}
    throw error;
  }
}
/** Stage a verified installer; do not terminate the daemon or other app processes.
 * The interactive NSIS installer performs the actual replacement, so it can
 * be postponed. No misleading claim of zero downtime for a daemon replacement.
 */
export function registerDesktopUpdater(): void {
  ipcMain.handle('synapse:update-check', () => checkDesktopUpdate());
  ipcMain.handle('synapse:update-install', async (): Promise<{ ok: boolean; error?: string }> => {
    if (installing) return { ok: false, error: 'Update is already being prepared.' };
    if (!cachedManifest || !app.isPackaged || process.platform !== 'win32') return { ok: false, error: 'No verified desktop update available.' };
    installing = true;
    try {
      const file = await downloadVerified(cachedManifest);
      await new Promise<void>((resolve, reject) => {
        const child = spawn(file, [], { detached: true, stdio: 'ignore', windowsHide: false });
        child.once('error', reject);
        child.once('spawn', () => { child.unref(); resolve(); });
      });
      // An installer is now running. It owns the update; preserve all Synapse
      // services until its own prerequisites have been checked and user agrees.
      return { ok: true };
    } catch (error) {
      return { ok: false, error: error instanceof Error ? error.message : String(error) };
    } finally { installing = false; }
  });
}
