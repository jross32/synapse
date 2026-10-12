import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Archive, ArrowUpRight, CheckCircle2, Clock3, FilePenLine,
  Loader2, RefreshCw, RotateCcw, Search, UsersRound,
} from 'lucide-react';

import { apiFetch } from '@shared/api-client';
import { openExternal } from '@shared/electron-bridge';
import { Button } from '../components/ui/button';
import { Card } from '../components/ui/card';
import { Input } from '../components/ui/input';

const WORKER_PROJECT_URL =
  'https://chatgpt.com/g/g-p-6a91003e980c81919b8920cfc9e0941e/project';
const WORKER_CONVERSATION_URL =
  /^https:\/\/chatgpt\.com\/g\/g-p-6a91003e980c81919b8920cfc9e0941e(?:-synapse2gpt-workers)?\/c\/[a-z0-9-]+(?:[?#].*)?$/i;
type WorkerStatus = 'starting' | 'active' | 'idle' | 'failed' | 'archived';
type WorkerFilter = 'current' | 'open' | 'working' | 'parked' | 'failed' | 'archived';

interface WorkerRecord {
  id: string;
  project_id: string;
  title: string;
  status: WorkerStatus;
  conversation_url: string;
  last_used_at: string;
  archived_reason: string;
  role_id: string | null;
  work_item_ids: string[];
  metadata: Record<string, unknown>;
  parked: boolean;
  open_in_browser: boolean;
  browser_activity: string;
}
interface CatalogResponse {
  workers: WorkerRecord[];
  total: number;
  open_count: number;
  parked_count: number;
}
const FILTERS: { key: WorkerFilter; label: string }[] = [
  { key: 'current', label: 'Current' },
  { key: 'open', label: 'Open' },
  { key: 'working', label: 'Working' },
  { key: 'parked', label: 'Parked' },
  { key: 'failed', label: 'Failed' },
  { key: 'archived', label: 'Archived' },
];
function safeMetadataText(worker: WorkerRecord, key: string): string {
  const value = worker.metadata?.[key];
  return typeof value === 'string' ? value : '';
}
function matchesFilter(worker: WorkerRecord, filter: WorkerFilter): boolean {
  switch (filter) {
    case 'open': return worker.open_in_browser && worker.status !== 'archived';
    case 'working': return worker.open_in_browser && worker.browser_activity === 'active';
    case 'parked': return worker.parked;
    case 'failed': return worker.status === 'failed';
    case 'archived': return worker.status === 'archived';
    default: return worker.status !== 'archived';
  }
}

export function WorkerCatalog(): JSX.Element {
  const [records, setRecords] = useState<WorkerRecord[]>([]);
  const [filter, setFilter] = useState<WorkerFilter>('current');
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [workingId, setWorkingId] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [handoff, setHandoff] = useState('');
  const [nextStep, setNextStep] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const refresh = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      const result = await apiFetch<CatalogResponse>('/chatgpt-workers/catalog?include_archived=true');
      setRecords(result.workers ?? []);
      setError(null);
    } catch (err) {
      if (!silent) setError(err instanceof Error ? err.message : 'Could not load Worker Catalog.');
    } finally {
      if (!silent) setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
    const polling = window.setInterval(() => void refresh(true), 20000);
    return () => window.clearInterval(polling);
  }, [refresh]);

  const visible = useMemo(() => {
    const normalized = search.toLocaleLowerCase().trim();
    return records.filter(worker => {
      if (!matchesFilter(worker, filter)) return false;
      if (!normalized) return true;
      return [
        worker.id, worker.title, worker.project_id, worker.role_id ?? '',
        ...worker.work_item_ids, safeMetadataText(worker, 'current_task'),
        safeMetadataText(worker, 'handoff_md'), safeMetadataText(worker, 'next_step'),
      ].some(value => value.toLocaleLowerCase().includes(normalized));
    });
  }, [records, filter, search]);
  const openCount = records.filter(worker => worker.open_in_browser).length;
  const parkedCount = records.filter(worker => worker.parked).length;
  const workingCount = records.filter(worker => worker.open_in_browser && worker.browser_activity === 'active').length;

  async function openWorker(worker: WorkerRecord) {
    if (!WORKER_CONVERSATION_URL.test(worker.conversation_url)) {
      setError('This worker has no verified conversation URL. Its saved record was not changed.');
      return;
    }
    if (worker.status === 'archived') {
      setError('Restore this worker first, then reopen its saved conversation.');
      return;
    }
    try {
      const result = await openExternal(worker.conversation_url);
      if (!result.ok) throw new Error(result.error || 'Unable to open Chrome worker.');
      setError(null);
      setNotice('Opened the saved conversation. The Chrome companion extension can add it to the worker group.');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to open Chrome worker.');
    }
  }
  async function changeArchive(worker: WorkerRecord, archive: boolean) {
    if (archive && worker.open_in_browser && worker.browser_activity === 'active') {
      setError('Wait for this worker to finish before archiving it.');
      return;
    }
    setWorkingId(worker.id);
    setError(null);
    try {
      await apiFetch('/chatgpt-workers/' + encodeURIComponent(worker.id) + (archive ? '/archive' : '/unarchive'), {
        method: 'POST',
        body: archive ? { reason: 'Retired from the Synapse Worker Catalog' } : {},
      });
      setNotice(archive
        ? 'Worker archived in Synapse. Its ChatGPT conversation was not deleted.'
        : 'Worker restored; its saved conversation is available again.');
      await refresh(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not update this worker.');
    } finally {
      setWorkingId(null);
    }
  }
  function startHandoff(worker: WorkerRecord) {
    setEditingId(worker.id);
    setHandoff(safeMetadataText(worker, 'handoff_md'));
    setNextStep(safeMetadataText(worker, 'next_step'));
    setError(null);
  }
  async function saveHandoff(worker: WorkerRecord) {
    setWorkingId(worker.id);
    setError(null);
    try {
      await apiFetch('/chatgpt-workers/' + encodeURIComponent(worker.id) + '/handoff', {
        method: 'POST',
        body: { handoff_md: handoff.slice(0, 6000), next_step: nextStep.slice(0, 2000) },
      });
      setNotice('Worker handoff saved for future Synapse AI agents.');
      setEditingId(null);
      await refresh(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save the handoff.');
    } finally {
      setWorkingId(null);
    }
  }

  return (
    <Card className='space-y-4 p-4' data-surface-id='chatgpt-worker-catalog'>
      <div className='flex flex-wrap items-start justify-between gap-3'>
        <div>
          <h2 className='flex items-center gap-2 text-lg font-semibold'>
            <UsersRound className='h-5 w-5 text-primary' /> Worker Catalog
          </h2>
          <p className='mt-1 text-sm text-muted-foreground'>
            Keep the conversations, tasks, and handoffs. Close idle Chrome tabs without losing their workers.
          </p>
          <p className='mt-2 text-xs text-muted-foreground'>
            {openCount} open · {workingCount} working · {parkedCount} parked · {records.length} total
          </p>
        </div>
        <div className='flex gap-2'>
          <Button size='sm' variant='outline' onClick={() => void refresh()} disabled={loading}>
            <RefreshCw className='h-4 w-4' /> Refresh
          </Button>
          <Button size='sm' onClick={() => void openExternal(WORKER_PROJECT_URL)}>
            <ArrowUpRight className='h-4 w-4' /> New worker chat
          </Button>
        </div>
      </div>

      <div className='flex flex-wrap items-center gap-2'>
        <Search className='h-4 w-4 text-muted-foreground' />
        <Input
          aria-label='Search saved AI workers'
          className='min-w-[210px] max-w-sm'
          placeholder='Search workers, assignments, handoffs...'
          value={search}
          onChange={event => setSearch(event.target.value)}
        />
        <select
          aria-label='Filter workers'
          value={filter}
          onChange={event => setFilter(event.target.value as WorkerFilter)}
          className='rounded-lg border border-border bg-background px-3 py-2 text-sm'
        >
          {FILTERS.map(item => <option key={item.key} value={item.key}>{item.label}</option>)}
        </select>
      </div>

      {error && <p role='alert' className='text-sm text-red-400'>{error}</p>}
      {notice && <p role='status' className='text-sm text-emerald-400'>{notice}</p>}
      {loading && <p className='text-sm text-muted-foreground'>Loading saved workers...</p>}
      {!loading && visible.length === 0 && (
        <div className='rounded-xl border border-dashed border-border p-5 text-sm text-muted-foreground'>
          No workers match this view. The extension registers conversations in the Synapse2GPT Workers project.
          Existing browser conversations require the updated extension and backend to observe them first.
        </div>
      )}
      <div className='grid gap-3 md:grid-cols-2'>
        {visible.map(worker => {
          const task = safeMetadataText(worker, 'current_task');
          const savedHandoff = safeMetadataText(worker, 'handoff_md');
          const savedNextStep = safeMetadataText(worker, 'next_step');
          const busy = workingId === worker.id;
          const active = worker.open_in_browser && worker.browser_activity === 'active';
          return (
            <div className='min-w-0 rounded-xl border border-border/70 bg-secondary/20 p-4' key={worker.id}>
              <div className='flex items-start justify-between gap-3'>
                <div className='min-w-0'>
                  <h3 className='truncate font-semibold' title={worker.title}>{worker.title || 'Untitled worker'}</h3>
                  <p className='truncate text-xs text-muted-foreground'>
                    {worker.project_id} · {worker.role_id || 'ChatGPT UI worker'}
                  </p>
                </div>
                <span className='shrink-0 rounded-full border border-border px-2 py-1 text-xs'>
                  {worker.status === 'archived' ? 'Archived' : active ? 'Working' :
                    worker.open_in_browser ? 'Open' : 'Parked'}
                </span>
              </div>
              <p className='mt-3 flex items-center gap-2 text-xs text-muted-foreground'>
                <Clock3 className='h-3.5 w-3.5' />
                Last used {new Date(worker.last_used_at).toLocaleString()}
              </p>
              {task && <p className='mt-3 line-clamp-3 text-sm' title={task}>
                <span className='font-medium'>Assignment:</span> {task}
              </p>}
              {!!worker.work_item_ids?.length && <p className='mt-2 break-words text-xs text-muted-foreground'>
                Work items: {worker.work_item_ids.join(', ')}
              </p>}
              {savedHandoff && <p className='mt-3 whitespace-pre-wrap text-sm text-muted-foreground'>
                <span className='font-medium text-foreground'>Handoff:</span> {savedHandoff}
              </p>}
              {savedNextStep && <p className='mt-2 text-sm text-muted-foreground'>
                <span className='font-medium text-foreground'>Next:</span> {savedNextStep}
              </p>}
              {worker.status === 'archived' && worker.archived_reason && (
                <p className='mt-2 text-xs text-muted-foreground'>Archived: {worker.archived_reason}</p>
              )}
              {editingId === worker.id && (
                <div className='mt-4 space-y-2'>
                  <label className='block text-xs font-medium'>Handoff for the next AI
                    <textarea
                      className='mt-1 w-full rounded-md border border-border bg-background p-2 text-sm'
                      rows={4} maxLength={6000} value={handoff}
                      onChange={event => setHandoff(event.target.value)}
                      placeholder='Verified work, files touched, tests, blockers...'
                    />
                  </label>
                  <label className='block text-xs font-medium'>Next step
                    <Input maxLength={2000} value={nextStep} onChange={event => setNextStep(event.target.value)} />
                  </label>
                  <div className='flex gap-2'>
                    <Button size='sm' disabled={busy} onClick={() => void saveHandoff(worker)}>
                      {busy ? <Loader2 className='h-4 w-4 animate-spin' /> : <CheckCircle2 className='h-4 w-4' />}
                      Save handoff
                    </Button>
                    <Button size='sm' variant='outline' onClick={() => setEditingId(null)}>Cancel</Button>
                  </div>
                </div>
              )}
              <div className='mt-4 flex flex-wrap gap-2'>
                <Button
                  size='sm' variant='outline'
                  disabled={worker.status === 'archived' || !WORKER_CONVERSATION_URL.test(worker.conversation_url)}
                  onClick={() => void openWorker(worker)}
                >
                  <ArrowUpRight className='h-4 w-4' /> Resume
                </Button>
                <Button size='sm' variant='outline' onClick={() => startHandoff(worker)}>
                  <FilePenLine className='h-4 w-4' /> Handoff
                </Button>
                <Button
                  size='sm' variant='outline'
                  disabled={busy || active}
                  onClick={() => void changeArchive(worker, worker.status !== 'archived')}
                >
                  {busy ? <Loader2 className='h-4 w-4 animate-spin' /> :
                    worker.status === 'archived' ? <RotateCcw className='h-4 w-4' /> : <Archive className='h-4 w-4' />}
                  {worker.status === 'archived' ? 'Restore' : 'Archive'}
                </Button>
              </div>
            </div>
          );
        })}
      </div>
    </Card>
  );
}
