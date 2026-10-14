import { app } from 'electron';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';

// Public, read-only publisher metadata shipped INSIDE the packaged application.
// Never load signing secrets or trust keys from a remote update manifest.
export interface UpdatePublisherConfig {
  feedUrl: string;
  publicKey: string;
}
export function trustedPublisher(): UpdatePublisherConfig | null {
  if (!app.isPackaged) return null;
  try {
    const filename = path.join(app.getAppPath(), 'dist-electron', 'update-publisher.json');
    const raw = fs.readFileSync(filename, 'utf8');
    if (raw.length > 16_384) return null;
    const candidate = JSON.parse(raw) as Record<string, unknown>;
    if (candidate.schema !== 1 || typeof candidate.feed_url !== 'string'
        || typeof candidate.public_key !== 'string') return null;
    const url = new URL(candidate.feed_url);
    if (url.protocol !== 'https:' || !url.hostname || url.username || url.password
        || url.hash || url.search) return null;
    const key = crypto.createPublicKey(candidate.public_key);
    if (key.asymmetricKeyType !== 'ed25519') return null;
    return { feedUrl: url.href, publicKey: candidate.public_key };
  } catch {
    return null;
  }
}
