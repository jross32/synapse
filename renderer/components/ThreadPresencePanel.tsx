import { useEffect, useMemo, useState } from 'react';
import { Activity, AlertTriangle, Clock3, Radio, Users, X } from 'lucide-react';

import {
  getThreadPresenceOverview,
  type ThreadDisplayStatus,
  type ThreadPresenceOverview,
} from '@shared/thread-presence-client';
import { cn } from '@shared/utils';
import { Card } from './ui/card';
import { Modal } from './ui/modal';

const DOT: Record<ThreadDisplayStatus, string> = {
  active: 'bg-status-launched',
  idle: 'bg-muted-foreground/50',
  error: 'bg-status-error',
  stale: 'bg-status-launching',
  gone: 'bg-muted-foreground/30',
  archived: 'bg-muted-foreground/20',
};

function duration(seconds: number): string {
  const rounded = Math.max(0, Math.round(seconds || 0));
  const days = Math.floor(rounded / 86400);
  const hours = Math.floor((rounded % 86400) / 3600);
  const minutes = Math.floor((rounded % 3600) / 60);
  const secs = rounded % 60;
  if (days) return `${days}d ${hours}h ${minutes}m`;
  if (hours) return `${hours}h ${minutes}m`;
  if (minutes) return `${minutes}m ${secs}s`;
  return `${secs}s`;
}

