import { useEffect, useMemo, useState } from 'react';
import { Bot, CheckCircle2, Loader2, PackagePlus, RefreshCw, Sparkles, Trash2 } from 'lucide-react';

import {
  fetchAiBundles,
  installAiBundle,
  uninstallAiBundle,
  type AiBundleCatalogItem,
} from '@shared/ai-bundles-client';
import { Badge } from './ui/badge';
import { Button } from './ui/button';
import { Card } from './ui/card';
import { Input } from './ui/input';
import { cn } from '@shared/utils';

type FilterMode = 'all' | 'installed' | 'not-installed';

export function AiBundleBrowser(): JSX.Element {
  const [data, setData] = useState<Awaited<ReturnType<typeof fetchAiBundles>> | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState<FilterMode>('all');
  const [error, setError] = useState<string | null>(null);

  async function load(): Promise<void> {
    try {
      setError(null);
      setData(await fetchAiBundles());
    } catch (err) {
      setError((err as Error).message);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  const bundles = useMemo(() => {
    const items = data?.catalog ?? [];
    const text = query.trim().toLowerCase();
    return items.filter((item) => {
      if (filter === 'installed' && !item.installed) return false;
      if (filter === 'not-installed' && item.installed) return false;
      if (!text) return true;
      return [
        item.name,
        item.description,
        item.publisher,
        item.tags.join(' '),
        item.recommended_case_modes.join(' '),
        item.recommended_mission_profiles.join(' '),
      ]
        .join(' ')
        .toLowerCase()
        .includes(text);
    });
  }, [data, filter, query]);

  async function handleInstall(bundle: AiBundleCatalogItem): Promise<void> {
    setBusyId(bundle.id);
    setError(null);
    try {
      await installAiBundle(bundle.id);
      await load();
    } catch (err) {
      setError(`Install failed: ${(err as Error).message}`);
    } finally {
      setBusyId(null);
    }
  }

  async function handleUninstall(bundle: AiBundleCatalogItem): Promise<void> {
    if (!window.confirm(`Uninstall '${bundle.name}'? Bundle-owned AI roles, quick actions, and factory assets may be removed.`)) {
      return;
    }
    setBusyId(bundle.id);
    setError(null);
    try {
      await uninstallAiBundle(bundle.id);
      await load();
    } catch (err) {
      setError(`Uninstall failed: ${(err as Error).message}`);
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className='space-y-5'>
      <Card className='border-border/70 bg-gradient-to-br from-card via-card to-secondary/20 p-5'>
        <div className='flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between'>
          <div className='max-w-3xl space-y-2'>
            <div className='flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.18em] text-primary/85'>
              <Sparkles className='h-3.5 w-3.5' />
              AI Bundles
            </div>
            <div>
              <h2 className='text-2xl font-semibold tracking-tight'>Install AI-first workflow packs</h2>
              <p className='mt-1 text-sm text-muted-foreground'>
                These bundles are built for AI operators: better roles, stronger personalities, reusable quick
                actions, and factory assets that reduce setup tokens and improve quality.
              </p>
            </div>
          </div>
          <Button variant='outline' size='sm' onClick={() => void load()} disabled={busyId !== null}>
            <RefreshCw className='h-4 w-4' />
            Refresh
          </Button>
        </div>

        <div className='mt-4 flex flex-col gap-3 lg:flex-row lg:items-center'>
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder='Search bundles, goals, case modes, or tags...'
            className='h-11 rounded-2xl border-border/70 bg-background/70'
          />
          <div className='flex gap-2'>
            {(['all', 'installed', 'not-installed'] as FilterMode[]).map((value) => (
              <button
                key={value}
                type='button'
                onClick={() => setFilter(value)}
                className={cn(
                  'rounded-full border px-3 py-2 text-xs font-medium transition-colors',
                  filter === value
                    ? 'border-primary/35 bg-primary/10 text-foreground'
                    : 'border-border/70 bg-background/70 text-muted-foreground hover:text-foreground'
                )}
              >
                {value === 'all' ? 'All bundles' : value === 'installed' ? 'Installed' : 'Not installed'}
              </button>
            ))}
          </div>
        </div>
      </Card>

      {error && (
        <p role='alert' className='text-sm text-destructive'>
          {error}
        </p>
      )}

      <div className='grid grid-cols-[repeat(auto-fill,minmax(min(100%,360px),1fr))] gap-4'>
        {bundles.map((bundle) => {
          const busy = busyId === bundle.id;
          const assetCount =
            bundle.roles.length +
            bundle.personalities.length +
            bundle.quick_actions.length +
            bundle.components.length +
            bundle.recipes.length +
            bundle.sources.length;
          return (
            <Card
              key={bundle.id}
              className='flex h-full flex-col gap-4 rounded-3xl border-border/70 bg-gradient-to-br from-card via-card to-secondary/25 p-5'
            >
              <div className='flex items-start justify-between gap-3'>
                <div className='flex items-start gap-3'>
                  <div className='mt-0.5 flex h-10 w-10 items-center justify-center rounded-2xl bg-primary/12 text-primary'>
                    <Bot className='h-4.5 w-4.5' />
                  </div>
                  <div>
                    <div className='flex flex-wrap items-center gap-2'>
                      <h3 className='text-base font-semibold'>{bundle.name}</h3>
                      {bundle.featured && (
                        <Badge className='rounded-full bg-primary/15 px-2 py-0.5 text-[10px] font-semibold text-primary'>
                          Featured
                        </Badge>
                      )}
                    </div>
                    <p className='mt-1 text-xs text-muted-foreground'>
                      {bundle.publisher} · v{bundle.version}
                    </p>
                  </div>
                </div>
                {bundle.installed ? (
                  <span className='inline-flex items-center gap-1.5 rounded-full bg-emerald-500/15 px-2 py-1 text-[10px] font-semibold text-emerald-300'>
                    <CheckCircle2 className='h-3 w-3' />
                    Installed
                  </span>
                ) : (
                  <Badge variant='outline' className='rounded-full border-border/70 text-[10px]'>
                    Ready
                  </Badge>
                )}
              </div>

              <p className='text-sm text-muted-foreground'>{bundle.description}</p>

              <div className='space-y-2 rounded-2xl border border-border/70 bg-background/40 p-3'>
                <p className='text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground'>Why it helps</p>
                <p className='text-sm'>{bundle.efficiency.quality_gain_summary}</p>
                <p className='text-xs text-muted-foreground'>{bundle.efficiency.token_savings_summary}</p>
              </div>

              <div className='grid grid-cols-2 gap-2 text-xs'>
                <InlineStat label='Modes' value={String(bundle.recommended_case_modes.length)} />
                <InlineStat label='Owned assets' value={String(assetCount)} />
                <InlineStat label='Quick actions' value={String(bundle.quick_actions.length)} />
                <InlineStat label='Roles' value={String(bundle.roles.length)} />
              </div>

              {bundle.overlap_report.length > 0 && (
                <div className='space-y-2'>
                  <p className='text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground'>
                    Overlap readout
                  </p>
                  <div className='space-y-2'>
                    {bundle.overlap_report.slice(0, 2).map((item) => (
                      <div key={`${bundle.id}-${item.bundle_id}`} className='rounded-2xl border border-border/70 bg-background/50 p-3'>
                        <div className='flex items-center justify-between gap-2 text-xs'>
                          <span className='font-medium'>{item.bundle_id}</span>
                          <span className='rounded-full bg-secondary px-2 py-0.5 text-[10px] text-secondary-foreground'>
                            {item.similarity_percent}% overlap
                          </span>
                        </div>
                        <p className='mt-2 text-xs text-muted-foreground'>{item.summary}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div className='flex flex-wrap gap-1.5'>
                {bundle.tags.slice(0, 6).map((tag) => (
                  <Badge key={tag} variant='secondary'>
                    {tag}
                  </Badge>
                ))}
              </div>

              <div className='mt-auto flex gap-2'>
                {bundle.installed ? (
                  <Button
                    type='button'
                    variant='ghost'
                    className='w-full rounded-2xl text-destructive hover:bg-destructive/10'
                    onClick={() => void handleUninstall(bundle)}
                    disabled={busy}
                  >
                    {busy ? <Loader2 className='h-4 w-4 animate-spin' /> : <Trash2 className='h-4 w-4' />}
                    Uninstall
                  </Button>
                ) : (
                  <Button
                    type='button'
                    className='w-full rounded-2xl'
                    onClick={() => void handleInstall(bundle)}
                    disabled={busy}
                  >
                    {busy ? <Loader2 className='h-4 w-4 animate-spin' /> : <PackagePlus className='h-4 w-4' />}
                    Install bundle
                  </Button>
                )}
              </div>
            </Card>
          );
        })}
      </div>

      {data && bundles.length === 0 && (
        <Card className='border-dashed p-10 text-center text-sm text-muted-foreground'>
          No bundles matched the current filters.
        </Card>
      )}
    </div>
  );
}

function InlineStat({ label, value }: { label: string; value: string }): JSX.Element {
  return (
    <div className='rounded-2xl border border-border/70 bg-background/45 p-3'>
      <p className='text-[11px] uppercase tracking-[0.16em] text-muted-foreground'>{label}</p>
      <p className='mt-1 text-base font-semibold'>{value}</p>
    </div>
  );
}
