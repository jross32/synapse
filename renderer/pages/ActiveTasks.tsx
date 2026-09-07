import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import {
  AlarmClock,
  CalendarClock,
  CheckCircle2,
  Clock3,
  History,
  Loader2,
  Pause,
  Play,
  Plus,
  RefreshCw,
  RotateCcw,
  Trash2,
  XCircle,
} from 'lucide-react';

import {
  createActiveTask,
  deleteActiveTask,
  getActiveTaskSummary,
  listActiveTaskRuns,
  listActiveTasks,
  runActiveTaskNow,
  updateActiveTask,
  type ActiveTask,
  type ActiveTaskRun,
  type ActiveTaskSummary,
} from '@shared/active-tasks-client';
import { useDaemon } from '@shared/daemon-context';
import { formatLocal } from '@shared/format-time';
import { cn } from '@shared/utils';
import { Badge } from '../components/ui/badge';
import { Button } from '../components/ui/button';
import { Card } from '../components/ui/card';
import { Input } from '../components/ui/input';
import { Modal } from '../components/ui/modal';

const CADENCES = [
  { label: '15 min', seconds: 900 },
  { label: '30 min', seconds: 1800 },
  { label: '1 hour', seconds: 3600 },
  { label: '2 hours', seconds: 7200 },
  { label: '6 hours', seconds: 21600 },
  { label: 'Daily', seconds: 86400 },
];

const RUNTIMES = [
  { value: 'chatgpt_web', label: 'ChatGPT Web' },
  { value: 'auto', label: 'Auto' },
  { value: 'claude', label: 'Claude' },
  { value: 'codex', label: 'Codex' },
  { value: 'copilot', label: 'Copilot' },
  { value: 'gemini', label: 'Gemini' },
  { value: 'local', label: 'Local AI' },
];

interface FormState {
  projectId: string;
  name: string;
  prompt: string;
  intervalSeconds: number;
  runtime: string;
  maxRuns: string;
  noOverlap: boolean;
}

const EMPTY_FORM: FormState = {
  projectId: '',
  name: '',
  prompt: '',
  intervalSeconds: 3600,
  runtime: 'chatgpt_web',
  maxRuns: '',
  noOverlap: true,
};

