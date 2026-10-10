import { useCallback, useEffect, useState } from 'react';
import { Check, Circle, Plus, RefreshCw, RotateCcw } from 'lucide-react';
import { getMasterTodo, mutateMasterTodo, setMasterTodoReminder, type MasterTodoSnapshot } from '@shared/master-todo-client';

function describe(error: unknown): string {
  return error instanceof Error ? error.message : 'The planner request failed. Check the Synapse connection.';
}

export function MasterTodoPage(): JSX.Element {
  const [data, setData] = useState<MasterTodoSnapshot | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [title, setTitle] = useState('');
  const load = useCallback(async () => {
    setLoading(true);
    try {
      setData(await getMasterTodo());
      setError('');
    } catch (err) {
      setError(describe(err));
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => { void load(); }, [load]);
  const update = async (action: 'add' | 'complete' | 'reopen', taskId?: string) => {
    if (saving || (action === 'add' && !title.trim())) return;
    setSaving(true);
    try {
      const updated = await mutateMasterTodo({
        action,
        event_id: crypto.randomUUID(),
        ...(taskId ? { task_id: taskId } : {}),
        ...(action === 'add' ? { title: title.trim() } : {}),
        ...(data ? { expected_revision: data.revision, day: data.date } : {}),
      });
      setData(updated);
      setError('');
      if (action === 'add') setTitle('');
    } catch (err) {
      setError(describe(err));
      await load(); // Refresh stale revisions before allowing another mutation.
    } finally {
      setSaving(false);
    }
  };
  const saveReminder = async (value: string) => {
    if (!data || saving) return;
    setSaving(true);
    try {
      setData(await setMasterTodoReminder(value || null, data.revision));
      setError('');
    } catch (err) {
      setError(describe(err));
      await load();
    } finally {
      setSaving(false);
    }
  };
  const remaining = data?.tasks.filter(task => !task.done_today).length ?? 0;
  return (
    <section aria-label='Master To-Do List' className='mx-auto flex w-full max-w-4xl flex-col gap-5 px-1 pb-8'>
      <header className='flex flex-wrap items-center justify-between gap-3'>
        <div>
          <h2 className='text-2xl font-semibold tracking-tight'>Master To-Do List</h2>
          <p className='text-sm text-muted-foreground'>One shared action list. Daily items refresh each day.</p>
        </div>
        <button type='button' aria-label='Refresh to-do list' onClick={() => void load()} disabled={loading || saving} className='inline-flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-sm hover:bg-accent disabled:opacity-50'>
          <RefreshCw size={16} aria-hidden='true' /> Refresh
        </button>
      </header>
      {error && <div role='alert' className='rounded-lg border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive'>{error}</div>}
      <div className='rounded-2xl border border-border bg-card p-4 shadow-sm'>
        <form className='flex flex-col gap-2 sm:flex-row' onSubmit={event => { event.preventDefault(); void update('add'); }}>
          <input aria-label='New task title' placeholder='What do you need to do?' maxLength={240} value={title} onChange={event => setTitle(event.target.value)} className='min-w-0 flex-1 rounded-lg border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring' />
          <button disabled={!title.trim() || saving} type='submit' className='inline-flex min-h-10 items-center justify-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50'><Plus size={16} aria-hidden='true' />Add task</button>
        </form>
      </div>
      <div className='flex flex-wrap items-center gap-3 rounded-xl border border-border bg-card p-3'>
        <label htmlFor='master-todo-reminder' className='text-sm font-medium'>Daily review time</label>
        <input id='master-todo-reminder' type='time' key={data?.reminder_time ?? 'unset'} defaultValue={data?.reminder_time ?? ''} disabled={!data || saving} onBlur={event => { if (event.target.value !== (data?.reminder_time ?? '')) void saveReminder(event.target.value); }} className='rounded-lg border border-input bg-background px-3 py-2 text-sm' />
        <span className='text-xs text-muted-foreground'>Saves your preference; notification delivery is not yet enabled.</span>
      </div>
      <div className='flex items-center justify-between gap-2 text-sm text-muted-foreground'>
        <span aria-live='polite'>{loading ? 'Loading tasks…' : `${remaining} remaining · ${data?.tasks.length ?? 0} total`}</span>
        <span>{data?.date ?? ''}</span>
      </div>
      {!loading && data?.tasks.length === 0 && <p className='rounded-xl border border-dashed border-border p-8 text-center text-muted-foreground'>No tasks yet. Add your first one above.</p>}
      <ul aria-label='Tasks' className='flex flex-col gap-2'>
        {data?.tasks.map(task => (
          <li key={task.id} className='flex items-center gap-3 rounded-xl border border-border bg-card p-3 shadow-sm'>
            <button type='button' disabled={saving} aria-label={`${task.done_today ? 'Reopen' : 'Complete'} ${task.title}`} onClick={() => void update(task.done_today ? 'reopen' : 'complete', task.id)} className='flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-border hover:bg-accent disabled:opacity-50'>
              {task.done_today ? <Check size={19} className='text-emerald-500' /> : <Circle size={19} className='text-muted-foreground' />}
            </button>
            <div className='min-w-0 flex-1'>
              <div className={task.done_today ? 'break-words text-sm text-muted-foreground line-through' : 'break-words text-sm font-medium'}>{task.title}</div>
              <div className='mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground'>
                <span>{task.category}</span>
                {task.minutes != null && <span>{task.minutes} min</span>}
                {task.budget_usd != null && <span>Up to ${task.budget_usd}</span>}
                {task.recurrence && <span className='inline-flex items-center gap-1'><RotateCcw size={12} />{task.recurrence}</span>}
              </div>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
