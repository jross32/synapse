// Backup & restore panel (Contract #28 · v0.1.10.5) -- Settings page.
//
// Download the whole project registry as one JSON snapshot, or restore one
// back. Restore is non-destructive: it creates new projects and updates
// existing ones by id, never deletes. Secret env values never leave the
// daemon -- the report lists which keys to re-enter.

import { useRef, useState } from 'react';
import { Download, Loader2, Upload } from 'lucide-react';

import type { RestoreReport, SnapshotPayload } from '@shared/generated-types';
import { exportSnapshot, restoreSnapshot } from '@shared/snapshot-client';
import { Button } from './ui/button';
import { Card } from './ui/card';

function timestamp(): string {
  return new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-');
}

export function SnapshotPanel(): JSX.Element {
  const fileInput = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState<'export' | 'restore' | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [report, setReport] = useState<RestoreReport | null>(null);

  async function handleDownload(): Promise<void> {
    setBusy('export');
    setError(null);
    setReport(null);
    try {
      const snapshot = await exportSnapshot();
      const blob = new Blob([JSON.stringify(snapshot, null, 2)], {
        type: 'application/json',
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `synapse-snapshot-${timestamp()}.json`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(`Export failed: ${(err as Error).message}`);
    } finally {
      setBusy(null);
    }
  }

  async function handleFile(file: File): Promise<void> {
    setBusy('restore');
    setError(null);
    setReport(null);
    try {
      const text = await file.text();
      const payload = JSON.parse(text) as SnapshotPayload;
      setReport(await restoreSnapshot(payload));
    } catch (err) {
      const msg = (err as Error).message;
      setError(
        msg.includes('JSON')
          ? "That file isn't a valid Synapse snapshot."
          : `Restore failed: ${msg}`
      );
    } finally {
      setBusy(null);
      if (fileInput.current) fileInput.current.value = '';
    }
  }

  return (
    <Card className='flex flex-col gap-4 p-6'>
      <div>
        <h2 className='text-lg font-semibold'>Backup &amp; restore</h2>
        <p className='mt-1 text-sm text-muted-foreground'>
          Export your whole project registry as one JSON file, or restore one. Restore is
          non-destructive — it adds new projects and updates existing ones by id, never
          deletes. Secret values stay on this machine and must be re-entered after a restore.
        </p>
      </div>

      <div className='flex flex-wrap gap-2'>
        <Button variant='outline' disabled={busy !== null} onClick={() => void handleDownload()}>
          {busy === 'export' ? (
            <Loader2 className='h-4 w-4 animate-spin' />
          ) : (
            <Download className='h-4 w-4' />
          )}
          Download snapshot
        </Button>
        <Button
          variant='outline'
          disabled={busy !== null}
          onClick={() => fileInput.current?.click()}
        >
          {busy === 'restore' ? (
            <Loader2 className='h-4 w-4 animate-spin' />
          ) : (
            <Upload className='h-4 w-4' />
          )}
          Restore from file
        </Button>
        <input
          ref={fileInput}
          type='file'
          accept='application/json,.json'
          className='hidden'
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) void handleFile(file);
          }}
        />
      </div>

      {error && (
        <p role='alert' className='text-sm text-destructive'>
          {error}
        </p>
      )}

      {report && (
        <div className='flex flex-col gap-2 rounded-md border border-border bg-secondary/40 p-4 text-sm'>
          <p className='font-medium text-foreground'>
            Restored — {report.projects_created} created, {report.projects_updated} updated.
          </p>
          {report.secrets_needing_reentry.length > 0 && (
            <p className='text-muted-foreground'>
              {report.secrets_needing_reentry.length} secret value(s) need re-entering:{' '}
              <span className='font-mono text-xs'>
                {report.secrets_needing_reentry
                  .map((s) => `${s.project_id}/${s.key}`)
                  .join(', ')}
              </span>
            </p>
          )}
          {report.warnings.length > 0 && (
            <ul className='flex flex-col gap-1 text-xs text-muted-foreground'>
              {report.warnings.map((w, i) => (
                <li key={i}>⚠ {w}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </Card>
  );
}
