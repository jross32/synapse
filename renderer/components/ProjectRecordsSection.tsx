// Per-project decision records, backlog, and version history (ADR-0011).
// Rendered inside ProjectDetailModal. Three tabs, each with a frictionless
// quick-add. ADRs support the quick-idea -> promote-to-numbered flow.

import { useEffect, useState } from 'react';
import {
  ArrowUpCircle,
  FileText,
  History,
  ListTodo,
  Loader2,
  Plus,
  Trash2,
} from 'lucide-react';

import {
  createAdr,
  createBacklogItem,
  createVersion,
  deleteAdr,
  deleteBacklogItem,
  deleteVersion,
  getProjectRecords,
  promoteAdr,
  updateBacklogItem,
  type ProjectAdr,
  type ProjectBacklogItem,
  type ProjectBacklogPriority,
  type ProjectBacklogStatus,
  type ProjectRecords,
  type ProjectVersion,
} from '@shared/project-records-client';
import { cn } from '@shared/utils';
import { Badge } from './ui/badge';
import { Button } from './ui/button';
import { Input } from './ui/input';

type Tab = 'decisions' | 'backlog' | 'history';

const SELECT_CLASS =
  'h-8 rounded-md border border-input bg-transparent px-2 text-xs text-foreground';

const ADR_PROMOTABLE: ProjectAdr['status'][] = ['idea', 'draft', 'proposed'];

function adrChip(adr: ProjectAdr): { label: string; cls: string } {
  switch (adr.status) {
    case 'accepted':
      return { label: `ADR-${String(adr.number ?? '?').padStart(3, '0')}`, cls: 'border-primary/30 bg-primary/10 text-primary' };
    case 'superseded':
      return { label: 'Superseded', cls: 'border-border bg-secondary text-muted-foreground line-through' };
    case 'rejected':
      return { label: 'Rejected', cls: 'border-border bg-secondary text-muted-foreground' };
    case 'proposed':
      return { label: 'Proposed', cls: 'border-sky-500/25 bg-sky-500/10 text-sky-300' };
    case 'draft':
      return { label: 'Draft', cls: 'border-amber-500/25 bg-amber-500/10 text-amber-300' };
    default:
      return { label: 'Idea', cls: 'border-border bg-secondary text-muted-foreground' };
  }
}

const PRIORITY_CLS: Record<ProjectBacklogPriority, string> = {
  high: 'border-rose-500/25 bg-rose-500/10 text-rose-300',
  medium: 'border-amber-500/25 bg-amber-500/10 text-amber-300',
  low: 'border-border bg-secondary text-muted-foreground',
};

