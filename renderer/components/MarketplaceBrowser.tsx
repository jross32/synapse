// Marketplace browser (v0.1.23 · ADR-0001 step 3).
//
// Read-only catalogue of tools available to install. v0.1.24 adds the
// Install button; for now we just list, badge tiers + verified state, and
// mark already-installed entries so the user can see what's already in the
// tools/ folder.

import { useEffect, useState } from 'react';
import {
  CheckCircle2,
  Download,
  ExternalLink,
  Layers,
  Loader2,
  PackageOpen,
  RefreshCw,
  ShieldCheck,
  Trash2,
} from 'lucide-react';

import type { MarketplaceResponse, RegistryEntry } from '@shared/generated-types';
import {
  fetchMarketplace,
  installTool,
  uninstallTool,
} from '@shared/marketplace-client';
import { openExternal } from '@shared/electron-bridge';
import { cn } from '@shared/utils';
import { Badge } from './ui/badge';
import { Button } from './ui/button';
import { Card } from './ui/card';

function tierLabel(tier: string): string {
  return tier === 'declarative' ? 'Declarative' : tier === 'handler' ? 'Handler' : tier;
}

function tierClass(tier: string): string {
  // Declarative tools are the open tier (anyone can author them); handler tools
  // ship in trusted Synapse builds. Different colour gives the user a quick read.
  return tier === 'declarative'
    ? 'bg-sky-500/15 text-sky-300'
    : 'bg-violet-500/20 text-violet-200';
}