export function ThreadPresencePanel(): JSX.Element {
  const [overview, setOverview] = useState<ThreadPresenceOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [timeOverviewOpen, setTimeOverviewOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const next = await getThreadPresenceOverview();
        if (!cancelled) {
          setOverview(next);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) setError((err as Error).message || 'Could not load thread presence.');
      }
    };
    void load();
    const timer = window.setInterval(() => void load(), 5000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  const errors = useMemo(
    () => (overview?.counts.error ?? 0)
      + (overview?.unassigned_browser_threads.filter((item) => item.status === 'error').length ?? 0),
    [overview]
  );

  if (!overview && !error) {
    return <div className='h-20 animate-pulse rounded-lg border border-border bg-muted/10' />;
  }

  return (
    <>
      <Card className='shrink-0 overflow-hidden p-0'>
        <div className='flex flex-wrap items-center justify-between gap-3 border-b border-border px-3 py-2'>
          <div>
            <p className='flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground'>
              <Radio className='h-3.5 w-3.5 text-primary' aria-hidden='true' /> AI threads
            </p>
            <p className='mt-0.5 text-xs text-muted-foreground'>
              Real conversation presence grouped by the request they are working on.
            </p>
          </div>

          {overview && (
            <div className='flex flex-wrap gap-1.5 text-[10px]'>
              <span className='rounded-full border border-status-launched/40 bg-status-launched/10 px-2 py-1 text-status-launched'>
                {overview.counts.in_progress} working
              </span>
              <span className='rounded-full border border-border bg-muted/30 px-2 py-1 text-muted-foreground'>
                {overview.counts.idle} idle
              </span>
              {overview.counts.stale > 0 && (
                <span className='rounded-full border border-status-launching/40 bg-status-launching/10 px-2 py-1 text-status-launching'>
                  {overview.counts.stale} stale
                </span>
              )}
              {errors > 0 && (
                <span className='rounded-full border border-status-error/40 bg-status-error/10 px-2 py-1 text-status-error'>
                  {errors} errors
                </span>
              )}
              <button
                type='button'
                onClick={() => setTimeOverviewOpen(true)}
                className='rounded-full border border-primary/30 bg-primary/5 px-2 py-1 text-primary transition hover:border-primary hover:bg-primary/10'
                title='Open per-project, per-request, and per-thread time breakdown'
              >
                {duration(overview.total_work_seconds)} tracked work · view
              </button>
            </div>
          )}
        </div>

        {error && !overview ? (
          <p role='alert' className='px-3 py-3 text-xs text-destructive'>{error}</p>
        ) : overview ? (
          <div className='scrollbar-thin max-h-56 overflow-y-auto p-2'>
            {overview.groups.length === 0 && overview.unassigned_browser_threads.length === 0 ? (
              <div className='px-2 py-4 text-center text-xs text-muted-foreground'>
                Threads appear here as ChatGPT/browser workers connect to Synapse.
              </div>
            ) : (
              <div className='space-y-2'>
                {overview.groups.map((group) => (
                  <details
                    key={group.id}
                    className='group rounded-md border border-border bg-muted/10'
                    open={group.active_count > 0}
                  >
                    <summary className='flex cursor-pointer list-none items-center justify-between gap-3 px-3 py-2'>
                      <div className='min-w-0'>
                        <div className='flex items-center gap-2'>
                          <Users className='h-3.5 w-3.5 shrink-0 text-primary' aria-hidden='true' />
                          <span className='truncate text-xs font-medium'>{group.name}</span>
                          <span className='shrink-0 text-[10px] text-muted-foreground'>{group.project_id}</span>
                        </div>
                        {group.description && (
                          <p className='mt-0.5 line-clamp-1 text-[10px] text-muted-foreground'>
                            {group.description}
                          </p>
                        )}
                      </div>
                      <div className='flex shrink-0 items-center gap-2 text-[10px] text-muted-foreground'>
                        {group.active_count > 0 && (
                          <span className='text-status-launched'>{group.active_count} working</span>
                        )}
                        <span>{group.thread_count} thread{group.thread_count === 1 ? '' : 's'}</span>
                        <span className='font-mono text-primary'>{duration(group.total_work_seconds)}</span>
                      </div>
                    </summary>
                    <div className='border-t border-border/70'>
                      {group.threads.map((thread) => (
                        <div
                          key={thread.id}
                          className='flex items-start gap-2 border-b border-border/50 px-3 py-2 last:border-b-0'
                        >
                          <span
                            className={cn(
                              'mt-1 h-2 w-2 shrink-0 rounded-full',
                              DOT[thread.display_status],
                              thread.display_status === 'active' && 'animate-pulse'
                            )}
                          />
                          <div className='min-w-0 flex-1'>
                            <div className='flex flex-wrap items-center gap-x-2 gap-y-0.5'>
                              <span className='truncate text-xs font-medium'>{thread.title || thread.runtime_id}</span>
                              <span className='text-[9px] uppercase tracking-wide text-muted-foreground'>
                                {thread.display_status}
                              </span>
                              <span className='font-mono text-[10px] text-primary'>
                                {duration(thread.total_work_seconds)}
                              </span>
                              <span className='text-[10px] text-muted-foreground'>
                                {thread.turn_count} turn{thread.turn_count === 1 ? '' : 's'}
                              </span>
                            </div>
                            {(thread.current_task || thread.description) && (
                              <p className='mt-0.5 line-clamp-1 text-[10px] text-muted-foreground'>
                                {thread.current_task || thread.description}
                              </p>
                            )}
                            {thread.last_error && (
                              <p className='mt-0.5 line-clamp-1 text-[10px] text-status-error'>
                                {thread.last_error}
                              </p>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  </details>
                ))}

                {overview.unassigned_browser_threads.length > 0 && (
                  <details
                    className='rounded-md border border-dashed border-border bg-muted/5'
                    open={overview.counts.browser_unassigned_active > 0}
                  >
                    <summary className='flex cursor-pointer list-none items-center justify-between gap-2 px-3 py-2 text-xs'>
                      <span className='flex items-center gap-2'>
                        <Activity className='h-3.5 w-3.5 text-status-launching' aria-hidden='true' />
                        Unassigned ChatGPT tabs
                      </span>
                      <span className='text-[10px] text-muted-foreground'>
                        {overview.counts.browser_unassigned_active} working · {overview.counts.browser_unassigned} seen
                      </span>
                    </summary>
                    <div className='border-t border-border/70'>
                      {overview.unassigned_browser_threads.map((thread) => (
                        <div
                          key={thread.external_thread_key}
                          className='flex items-start gap-2 border-b border-border/50 px-3 py-2 last:border-b-0'
                        >
                          <span
                            className={cn(
                              'mt-1 h-2 w-2 shrink-0 rounded-full',
                              DOT[thread.status],
                              thread.status === 'active' && 'animate-pulse'
                            )}
                          />
                          <div className='min-w-0 flex-1'>
                            <p className='truncate text-xs'>{thread.title || thread.external_thread_key}</p>
                            <p className='mt-0.5 line-clamp-1 text-[10px] text-muted-foreground'>
                              {thread.current_task || 'Waiting for this thread to identify its Synapse project/request.'}
                            </p>
                          </div>
                          {thread.status === 'error' && (
                            <AlertTriangle className='h-3.5 w-3.5 text-status-error' aria-hidden='true' />
                          )}
                        </div>
                      ))}
                    </div>
                  </details>
                )}
              </div>
            )}
          </div>
        ) : null}

        <div className='flex items-center gap-1.5 border-t border-border/60 px-3 py-1.5 text-[9px] text-muted-foreground'>
          <Clock3 className='h-3 w-3' aria-hidden='true' />
          Per-thread time is the sum of completed response/work turns; UI-reported time is preferred when available.
        </div>
      </Card>

      <Modal
        open={timeOverviewOpen}
        onClose={() => setTimeOverviewOpen(false)}
        labelledBy='thread-time-overview-title'
        className='max-w-3xl p-0'
      >
        <div className='flex items-start justify-between gap-3 border-b border-border px-5 py-4'>
          <div>
            <h2 id='thread-time-overview-title' className='text-base font-semibold'>AI work-time overview</h2>
            <p className='mt-1 text-xs text-muted-foreground'>
              Every tracked request and the ChatGPT/AI threads that contributed to it.
            </p>
          </div>
          <button
            type='button'
            onClick={() => setTimeOverviewOpen(false)}
            aria-label='Close work-time overview'
            className='rounded-md p-1.5 text-muted-foreground transition hover:bg-accent hover:text-foreground'
          >
            <X className='h-4 w-4' aria-hidden='true' />
          </button>
        </div>

        {overview && (
          <>
            <div className='grid gap-2 border-b border-border bg-muted/10 px-5 py-3 sm:grid-cols-4'>
              <div>
                <p className='text-[10px] uppercase tracking-wide text-muted-foreground'>Total work</p>
                <p className='mt-0.5 font-mono text-sm font-semibold text-primary'>{duration(overview.total_work_seconds)}</p>
              </div>
              <div>
                <p className='text-[10px] uppercase tracking-wide text-muted-foreground'>Requests</p>
                <p className='mt-0.5 text-sm font-semibold'>{overview.counts.groups}</p>
              </div>
              <div>
                <p className='text-[10px] uppercase tracking-wide text-muted-foreground'>Tracked threads</p>
                <p className='mt-0.5 text-sm font-semibold'>{overview.counts.threads}</p>
              </div>
              <div>
                <p className='text-[10px] uppercase tracking-wide text-muted-foreground'>Working now</p>
                <p className='mt-0.5 text-sm font-semibold text-status-launched'>{overview.counts.in_progress}</p>
              </div>
            </div>

            <div className='scrollbar-thin max-h-[65vh] space-y-3 overflow-y-auto p-4'>
              {overview.groups.length === 0 ? (
                <p className='py-8 text-center text-sm text-muted-foreground'>No timed thread work has been recorded yet.</p>
              ) : (
                overview.groups.map((group) => (
                  <section key={group.id} className='overflow-hidden rounded-lg border border-border'>
                    <div className='flex flex-wrap items-start justify-between gap-3 bg-muted/20 px-4 py-3'>
                      <div className='min-w-0'>
                        <div className='flex flex-wrap items-center gap-2'>
                          <span className='text-sm font-semibold'>{group.name}</span>
                          <span className='rounded-full border border-border px-2 py-0.5 text-[10px] text-muted-foreground'>
                            {group.project_id}
                          </span>
                        </div>
                        {group.description && (
                          <p className='mt-1 text-xs text-muted-foreground'>{group.description}</p>
                        )}
                      </div>
                      <div className='text-right'>
                        <p className='font-mono text-sm font-semibold text-primary'>{duration(group.total_work_seconds)}</p>
                        <p className='text-[10px] text-muted-foreground'>
                          {group.thread_count} thread{group.thread_count === 1 ? '' : 's'}
                        </p>
                      </div>
                    </div>

                    <div className='divide-y divide-border'>
                      {group.threads.map((thread, index) => (
                        <div key={thread.id} className='grid gap-2 px-4 py-3 sm:grid-cols-[minmax(0,1fr)_auto]'>
                          <div className='min-w-0'>
                            <div className='flex flex-wrap items-center gap-2'>
                              <span className='font-mono text-[10px] text-muted-foreground'>#{index + 1}</span>
                              <span
                                className={cn(
                                  'h-2 w-2 rounded-full',
                                  DOT[thread.display_status],
                                  thread.display_status === 'active' && 'animate-pulse'
                                )}
                              />
                              <span className='truncate text-xs font-medium'>{thread.title || thread.runtime_id}</span>
                              <span className='text-[9px] uppercase tracking-wide text-muted-foreground'>
                                {thread.display_status}
                              </span>
                            </div>
                            <p className='mt-1 line-clamp-2 text-[11px] text-muted-foreground'>
                              {thread.current_task || thread.description || 'No current task summary.'}
                            </p>
                          </div>
                          <div className='flex items-center gap-3 text-right sm:block'>
                            <p className='font-mono text-xs font-semibold text-primary'>{duration(thread.total_work_seconds)}</p>
                            <p className='text-[10px] text-muted-foreground'>
                              {thread.turn_count} turn{thread.turn_count === 1 ? '' : 's'}
                            </p>
                          </div>
                        </div>
                      ))}
                    </div>
                  </section>
                ))
              )}
            </div>
          </>
        )}
      </Modal>
    </>
  );
}