export function ProjectRecordsSection({ projectId }: { projectId: string }): JSX.Element {
  const [tab, setTab] = useState<Tab>('decisions');
  const [records, setRecords] = useState<ProjectRecords | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Quick-add inputs.
  const [ideaTitle, setIdeaTitle] = useState('');
  const [taskTitle, setTaskTitle] = useState('');
  const [taskPriority, setTaskPriority] = useState<ProjectBacklogPriority>('medium');
  const [verName, setVerName] = useState('');
  const [verChanges, setVerChanges] = useState('');

  async function refresh(): Promise<void> {
    try {
      setRecords(await getProjectRecords(projectId));
      setError(null);
    } catch (e) {
      setError((e as Error).message || 'Could not load project records.');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    setLoading(true);
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  async function run(fn: () => Promise<unknown>): Promise<void> {
    setBusy(true);
    setError(null);
    try {
      await fn();
      await refresh();
    } catch (e) {
      setError((e as Error).message || 'Action failed.');
    } finally {
      setBusy(false);
    }
  }

  const adrs = records?.adrs ?? [];
  const backlog = records?.backlog ?? [];
  const versions = records?.versions ?? [];

  return (
    <div className='rounded-md border border-border bg-secondary/20 p-3'>
      <div className='mb-3 flex items-center gap-1' role='tablist' aria-label='Project records'>
        <TabButton active={tab === 'decisions'} onClick={() => setTab('decisions')} icon={FileText} label='Decisions' count={adrs.length} />
        <TabButton active={tab === 'backlog'} onClick={() => setTab('backlog')} icon={ListTodo} label='Backlog' count={backlog.length} />
        <TabButton active={tab === 'history'} onClick={() => setTab('history')} icon={History} label='History' count={versions.length} />
        {(loading || busy) && <Loader2 className='ml-auto h-4 w-4 animate-spin text-primary' />}
      </div>

      {error && (
        <p role='alert' className='mb-2 text-xs text-destructive'>
          {error}
        </p>
      )}

      {/* Decisions */}
      {tab === 'decisions' && (
        <div className='flex flex-col gap-2'>
          <form
            className='flex items-center gap-2'
            onSubmit={(e) => {
              e.preventDefault();
              if (!ideaTitle.trim()) return;
              void run(() => createAdr(projectId, { title: ideaTitle.trim() })).then(() => setIdeaTitle(''));
            }}
          >
            <Input
              value={ideaTitle}
              onChange={(e) => setIdeaTitle(e.target.value)}
              placeholder='Quick idea or decision (e.g. "switch to Postgres")'
              aria-label='Quick ADR idea'
            />
            <Button type='submit' size='sm' disabled={busy || !ideaTitle.trim()}>
              <Plus className='h-4 w-4' /> Idea
            </Button>
          </form>
          {adrs.length === 0 ? (
            <Empty text='No decisions yet. Drop a quick idea above; promote it to a numbered ADR once it is decided.' />
          ) : (
            adrs.map((adr) => {
              const chip = adrChip(adr);
              return (
                <Row key={adr.id}>
                  <Badge className={cn('border shrink-0 font-mono', chip.cls)}>{chip.label}</Badge>
                  <div className='min-w-0 flex-1'>
                    <p className='truncate text-sm'>{adr.title}</p>
                    {adr.tags.length > 0 && (
                      <p className='truncate text-[11px] text-muted-foreground'>{adr.tags.join(' · ')}</p>
                    )}
                  </div>
                  {ADR_PROMOTABLE.includes(adr.status) && (
                    <Button
                      size='sm'
                      variant='outline'
                      disabled={busy}
                      onClick={() => void run(() => promoteAdr(adr.id))}
                      title='Officially write this in as a numbered ADR'
                    >
                      <ArrowUpCircle className='h-4 w-4' /> Promote
                    </Button>
                  )}
                  <DeleteButton label={adr.title} disabled={busy} onClick={() => void run(() => deleteAdr(adr.id))} />
                </Row>
              );
            })
          )}
        </div>
      )}

      {/* Backlog */}
      {tab === 'backlog' && (
        <div className='flex flex-col gap-2'>
          <form
            className='flex items-center gap-2'
            onSubmit={(e) => {
              e.preventDefault();
              if (!taskTitle.trim()) return;
              void run(() =>
                createBacklogItem(projectId, { title: taskTitle.trim(), priority: taskPriority })
              ).then(() => setTaskTitle(''));
            }}
          >
            <Input
              value={taskTitle}
              onChange={(e) => setTaskTitle(e.target.value)}
              placeholder='Backlog item'
              aria-label='New backlog item'
            />
            <select
              value={taskPriority}
              onChange={(e) => setTaskPriority(e.target.value as ProjectBacklogPriority)}
              className={SELECT_CLASS}
              aria-label='Priority'
            >
              <option value='low'>Low</option>
              <option value='medium'>Medium</option>
              <option value='high'>High</option>
            </select>
            <Button type='submit' size='sm' disabled={busy || !taskTitle.trim()}>
              <Plus className='h-4 w-4' /> Add
            </Button>
          </form>
          {backlog.length === 0 ? (
            <Empty text='No backlog items yet. Capture what is left to do on this project.' />
          ) : (
            backlog.map((item) => (
              <Row key={item.id}>
                <Badge className={cn('border shrink-0', PRIORITY_CLS[item.priority])}>{item.priority}</Badge>
                <p className={cn('min-w-0 flex-1 truncate text-sm', item.status === 'done' && 'text-muted-foreground line-through')}>
                  {item.title}
                </p>
                <select
                  value={item.status}
                  onChange={(e) =>
                    void run(() =>
                      updateBacklogItem(item.id, { status: e.target.value as ProjectBacklogStatus })
                    )
                  }
                  className={SELECT_CLASS}
                  aria-label={`Status for ${item.title}`}
                  disabled={busy}
                >
                  <option value='todo'>To do</option>
                  <option value='in_progress'>In progress</option>
                  <option value='done'>Done</option>
                  <option value='wontfix'>Won&apos;t fix</option>
                </select>
                <DeleteButton label={item.title} disabled={busy} onClick={() => void run(() => deleteBacklogItem(item.id))} />
              </Row>
            ))
          )}
        </div>
      )}

      {/* History */}
      {tab === 'history' && (
        <div className='flex flex-col gap-2'>
          <form
            className='flex flex-col gap-2'
            onSubmit={(e) => {
              e.preventDefault();
              if (!verName.trim()) return;
              void run(() =>
                createVersion(projectId, { version: verName.trim(), changes_md: verChanges.trim() })
              ).then(() => {
                setVerName('');
                setVerChanges('');
              });
            }}
          >
            <div className='flex items-center gap-2'>
              <Input
                value={verName}
                onChange={(e) => setVerName(e.target.value)}
                placeholder='Version (e.g. 0.2.0)'
                aria-label='Version number'
                className='max-w-[160px]'
              />
              <Input
                value={verChanges}
                onChange={(e) => setVerChanges(e.target.value)}
                placeholder='What changed in this version'
                aria-label='Version changes'
              />
              <Button type='submit' size='sm' disabled={busy || !verName.trim()}>
                <Plus className='h-4 w-4' /> Add
              </Button>
            </div>
          </form>
          {versions.length === 0 ? (
            <Empty text='No version history yet. Log each release and what changed.' />
          ) : (
            versions.map((v) => (
              <Row key={v.id}>
                <Badge variant='outline' className='shrink-0 font-mono'>{v.version}</Badge>
                <p className='min-w-0 flex-1 truncate text-sm text-muted-foreground'>
                  {v.changes_md || <span className='italic'>no notes</span>}
                </p>
                <DeleteButton label={v.version} disabled={busy} onClick={() => void run(() => deleteVersion(v.id))} />
              </Row>
            ))
          )}
        </div>
      )}
    </div>
  );
}

function TabButton({
  active,
  onClick,
  icon: Icon,
  label,
  count,
}: {
  active: boolean;
  onClick: () => void;
  icon: typeof FileText;
  label: string;
  count: number;
}): JSX.Element {
  return (
    <button
      type='button'
      role='tab'
      aria-selected={active}
      onClick={onClick}
      className={cn(
        'flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors',
        active ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground'
      )}
    >
      <Icon className='h-3.5 w-3.5' aria-hidden='true' />
      {label}
      {count > 0 && <span className={cn('rounded-full px-1.5 text-[10px]', active ? 'bg-primary-foreground/20' : 'bg-secondary')}>{count}</span>}
    </button>
  );
}

function Row({ children }: { children: React.ReactNode }): JSX.Element {
  return (
    <div className='flex items-center gap-2 rounded-md border border-border bg-card px-3 py-2'>
      {children}
    </div>
  );
}

function Empty({ text }: { text: string }): JSX.Element {
  return (
    <p className='rounded-md border border-dashed border-border p-3 text-xs text-muted-foreground'>
      {text}
    </p>
  );
}

function DeleteButton({
  label,
  onClick,
  disabled,
}: {
  label: string;
  onClick: () => void;
  disabled?: boolean;
}): JSX.Element {
  return (
    <button
      type='button'
      onClick={onClick}
      disabled={disabled}
      aria-label={`Delete ${label}`}
      title={`Delete ${label}`}
      className='shrink-0 rounded p-1 text-muted-foreground opacity-70 transition hover:bg-accent hover:text-destructive hover:opacity-100 disabled:opacity-40'
    >
      <Trash2 className='h-3.5 w-3.5' />
    </button>
  );
}
