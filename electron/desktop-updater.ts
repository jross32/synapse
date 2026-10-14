import { app, ipcMain } from 'electron';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import https from 'node:https';
import http from 'node:http';
import { spawn } from 'node:child_process';
import { trustedPublisher } from './update-publisher';

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
const publisher = trustedPublisher();
const feedUrl = publisher?.feedUrl ?? '';
const publicKey = publisher?.publicKey ?? '';
let cachedManifest: Manifest | null = null;
let installing = false;

function parseVersion(version: string): number[] {
  if (!/^\d+\.\d+\.\d+(?:[-+][a-zA-Z0-9.-]+)?$/.test(version)) throw new Error('Invalid version');
  return version.split(/[.+-]/)[0].split('.').map(Number);
}
export function versionIsNewer(candidate: string, current: string): boolean {
  const a = parseVersion(candidate), b = parseVersion(current);
  for (let i = 0; i < 3; i++) { if (a[i] !== b[i]) return a[i] > b[i]; }
  return false;
}
function getJson(url: string): Promise<string> {
  return new Promise((resolve, reject) => {
    const parsed = new URL(url);
    if (parsed.protocol !== 'https:') return reject(new Error('Update manifest requires HTTPS'));
    const req = https.get(parsed, { timeout: 10000 }, (response) => {
      if (response.statusCode !== 200) { response.resume(); reject(new Error('Update feed HTTP ' + response.statusCode)); return; }
      const parts: Buffer[] = [];
      let total = 0;
      response.on('data', (part: Buffer) => { total += part.length; if (total > 128 * 1024) req.destroy(new Error('Update manifest too large')); else parts.push(part); });
      response.on('end', () => resolve(Buffer.concat(parts).toString('utf8')));
      response.on('error', reject);
    });
    req.on('timeout', () => req.destroy(new Error('Update request timed out')));
    req.on('error', reject);
  });
}
function trustedManifest(raw: string): Manifest {
  const candidate = JSON.parse(raw) as Manifest;
  if (!candidate || typeof candidate.version !== 'string' || !candidate.windows || typeof candidate.signature !== 'string') throw new Error('Invalid update manifest');
  parseVersion(candidate.version);
  const artifact = candidate.windows;
  const url = new URL(artifact.url);
  if (url.protocol !== 'https:' || !/^[a-f0-9]{64}$/i.test(artifact.sha256) || !Number.isSafeInteger(artifact.size) || artifact.size <= 0) throw new Error('Invalid update artifact');
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
    await new Promise<void>((resolve, reject) => {
      const request = https.get(artifact.url, { timeout: 30000 }, (response) => {
        if (response.statusCode !== 200) { response.resume(); reject(new Error('Installer HTTP ' + response.statusCode)); return; }
        const output = fs.createWriteStream(temporary, { flags: 'w' });
        const hash = crypto.createHash('sha256');
        let received = 0;
        response.on('data', (chunk: Buffer) => {
          received += chunk.length;
          if (received > artifact.size) { request.destroy(new Error('Installer exceeds declared size')); return; }
          hash.update(chunk);
        });
        response.pipe(output);
        output.on('finish', () => {
          output.close(() => {
            if (received !== artifact.size || hash.digest('hex').toLowerCase() !== artifact.sha256.toLowerCase()) reject(new Error('Installer integrity check failed'));
            else resolve();
          });
        });
        output.on('error', reject);
        response.on('error', reject);
      });
      request.on('timeout', () => request.destroy(new Error('Installer download timed out')));
      request.on('error', reject);
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
      // Re-read the feed immediately before install rather than trusting a
      // possibly stale manifest from the last UI check.
      const fresh = trustedManifest(await getJson(feedUrl));
      if (!versionIsNewer(fresh.version, app.getVersion()))
        return { ok: false, error: 'The advertised update is no longer newer.' };
      if (cachedManifest.version !== fresh.version || cachedManifest.signature !== fresh.signature)
        return { ok: false, error: 'Update offer changed. Check for updates again.' };
      const file = await downloadVerified(fresh);
      await new Promise<void>((resolve, reject) => {
        const child = spawn(file, [], { detached: true, stdio: 'ignore', windowsHide: false });
        child.once('error', reject);
        child.once('spawn', () => { child.unref(); resolve(); });
      });
      // The installer process has actually started, but installation is not
      // confirmed. Keep the live Synapse services running until user consent.
      return { ok: true };
    } catch (error) {
      return { ok: false, error: error instanceof Error ? error.message : String(error) };
    } finally { installing = false; }
  });
}
