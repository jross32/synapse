// Local-model marketplace (ADR-0014 Phase M). Browse a curated catalog and
// pull models with live progress streamed over v1.model.pull_progress. Mirrors
// the tool MarketplaceBrowser; works in the mobile shell (responsive grid).

import { useCallback, useEffect, useRef, useState } from 'react';
import { Check, Download, Loader2, Star, Trash2, X } from 'lucide-react';

import {
  cancelModelPull,
  getModelRegistry,
  listModelPulls,
  pullModel,
  removeModel,
  type ModelCatalogEntry,
  type ModelPullState,
} from '../lib/models-client';
import { useDaemon } from '../lib/daemon-context';
import { cn } from '@shared/utils';
import { Button } from './ui/button';
import { Card } from './ui/card';

interface ModelBrowserProps {
  /** Called when the installed set changes (pull finished or model removed) so
   *  the parent can refresh its model picker. */
  onInstalledChange?: () => void;
}

const ACTIVE: ReadonlySet<string> = new Set(['queued', 'downloading']);

export function ModelBrowser({ onInstalledChange }: ModelBrowserProps): JSX.Element {
  const { subscribeRaw } = useDaemon();
  const [models, setModels] = useState<ModelCatalogEntry[]>([]);
  const [pulls, setPulls] = useState<Record<string, ModelPullState>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const onInstalled = useRef(onInstalledChange);
  onInstalled.current = onInstalledChange;

  const refreshRegistry = useCallback(async () => {
    try {
      const cat = await getModelRegistry();
      setModels(cat.models);
      setError(null);
    } catch (e) {
      setError((e as Error).message || 'Could not load the model catalog.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refreshRegistry();
    void listModelPulls().then(({ pulls: list }) => {
      setPulls(Object.fromEntries(list.map((p) => [p.name, p])));
    }).catch(() => undefined);
  }, [refreshRegistry]);

  // Live download progress.
  useEffect(() => {
    return subscribeRaw((event) => {
      if (event.name !== 'v1.model.pull_progress') return;
      const state = event.payload as ModelPullState;
      setPulls((prev) => ({ ...prev, [state.name]: state }));
      if (state.status === 'success') {
        void refreshRegistry();
        onInstalled.current?.();
      }
    });
  }, [subscribeRaw, refreshRegistry]);

  async function startPull(name: string): Promise<void> {
    setPulls((prev) => ({
      ...prev,
      [name]: { name, status: 'queued', completed: 0, total: 0, percent: 0, detail: null, error: null, updated_at: '' },
    }));
    try {
      await pullModel(name);
    } catch (e) {
      setError((e as Error).message || 'Could not start the download.');
      setPulls((prev) => {
        const next = { ...prev };
        delete next[name];
        return next;
      });
    }
  }

  async function cancel(name: string): Promise<void> {
    await cancelModelPull(name).catch(() => undefined);
  }

  async function remove(name: string): Promise<void> {
    await removeModel(name).catch((e) => setError((e as Error).message));
    await refreshRegistry();
    onInstalled.current?.();
  }

  if (loading) {
    return (
      <Card className='flex items-center gap-2 p-6 text-sm text-muted-foreground'>
        <Loader2 className='h-4 w-4 animate-spin' /> Loading the model catalog...
      </Card>
    );
  }

  return (
    <div className='flex flex-col gap-3'>
      {error && <p role='alert' className='text-xs text-destructive'>{error}</p>}
      <div className='grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3'>
        {models.map((m) => {
          const pull = pulls[m.id];
          const active = pull && ACTIVE.has(pull.status);
          return (
            <Card key={m.id} className='flex flex-col gap-2 p-4'>
              <div className='flex items-start justify-between gap-2'>
                <div className='min-w-0'>
                  <div className='flex items-center gap-1.5'>
                    <h3 className='truncate font-semibold'>{m.name}</h3>
                    {m.recommended && (
                      <Star className='h-3.5 w-3.5 shrink-0 fill-primary text-primary' aria-label='Recommended' />
                    )}
                  </div>
                  <p className='text-xs text-muted-foreground'>
                    {m.publisher ? `${m.publisher} · ` : ''}{m.parameter_size ?? ''}{m.size_label ? ` · ${m.size_label}` : ''}
                  </p>
                </div>
                {m.installed && !active && (
                  <span className='inline-flex shrink-0 items-center gap-1 rounded-full bg-emerald-500/15 px-2 py-0.5 text-xs font-medium text-emerald-300'>
                    <Check className='h-3 w-3' /> Installed
                  </span>
                )}
              </div>

              <p className='line-clamp-2 text-sm text-muted-foreground'>{m.description}</p>

              <div className='flex flex-wrap gap-1'>
                {m.tags.map((t) => (
                  <span key={t} className='rounded bg-secondary/50 px-1.5 py-0.5 text-[10px] text-muted-foreground'>{t}</span>
                ))}
              </div>

              <div className='mt-auto pt-1'>
                {active ? (
                  <div className='flex flex-col gap-1.5'>
                    <div className='h-2 w-full overflow-hidden rounded-full bg-secondary'>
                      <div
                        className='h-full rounded-full bg-primary transition-all'
                        style={{ width: `${pull.status === 'queued' ? 4 : pull.percent}%` }}
                      />
                    </div>
                    <div className='flex items-center justify-between text-xs text-muted-foreground'>
                      <span className='truncate'>
                        {pull.status === 'queued' ? 'Queued…' : `${pull.detail ?? 'Downloading'} · ${pull.percent}%`}
                      </span>
                      <Button size='sm' variant='ghost' className='h-6 px-2' onClick={() => void cancel(m.id)}>
                        <X className='h-3.5 w-3.5' /> Cancel
                      </Button>
                    </div>
                  </div>
                ) : pull?.status === 'error' ? (
                  <div className='flex items-center justify-between gap-2'>
                    <span className='truncate text-xs text-destructive'>{pull.error ?? 'Download failed'}</span>
                    <Button size='sm' variant='outline' onClick={() => void startPull(m.id)}>Retry</Button>
                  </div>
                ) : m.installed ? (
                  <Button size='sm' variant='ghost' className='text-destructive' onClick={() => void remove(m.id)}>
                    <Trash2 className='h-4 w-4' /> Remove
                  </Button>
                ) : (
                  <Button size='sm' onClick={() => void startPull(m.id)}>
                    <Download className='h-4 w-4' /> Download
                  </Button>
                )}
              </div>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