export function ActiveTasksPage(): JSX.Element {
  const { projects } = useDaemon();
  const [tasks, setTasks] = useState<ActiveTask[]>([]);
  const [summary, setSummary] = useState<ActiveTaskSummary | null>(null);
  const [projectFilter, setProjectFilter] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [historyTask, setHistoryTask] = useState<ActiveTask | null>(null);
  const [history, setHistory] = useState<ActiveTaskRun[]>([]);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);

  const projectNames = useMemo(
    () => new Map(projects.map((project) => [project.id, project.name])),
    [projects]
  );

  const refresh = useCallback(async () => {
    setError(null);
    try {
      const [list, nextSummary] = await Promise.all([
        listActiveTasks(projectFilter || undefined),
        getActiveTaskSummary(),
      ]);
      setTasks(list.tasks);
      setSummary(nextSummary);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load Active Tasks');
    } finally {
      setLoading(false);
    }
  }, [projectFilter]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  function openCreate(): void {
    const defaultProject = projectFilter || projects[0]?.id || '';
    setForm({ ...EMPTY_FORM, projectId: defaultProject });
    setCreateOpen(true);
  }

  async function createTask(): Promise<void> {
    if (!form.projectId || !form.name.trim()) return;
    setBusyId('create');
    setError(null);
    try {
      await createActiveTask({
        project_id: form.projectId,
        name: form.name.trim(),
        prompt: form.prompt.trim(),
        interval_seconds: form.intervalSeconds,
        preferred_runtime: form.runtime,
        max_runs: form.maxRuns ? Number(form.maxRuns) : null,
        no_overlap: form.noOverlap,
        enabled: true,
      });
      setCreateOpen(false);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create Active Task');
    } finally {
      setBusyId(null);
    }
  }

  async function toggleTask(task: ActiveTask): Promise<void> {
    setBusyId(task.id);
    setError(null);
    try {
      await updateActiveTask(task.id, { enabled: !task.enabled });
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update Active Task');
    } finally {
      setBusyId(null);
    }
  }

  async function runNow(task: ActiveTask): Promise<void> {
    setBusyId(task.id);
    setError(null);
    try {
      await runActiveTaskNow(task.id);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to dispatch Active Task');
    } finally {
      setBusyId(null);
    }
  }

  async function removeTask(task: ActiveTask): Promise<void> {
    if (!window.confirm(`Delete Active Task “${task.name}”? Its run history will also be removed.`)) return;
    setBusyId(task.id);
    try {
      await deleteActiveTask(task.id);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete Active Task');
    } finally {
      setBusyId(null);
    }
  }

  async function showHistory(task: ActiveTask): Promise<void> {
    setHistoryTask(task);
    setHistory([]);
    try {
      const result = await listActiveTaskRuns(task.id, 30);
      setHistory(result.runs);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load task history');
    }
  }

  return (
    <div className='mx-auto flex w-full max-w-7xl flex-col gap-4 p-1 pb-8'>
      <div className='flex flex-col gap-3 rounded-xl border border-border/70 bg-card p-4 sm:flex-row sm:items-center sm:justify-between'>
        <div>
          <div className='flex items-center gap-2'>
            <AlarmClock className='h-5 w-5 text-primary' />
            <h2 className='text-lg font-semibold'>Active Tasks</h2>
          </div>
          <p className='mt-1 max-w-3xl text-sm text-muted-foreground'>
            Synapse schedules these tasks locally and dispatches guarded AI project iterations when they are due.
            They do not consume ChatGPT's built-in task slots.
          </p>
        </div>
        <div className='flex shrink-0 gap-2'>
          <Button variant='outline' size='sm' onClick={() => void refresh()} disabled={loading}>
            <RefreshCw className={cn('h-4 w-4', loading && 'animate-spin')} />
            Refresh
          </Button>
          <Button size='sm' onClick={openCreate}>
            <Plus className='h-4 w-4' />
            New task
          </Button>
        </div>
      </div>

      <div className='grid gap-3 sm:grid-cols-4'>
        <Metric label='Total' value={summary?.count ?? tasks.length} />
        <Metric label='Enabled' value={summary?.enabled ?? tasks.filter((task) => task.enabled).length} />
        <Metric label='Due now' value={summary?.due ?? 0} />
        <Metric label='Running / dispatched' value={summary?.running_or_dispatched ?? 0} />
      </div>

      <div className='flex flex-wrap items-center gap-2'>
        <label className='text-xs font-medium text-muted-foreground' htmlFor='active-task-project-filter'>Project</label>
        <select
          id='active-task-project-filter'
          value={projectFilter}
          onChange={(event) => setProjectFilter(event.target.value)}
          className='h-9 min-w-[220px] rounded-md border border-input bg-background px-3 text-sm'
        >
          <option value=''>All projects</option>
          {projects.map((project) => (
            <option key={project.id} value={project.id}>{project.name}</option>
          ))}
        </select>
      </div>

      {error && (
        <div role='alert' className='rounded-lg border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive'>
          {error}
        </div>
      )}

      {loading ? (
        <div className='flex min-h-48 items-center justify-center gap-2 text-sm text-muted-foreground'>
          <Loader2 className='h-4 w-4 animate-spin' /> Loading Active Tasks…
        </div>
      ) : tasks.length === 0 ? (
        <Card className='p-8 text-center'>
          <AlarmClock className='mx-auto h-9 w-9 text-muted-foreground' />
          <h3 className='mt-3 font-semibold'>No Active Tasks yet</h3>
          <p className='mx-auto mt-1 max-w-xl text-sm text-muted-foreground'>
            Create a standing project directive such as “continue AI WORLD every hour.” Synapse persists the schedule across daemon restarts.
          </p>
          <Button className='mt-4' size='sm' onClick={openCreate}><Plus className='h-4 w-4' />Create task</Button>
        </Card>
      ) : (
        <div className='grid gap-3 xl:grid-cols-2'>
          {tasks.map((task) => (
            <TaskCard
              key={task.id}
              task={task}
              projectName={projectNames.get(task.project_id) ?? task.project_id}
              busy={busyId === task.id}
              onToggle={() => void toggleTask(task)}
              onRun={() => void runNow(task)}
              onHistory={() => void showHistory(task)}
              onDelete={() => void removeTask(task)}
            />
          ))}
        </div>
      )}

      <CreateTaskModal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        form={form}
        setForm={setForm}
        projects={projects.map((project) => ({ id: project.id, name: project.name }))}
        busy={busyId === 'create'}
        onCreate={() => void createTask()}
      />

      <HistoryModal task={historyTask} runs={history} onClose={() => setHistoryTask(null)} />
    </div>
  );
}

function Metric({ label, value }: { label: string; value: number }): JSX.Element {
  return (
    <Card className='p-3'>
      <p className='text-xs font-medium text-muted-foreground'>{label}</p>
      <p className='mt-1 text-2xl font-semibold tabular-nums'>{value}</p>
    </Card>
  );
}

