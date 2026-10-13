import fs from 'node:fs';
import path from 'node:path';

export type InstallDisposition = 'new' | 'existing' | 'unknown';
/**
 * Call before starting the daemon. Never infer "new" from missing renderer localStorage:
 * upgrades may not have the onboarding key yet.
 */
export function classifyInstallation(userData: string, packaged: boolean): InstallDisposition {
  if (!packaged) return 'existing';
  try {
    const entries = fs.readdirSync(userData, { withFileTypes: true });
    const hasPriorData = entries.some(entry =>
      ['data', 'Local Storage', 'IndexedDB', 'Preferences', 'Session Storage', 'bootstrap-ai-bundles.json'].includes(entry.name));
    return hasPriorData ? 'existing' : 'new';
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === 'ENOENT') return 'new';
    return 'unknown'; // fail closed: don't interrupt existing installations
  }
}
export function installMarkerPath(userData: string): string {
  return path.join(userData, 'first-launch-install-v1.json');
}
export function readInstallDisposition(userData: string, packaged: boolean): InstallDisposition {
  try {
    if (!fs.existsSync(installMarkerPath(userData))) return classifyInstallation(userData, packaged);
    const marker = JSON.parse(fs.readFileSync(installMarkerPath(userData), 'utf8')) as { disposition?: unknown };
    if (marker.disposition === 'new' || marker.disposition === 'existing') return marker.disposition;
  } catch { return 'unknown'; }
  return 'unknown';
}