export function MarketplaceBrowser(): JSX.Element {
  const [data, setData] = useState<MarketplaceResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function load(refresh = false): Promise<void> {
    setBusy(true);
    setError(null);
    try {
      const res = await fetchMarketplace(refresh);
      setData(res);
    } catch (err) {
      setError((err as Error).message || 'Failed to load marketplace.');
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  const [busyId, setBusyId] = useState<string | null>(null);
  const installed = new Set(data?.installed_ids ?? []);
  const entries = data?.registry.tools ?? [];

  async function handleInstall(id: string): Promise<void> {
    setBusyId(id);
    setError(null);
    try {
      const res = await installTool(id);
      // Optimistically mark installed; the v1.tool.reloaded broadcast will
      // also poke the Installed tab.
      setData((prev) =>
        prev
          ? { ...prev, installed_ids: Array.from(new Set([...prev.installed_ids, res.installed])).sort() }
          : prev
      );
    } catch (err) {
      setError(`Install failed: ${(err as Error).message}`);
    } finally {
      setBusyId(null);
    }
  }

  async function handleUninstall(id: string): Promise<void> {
    if (!window.confirm(`Uninstall '${id}'? Its manifest will be removed from tools/.`)) return;
    setBusyId(id);
    setError(null);
    try {
      await uninstallTool(id);
      setData((prev) =>
        prev
          ? { ...prev, installed_ids: prev.installed_ids.filter((x) => x !== id) }
          : prev
      );
    } catch (err) {
      setError(`Uninstall failed: ${(err as Error).message}`);
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className='flex flex-col gap-4'>
      <div className='flex flex-wrap items-center justify-between gap-3'>
        <div>
          <h2 className='text-lg font-semibold'>Browse tools</h2>
          <p className='text-sm text-muted-foreground'>
            Tools available to install. Declarative ones are pure JSON — anyone can
            author one. Handler-tier tools ship inside trusted Synapse builds.
          </p>
        </div>
        <div className='flex items-center gap-2'>
          {data?.source && (
            <span className='hidden text-[11px] text-muted-foreground sm:inline'>
              {data.source.kind === 'url' ? data.source.location : 'bundled sample'}
            </span>
          )}
          <Button variant='outline' size='sm' onClick={() => void load(true)} disabled={busy}>
            {busy ? <Loader2 className='h-4 w-4 animate-spin' /> : <RefreshCw className='h-4 w-4' />}
            Refresh
          </Button>
        </div>
      </div>

      {error && (
        <p role='alert' className='text-sm text-destructive'>
          {error}
        </p>
      )}

      {data === null && !error && (
        <Card className='flex items-center justify-center gap-2 p-12 text-sm text-muted-foreground'>
          <Loader2 className='h-4 w-4 animate-spin' /> Loading registry…
        </Card>
      )}

      {data !== null && entries.length === 0 && (
        <Card className='flex flex-col items-center gap-3 border-dashed p-12 text-center'>
          <PackageOpen className='h-8 w-8 text-muted-foreground' />
          <p className='text-sm text-muted-foreground'>
            Registry is empty. Set <code className='font-mono'>SYNAPSE_TOOL_REGISTRY_URL</code>{' '}
            to point at a real index, or drop tools into{' '}
            <code className='font-mono'>tools/</code> by hand.
          </p>
        </Card>
      )}

      {entries.length > 0 && (
        <div className='grid grid-cols-[repeat(auto-fill,minmax(min(100%,340px),1fr))] gap-4'>
          {entries.map((e) => (
            <RegistryCard
              key={e.id}
              entry={e}
              installed={installed.has(e.id)}
              busy={busyId === e.id}
              onInstall={() => void handleInstall(e.id)}
              onUninstall={() => void handleUninstall(e.id)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

interface RegistryCardProps {
  entry: RegistryEntry;
  installed: boolean;
  busy: boolean;
  onInstall: () => void;
  onUninstall: () => void;
}

function RegistryCard({
  entry,
  installed,
  busy,
  onInstall,
  onUninstall,
}: RegistryCardProps): JSX.Element {
  // Handler-tier tools without a bundled handler are still "installable" --
  // they just won't run until a Synapse build ships the matching handler.
  // We surface that via the Verified hint in the description; the install
  // itself is the same flow.
  const canInstall = !installed && (!!entry.manifest_inline || !!entry.manifest_url);
  return (
    <Card className='flex flex-col gap-3 p-5'>
      <header className='flex items-start justify-between gap-3'>
        <div className='min-w-0'>
          <h3 className='truncate text-base font-semibold'>{entry.name}</h3>
          <p className='font-mono text-[11px] text-muted-foreground'>
            v{entry.version} · {entry.publisher}
          </p>
        </div>
        <div className='flex shrink-0 flex-col items-end gap-1'>
          <span
            className={cn(
              'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium',
              tierClass(entry.tier)
            )}
            title={
              entry.tier === 'declarative'
                ? 'Pure-JSON tool — runs through vetted primitives.'
                : 'Ships with a curated Python handler in trusted Synapse builds.'
            }
          >
            <Layers className='h-2.5 w-2.5' />
            {tierLabel(entry.tier)}
          </span>
          {entry.verified && (
            <span
              className='inline-flex items-center gap-1 rounded-full bg-emerald-500/15 px-2 py-0.5 text-[10px] font-medium text-emerald-300'
              title='Reviewed by The WhatIf Company'
            >
              <ShieldCheck className='h-2.5 w-2.5' />
              Verified
            </span>
          )}
        </div>
      </header>

      <p className='text-sm text-muted-foreground'>{entry.description}</p>

      <div className='mt-auto flex items-center justify-between gap-2'>
        {installed ? (
          <span className='inline-flex items-center gap-1.5 text-xs font-medium text-status-launched'>
            <CheckCircle2 className='h-3.5 w-3.5' />
            Already installed
          </span>
        ) : (
          <Badge variant='outline' className='text-[10px]'>
            Not installed
          </Badge>
        )}
        <div className='flex items-center gap-1'>
          {entry.homepage && (
            <Button
              variant='ghost'
              size='sm'
              className='h-7 px-2 text-xs'
              onClick={() => void openExternal(entry.homepage as string)}
              title={entry.homepage}
            >
              <ExternalLink className='h-3 w-3' /> Homepage
            </Button>
          )}
          {installed ? (
            <Button
              variant='ghost'
              size='sm'
              className='h-7 px-2 text-xs text-destructive hover:bg-destructive/10'
              onClick={onUninstall}
              disabled={busy}
              title='Remove this tool from tools/'
            >
              {busy ? <Loader2 className='h-3 w-3 animate-spin' /> : <Trash2 className='h-3 w-3' />}
              Uninstall
            </Button>
          ) : (
            <Button
              size='sm'
              className='h-7 px-2 text-xs'
              onClick={onInstall}
              disabled={!canInstall || busy}
              title={canInstall ? 'Install this tool' : 'No installable manifest for this entry'}
            >
              {busy ? <Loader2 className='h-3 w-3 animate-spin' /> : <Download className='h-3 w-3' />}
              Install
            </Button>
          )}
        </div>
      </div>
    </Card>
  );
}