function TaskCard({
  task,
  projectName,
  busy,
  onToggle,
  onRun,
  onHistory,
  onDelete,
}: {
  task: ActiveTask;
  projectName: string;
  busy: boolean;
  onToggle: () => void;
  onRun: () => void;
  onHistory: () => void;
  onDelete: () => void;
}): JSX.Element {
  const statusTone = task.last_status === 'failed' || task.last_status === 'interrupted'
    ? 'border-destructive/40 text-destructive'
    : task.last_status === 'skipped_overlap'
      ? 'border-amber-500/40 text-amber-600 dark:text-amber-400'
      : 'border-border text-muted-foreground';
  return (
    <Card className='flex flex-col gap-3 p-4'>
      <div className='flex items-start justify-between gap-3'>
        <div className='min-w-0'>
          <div className='flex flex-wrap items-center gap-2'>
            <h3 className='truncate font-semibold'>{task.name}</h3>
            <Badge variant={task.enabled ? 'default' : 'secondary'}>{task.enabled ? 'Enabled' : 'Paused'}</Badge>
            {task.last_status && <span className={cn('rounded border px-1.5 py-0.5 text-[10px]', statusTone)}>{task.last_status.replace(/_/g, ' ')}</span>}
          </div>
          <p className='mt-1 text-xs text-muted-foreground'>{projectName} · {runtimeLabel(task.preferred_runtime)}</p>
        </div>
        <button type='button' onClick={onDelete} disabled={busy} className='rounded p-1.5 text-muted-foreground hover:bg-destructive/10 hover:text-destructive' aria-label={`Delete ${task.name}`}>
          <Trash2 className='h-4 w-4' />
        </button>
      </div>

      <p className='line-clamp-3 min-h-[3.75rem] whitespace-pre-wrap text-sm text-foreground/90'>
        {task.prompt || 'Continue the project according to its current AI context and highest-value verified next step.'}
      </p>

      <div className='grid grid-cols-2 gap-2 text-xs sm:grid-cols-4'>
        <SmallFact icon={Clock3} label='Cadence' value={cadenceLabel(task)} />
        <SmallFact icon={CalendarClock} label='Next run' value={task.next_run_at ? formatLocal(task.next_run_at, 'short') : '—'} />
        <SmallFact icon={RotateCcw} label='Runs' value={task.max_runs ? `${task.run_count}/${task.max_runs}` : String(task.run_count)} />
        <SmallFact icon={task.no_overlap ? CheckCircle2 : XCircle} label='Overlap' value={task.no_overlap ? 'Blocked' : 'Allowed'} />
      </div>

      {task.last_error && <p className='rounded bg-destructive/10 px-2.5 py-2 text-xs text-destructive'>{task.last_error}</p>}

      <div className='mt-auto flex flex-wrap gap-2 border-t border-border/60 pt-3'>
        <Button size='sm' variant={task.enabled ? 'outline' : 'default'} disabled={busy} onClick={onToggle}>
          {busy ? <Loader2 className='h-4 w-4 animate-spin' /> : task.enabled ? <Pause className='h-4 w-4' /> : <Play className='h-4 w-4' />}
          {task.enabled ? 'Pause' : 'Resume'}
        </Button>
        <Button size='sm' variant='outline' disabled={busy} onClick={onRun}>
          <Play className='h-4 w-4' /> Run now
        </Button>
        <Button size='sm' variant='ghost' onClick={onHistory}>
          <History className='h-4 w-4' /> History
        </Button>
      </div>
    </Card>
  );
}

function SmallFact({ icon: Icon, label, value }: { icon: typeof Clock3; label: string; value: string }): JSX.Element {
  return (
    <div className='rounded-lg bg-secondary/35 p-2'>
      <span className='flex items-center gap-1 text-muted-foreground'><Icon className='h-3.5 w-3.5' />{label}</span>
      <span className='mt-1 block truncate font-medium text-foreground' title={value}>{value}</span>
    </div>
  );
}

