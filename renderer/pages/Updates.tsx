import { useEffect, useState } from 'react';
import { AlertCircle, CheckCircle2, Download, Laptop, Loader2, Monitor, PackageCheck, RefreshCw, ShieldCheck, TerminalSquare } from 'lucide-react';

import { downloadReleaseArtifact, getReleaseManifest, type ReleaseArtifact, type ReleaseManifest } from '@shared/releases-client';
import { PageHeader } from '../components/PageHeader';
import { Button } from '../components/ui/button';
import { Card } from '../components/ui/card';
import './updates.css';

function formatBytes(value: number | null): string | null {
  if (value == null) return null;
  if (value < 1024 * 1024) return `${Math.round(value / 1024)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

export function UpdatesPage(): JSX.Element {
  const [manifest, setManifest] = useState<ReleaseManifest | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState<string | null>(null);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  const refresh = (): void => {
    setError(null);
    void getReleaseManifest().then(setManifest).catch((err) => setError((err as Error).message));
  };

  useEffect(() => { refresh(); }, []);

  const download = async (artifact: ReleaseArtifact): Promise<void> => {
    setDownloading(artifact.platform);
    setDownloadError(null);
    try {
      await downloadReleaseArtifact(artifact);
    } catch (err) {
      setDownloadError((err as Error).message);
    } finally {
      setDownloading(null);
    }
  };

  const icons = {
    windows: <Monitor className='h-8 w-8' aria-hidden='true' />,
    macos: <Laptop className='h-8 w-8' aria-hidden='true' />,
    linux: <TerminalSquare className='h-8 w-8' aria-hidden='true' />,
  } as const;

  return (
    <div className='flex h-full flex-col gap-4 overflow-y-auto pb-4'>
      <PageHeader title='Downloads & Updates' subtitle='Install Synapse, verify releases, and keep your connected workspace current.'
        action={<Button variant='outline' onClick={refresh}><RefreshCw className='h-4 w-4' /> Check releases</Button>}
      />

      <section className='synapse-updates-hero'>
        <div className='synapse-updates-hero__orb' aria-hidden='true'><PackageCheck className='h-14 w-14' /></div>
        <div className='synapse-updates-hero__text'>
          <span className='synapse-updates-hero__eyebrow'>ONE ACCOUNT. ALL YOUR MACHINES.</span>
          <h2>Download Synapse</h2>
          <p>Available for Windows, macOS, and Linux. Signed installers and additional operating systems will appear here once they're actually built and published.</p>
          {manifest && <div className='synapse-updates-hero__version'>Current source version <strong>v{manifest.version}</strong><span aria-hidden='true'>·</span>{manifest.channel} channel</div>}
        </div>
      </section>

      {error && <Card role='alert' className='flex items-center gap-2 p-4 text-sm text-destructive'><AlertCircle className='h-4 w-4' />{error}</Card>}
      {downloadError && <Card role='alert' className='flex items-center gap-2 p-4 text-sm text-destructive'><AlertCircle className='h-4 w-4' />{downloadError}</Card>}

      {!manifest ? (
        <Card role='status' className='flex items-center gap-2 p-6 text-sm text-muted-foreground'>
          <Loader2 className='h-4 w-4 animate-spin' /> Checking release metadata...
        </Card>
      ) : (
        <>
          <div className='grid gap-3 md:grid-cols-3'>
            {manifest.artifacts.map((artifact) => {
              const isReady = artifact.status === 'ready' && Boolean(artifact.download_url && artifact.filename);
              const icon = icons[artifact.platform as keyof typeof icons] ?? <Download className='h-8 w-8' aria-hidden='true' />;
              return (
                <Card key={artifact.platform} className='synapse-update-card'>
                  <div className='synapse-update-card__icon'>{icon}</div>
                  <h3>{artifact.platform === 'macos' ? 'macOS' : artifact.platform === 'windows' ? 'Windows' : 'Linux'}</h3>
                  <p>{artifact.label}</p>
                  <div className='synapse-update-card__state'>
                    {isReady ? <><CheckCircle2 className='h-3.5 w-3.5' /> Artifact available</> : 'Not published yet'}
                  </div>
                  <Button className='w-full' disabled={!isReady || downloading !== null} onClick={() => void download(artifact)}>
                    {downloading === artifact.platform ? <Loader2 className='h-4 w-4 animate-spin' /> : <Download className='h-4 w-4' />}
                    {downloading === artifact.platform ? 'Preparing download…' : isReady ? `Download .${artifact.format}` : 'Coming soon'}
                  </Button>
                  {isReady && artifact.size_bytes != null && <p className='synapse-update-card__size'>v{manifest.version} · {formatBytes(artifact.size_bytes)}</p>}
                  {isReady && artifact.sha256 && <details className='synapse-update-card__checksum'>
                    <summary><ShieldCheck className='h-3.5 w-3.5' /> SHA-256 checksum</summary>
                    <code>{artifact.sha256}</code>
                  </details>}
                </Card>
              );
            })}
          </div>
          <Card className='flex items-start gap-3 p-5'>
            <ShieldCheck className='mt-0.5 h-5 w-5 shrink-0 text-primary' />
            <div>
              <h3 className='font-semibold'>Verified releases, not placeholder buttons</h3>
              <p className='mt-1 text-sm text-muted-foreground'>Downloads are enabled only after an artifact exists on the release server. Installer signing, automatic installation, rollback, and multi-device sync require independent end-to-end verification before being represented as complete.</p>
            </div>
          </Card>
        </>
      )}
    </div>
  );
}
