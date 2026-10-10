import { useEffect, useState } from 'react';
import { launchAgentWorkItem } from '../lib/agent-squads-client';
import { AlertTriangle, CheckCircle2, CircleDot, RefreshCw } from 'lucide-react';
import {
  getStaffExecution,
  openChatgptWorkerSetupBrowser,
  type StaffExecutionSnapshot,
} from '../lib/staff-client';

/** Connected does not mean running. Work must have a recent session heartbeat. */
export function MayaExecutionPanel(): JSX.Element {
  const [snapshot, setSnapshot] = useState<StaffExecutionSnapshot | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [setupBusy, setSetupBusy] = useState(false);
  const [setupMessage, setSetupMessage] = useState('');
  const [retryingId, setRetryingId] = useState<string | null>(null);
  const [retryMessage, setRetryMessage] = useState('');

  async function retryBlockedPilot(workItemId: string): Promise<void> {
    if (retryingId) return;
    setRetryingId(workItemId);
    setRetryMessage('');
    try {
      await launchAgentWorkItem(workItemId, {
        preferred_runtime: 'chatgpt_web',
        execution_mode: 'automatic',
        authority: 'observe',
        open_in_tab: false,
        timeout_seconds: 600,
      });
      setRetryMessage('Launch requested. Check the heartbeat and work-item handoff for confirmation.');
      await refresh();
    } catch (err) {
      setRetryMessage(err instanceof Error ? err.message : 'Could not retry Maya work item.');
      await refresh();
    } finally {
      setRetryingId(null);
    }
  }

  async function openSetup(): Promise<void> {
    if (setupBusy) return;
    setSetupBusy(true);
    setSetupMessage('');
    try {
      const result = await openChatgptWorkerSetupBrowser();
      setSetupMessage(result.error
        ? result.error
        : result.instructions || 'The worker setup browser was requested.');
    } catch (err) {
      setSetupMessage(err instanceof Error ? err.message : 'Could not open worker setup browser.');
    } finally {
      setSetupBusy(false);
    }
  }

  async function refresh(): Promise<void> {
    setBusy(true);
    try {
      const next = await getStaffExecution('maya');
      setSnapshot(next);
      setError('');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unable to read Maya work status.');
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => { void refresh(); }, []);

  const confirmed = snapshot?.counts.running_confirmed ?? 0;
  const queued = snapshot?.counts.queued ?? 0;
  const stale = snapshot?.counts.stale_or_disconnected ?? 0;
  const finished = snapshot?.counts.completed_with_handoff ?? 0;

  return (
    <section className='rounded-3xl border border-border bg-background/40 p-5' aria-label='Maya verified work cycle'>
      <div className='flex flex-wrap items-start justify-between gap-3'>
        <div>
          <p className='flex items-center gap-2 text-sm font-semibold text-foreground'>
            <CircleDot className='h-4 w-4 text-primary' /> Work cycle
          </p>
          <p className='mt-1 text-xs text-muted-foreground'>
            Verified against linked assignments and worker heartbeats, not the profile status.
          </p>
        </div>
        <button
          type='button'
          onClick={() => void refresh()}
          disabled={busy}
          className='rounded-xl border border-border p-2 text-muted-foreground hover:text-foreground disabled:opacity-50'
          aria-label='Refresh Maya work status'
        >
          <RefreshCw className={busy ? 'h-4 w-4 animate-spin' : 'h-4 w-4'} />
        </button>
      </div>
      {snapshot && (
        <>
          <div className='mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4'>
            {[
              ['Working (verified)', confirmed],
              ['Queued', queued],
              ['Stale', stale],
              ['Finished with handoff', finished],
            ].map(([name, count]) => (
              <div key={name} className='rounded-xl border border-border bg-card/40 p-3'>
                <p className='text-[10px] text-muted-foreground'>{name}</p>
                <p className='mt-1 text-xl font-semibold text-foreground'>{count}</p>
              </div>
            ))}
          </div>
          <p className='mt-3 text-xs leading-5 text-muted-foreground'>{snapshot.next_safe_action}</p>
          {snapshot.work_items.length === 0 && (
            <p className='mt-3 rounded-xl border border-dashed border-border p-3 text-xs text-muted-foreground'>
              Maya has no linked worker assignments yet. A portfolio review receipt is not a worker run.
            </p>
          )}
          {snapshot.work_items.slice(0, 5).map(item => (
            <div key={item.work_item_id} className='mt-2 rounded-xl border border-border bg-card/40 p-3'>
              <div className='flex items-center justify-between gap-2'>
                <p className='text-xs font-semibold text-foreground'>{item.title}</p>
                {item.observed_state === 'running_confirmed'
                  ? <CheckCircle2 className='h-4 w-4 shrink-0 text-emerald-300' />
                  : item.requires_reconciliation
                    ? <AlertTriangle className='h-4 w-4 shrink-0 text-amber-300' />
                    : <CircleDot className='h-4 w-4 shrink-0 text-muted-foreground' />}
              </div>
              <p className='mt-1 text-[11px] text-muted-foreground'>
                {item.observed_state.replaceAll('_', ' ')} · {item.project_id}
                {item.runtime ? ` · ${item.runtime}` : ''}
              </p>
              {item.summary_md && (
                <p className='mt-2 text-xs text-muted-foreground'>{item.summary_md}</p>
              )}
              {item.blockers_md && (
                <p className='mt-2 rounded-lg border border-amber-400/20 bg-amber-500/10 p-2 text-xs text-amber-200'>
                  Blocker: {item.blockers_md}
                </p>
              )}
              {item.observed_state === 'blocked' && /browser profile is not signed in/i.test(item.blockers_md ?? '') && (
                <>
                  <button type='button' onClick={() => void openSetup()} disabled={setupBusy}
                    className='mt-2 rounded-xl border border-primary/30 px-3 py-2 text-xs font-semibold text-primary hover:bg-primary/10 disabled:opacity-50'>
                    {setupBusy ? 'Opening profile…' : 'Open dedicated ChatGPT sign-in'}
                  </button>
                  <button type='button' onClick={() => void retryBlockedPilot(item.work_item_id)}
                    disabled={retryingId !== null}
                    className='ml-2 mt-2 rounded-xl border border-border px-3 py-2 text-xs font-semibold text-foreground hover:bg-accent disabled:opacity-50'>
                    {retryingId === item.work_item_id ? 'Retrying…' : 'Retry same assignment'}
                  </button>
                  <p className='mt-2 text-[11px] text-muted-foreground'>
                    Finish sign-in and close the setup browser before retrying. No duplicate task will be created.
                  </p>
                </>
              )}
            </div>
          ))}
          <p className='mt-3 text-[11px] text-muted-foreground'>
            Heartbeats older than {snapshot.heartbeat_stale_seconds}s are not proof of current execution.
          </p>
        </>
      )}
      {retryMessage && (
        <p className='mt-3 rounded-xl border border-border bg-card/50 p-3 text-xs text-muted-foreground'>
          {retryMessage}
        </p>
      )}
      {setupMessage && (
        <p className='mt-3 rounded-xl border border-border bg-card/50 p-3 text-xs text-muted-foreground'>
          {setupMessage}
        </p>
      )}
      {error && (
        <p className='mt-3 rounded-xl border border-amber-500/20 bg-amber-500/10 p-3 text-xs text-amber-200'>
          Work-cycle status unavailable: {error}
        </p>
      )}
    </section>
  );
}