function CreateTaskModal({
  open,
  onClose,
  form,
  setForm,
  projects,
  busy,
  onCreate,
}: {
  open: boolean;
  onClose: () => void;
  form: FormState;
  setForm: (value: FormState) => void;
  projects: Array<{ id: string; name: string }>;
  busy: boolean;
  onCreate: () => void;
}): JSX.Element {
  return (
    <Modal open={open} onClose={onClose} labelledBy='new-active-task-title' className='max-w-2xl'>
      <div className='space-y-5 p-5'>
        <div>
          <h3 id='new-active-task-title' className='text-xl font-semibold'>New Active Task</h3>
          <p className='mt-1 text-sm text-muted-foreground'>This schedule lives in Synapse, not ChatGPT Tasks.</p>
        </div>
        <div className='grid gap-4 sm:grid-cols-2'>
          <Field label='Project'>
            <select value={form.projectId} onChange={(event) => setForm({ ...form, projectId: event.target.value })} className='h-9 w-full rounded-md border border-input bg-background px-3 text-sm'>
              <option value=''>Choose a project</option>
              {projects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}
            </select>
          </Field>
          <Field label='Task name'>
            <Input value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} placeholder='AI WORLD continuous development' />
          </Field>
          <Field label='Cadence'>
            <select value={form.intervalSeconds} onChange={(event) => setForm({ ...form, intervalSeconds: Number(event.target.value) })} className='h-9 w-full rounded-md border border-input bg-background px-3 text-sm'>
              {CADENCES.map((item) => <option key={item.seconds} value={item.seconds}>{item.label}</option>)}
            </select>
          </Field>
          <Field label='Runtime'>
            <select value={form.runtime} onChange={(event) => setForm({ ...form, runtime: event.target.value })} className='h-9 w-full rounded-md border border-input bg-background px-3 text-sm'>
              {RUNTIMES.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
            </select>
          </Field>
          <Field label='Max runs (optional)'>
            <Input type='number' min={1} value={form.maxRuns} onChange={(event) => setForm({ ...form, maxRuns: event.target.value })} placeholder='Unlimited' />
          </Field>
          <label className='flex items-center gap-2 self-end rounded-lg border border-border/70 px-3 py-2 text-sm'>
            <input type='checkbox' checked={form.noOverlap} onChange={(event) => setForm({ ...form, noOverlap: event.target.checked })} />
            Prevent overlapping writers
          </label>
        </div>
        <Field label='Standing directive'>
          <textarea
            value={form.prompt}
            onChange={(event) => setForm({ ...form, prompt: event.target.value })}
            rows={7}
            className='w-full resize-y rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring'
            placeholder='Read the project AI context, continue the highest-value verified work, run tests, and leave a handoff.'
          />
        </Field>
        <div className='flex justify-end gap-2'>
          <Button variant='outline' onClick={onClose} disabled={busy}>Cancel</Button>
          <Button onClick={onCreate} disabled={busy || !form.projectId || !form.name.trim()}>
            {busy && <Loader2 className='h-4 w-4 animate-spin' />}
            Create Active Task
          </Button>
        </div>
      </div>
    </Modal>
  );
}

function HistoryModal({ task, runs, onClose }: { task: ActiveTask | null; runs: ActiveTaskRun[]; onClose: () => void }): JSX.Element {
  return (
    <Modal open={task !== null} onClose={onClose} labelledBy='active-task-history-title' className='max-w-3xl'>
      <div className='space-y-4 p-5'>
        <div>
          <h3 id='active-task-history-title' className='text-xl font-semibold'>{task?.name ?? 'Task'} history</h3>
          <p className='mt-1 text-sm text-muted-foreground'>Durable dispatch receipts from the Synapse scheduler.</p>
        </div>
        {runs.length === 0 ? (
          <p className='rounded-lg bg-secondary/35 p-4 text-sm text-muted-foreground'>No runs recorded yet.</p>
        ) : (
          <div className='scrollbar-thin max-h-[55vh] space-y-2 overflow-y-auto'>
            {runs.map((run) => (
              <div key={run.id} className='rounded-lg border border-border/70 p-3 text-sm'>
                <div className='flex flex-wrap items-center justify-between gap-2'>
                  <span className='font-medium'>{run.status.replace(/_/g, ' ')}</span>
                  <span className='text-xs text-muted-foreground'>{formatLocal(run.scheduled_for, 'long')}</span>
                </div>
                <p className='mt-1 text-xs text-muted-foreground'>{run.manual ? 'Manual run' : 'Scheduled run'}{run.dispatch_ref ? ` · ${run.dispatch_ref}` : ''}</p>
                {run.error && <p className='mt-2 text-xs text-destructive'>{run.error}</p>}
              </div>
            ))}
          </div>
        )}
        <div className='flex justify-end'><Button variant='outline' onClick={onClose}>Close</Button></div>
      </div>
    </Modal>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }): JSX.Element {
  return <label className='space-y-1.5 text-sm'><span className='font-medium'>{label}</span>{children}</label>;
}

function cadenceLabel(task: ActiveTask): string {
  if (task.schedule_kind === 'once') return 'One time';
  const seconds = task.interval_seconds ?? 0;
  const preset = CADENCES.find((item) => item.seconds === seconds);
  if (preset) return preset.label;
  if (seconds % 3600 === 0) return `${seconds / 3600}h`;
  if (seconds % 60 === 0) return `${seconds / 60}m`;
  return `${seconds}s`;
}

function runtimeLabel(runtime: string): string {
  return RUNTIMES.find((item) => item.value === runtime)?.label ?? runtime;
}
