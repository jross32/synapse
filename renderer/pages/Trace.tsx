import { useEffect, useMemo, useState } from 'react';
import {
  Activity,
  AlertTriangle,
  Clock3,
  Gauge,
  RefreshCw,
  Search,
  ShieldCheck,
  Sparkles,
  TerminalSquare,
  TimerReset,
} from 'lucide-react';

import { PageHeader } from '../components/PageHeader';
import {
  fetchTraceAnalysis,
  fetchTraceEvents,
  type TraceAnalysis,
  type TraceEvent,
} from '../lib/trace-client';
import { cn } from '../lib/utils';

const AUTO_REFRESH_MS = 8000;

function statusClass(status: string): string {
  const value = status.toLowerCase();
  if (value === 'success' || value === 'healthy') {
    return 'border-status-launched/30 bg-status-launched/10 text-status-launched';
  }
  if (value === 'error') {
    return 'border-status-error/30 bg-status-error/10 text-status-error';
  }
  if (value === 'warning') {
    return 'border-amber-500/30 bg-amber-500/10 text-amber-500';
  }
  if (value === 'recovery') {
    return 'border-primary/30 bg-primary/10 text-primary';
  }
  return 'border-border bg-secondary text-muted-foreground';
}

function formatWhen(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function formatDuration(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return '—';
  if (value < 1000) return Math.round(value) + ' ms';
  if (value < 60_000) return (value / 1000).toFixed(1) + ' s';
  return (value / 60_000).toFixed(1) + ' min';
}

function EventRow({ event }: { event: TraceEvent }): JSX.Element {
  const [open, setOpen] = useState(false);
  const details = JSON.stringify(event.details ?? {}, null, 2);

  return (
    <article className='rounded-2xl border border-border bg-card p-4 shadow-sm'>
      <button
        type='button'
        onClick={() => setOpen((value) => !value)}
        className='w-full text-left'
      >
        <div className='flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between'>
          <div className='min-w-0'>
            <div className='flex flex-wrap items-center gap-2'>
              <span className={cn(
                'rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide',
                statusClass(event.status)
              )}>
                {event.status}
              </span>
              <span className='rounded-full border border-border bg-secondary px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-muted-foreground'>
                {event.category}
              </span>
              <span className='text-sm font-semibold'>{event.action}</span>
            </div>
            <p className='mt-2 text-sm leading-relaxed text-muted-foreground'>
              {event.summary || 'No summary was recorded.'}
            </p>
          </div>
          <div className='shrink-0 text-left text-xs text-muted-foreground lg:text-right'>
            <div>{formatWhen(event.occurred_at)}</div>
            <div className='mt-1 font-mono'>{event.source}</div>
          </div>
        </div>
        <div className='mt-3 flex flex-wrap gap-x-5 gap-y-2 text-xs text-muted-foreground'>
          <span>Duration: <strong className='font-medium text-foreground'>{formatDuration(event.duration_ms)}</strong></span>
          {event.project_id && <span>Project: <strong className='font-medium text-foreground'>{event.project_id}</strong></span>}
          {event.session_id && <span>Session: <strong className='font-medium text-foreground'>{event.session_id}</strong></span>}
          {event.error_code && <span>Error: <strong className='font-medium text-status-error'>{event.error_code}</strong></span>}
        </div>
      </button>
      {open && (
        <div className='mt-4 border-t border-border pt-4'>
          <div className='mb-2 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground'>
            Privacy-filtered metadata
          </div>
          <pre className='max-h-80 overflow-auto rounded-xl border border-border bg-background p-3 text-[11px] leading-relaxed text-muted-foreground'>
            {details}
          </pre>
        </div>
      )}
    </article>
  );
}

export function TracePage(): JSX.Element {
  const [events, setEvents] = useState<TraceEvent[]>([]);
  const [analysis, setAnalysis] = useState<TraceAnalysis | null>(null);
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState('');
  const [source, setSource] = useState('');
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function refresh(force = false): Promise<void> {
    if (force) setRefreshing(true);
    try {
      const [timeline, nextAnalysis] = await Promise.all([
        fetchTraceEvents({ limit: 250 }),
        fetchTraceAnalysis(24),
      ]);
      setEvents(timeline.items);
      setAnalysis(nextAnalysis);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }

  useEffect(() => {
    void refresh(true);
    const timer = window.setInterval(() => void refresh(false), AUTO_REFRESH_MS);
    return () => window.clearInterval(timer);
  }, []);

  const sources = useMemo(
    () => Array.from(new Set(events.map((event) => event.source))).sort(),
    [events]
  );

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return events.filter((event) => {
      if (status && event.status !== status) return false;
      if (source && event.source !== source) return false;
      if (!q) return true;
      return [
        event.source,
        event.category,
        event.action,
        event.status,
        event.summary,
        event.project_id ?? '',
        event.session_id ?? '',
        event.error_code ?? '',
      ]
        .join(' ')
        .toLowerCase()
        .includes(q);
    });
  }, [events, query, source, status]);

  const totals = analysis?.totals;

  return (
    <div className='space-y-6'>
      <PageHeader
        title='Trace'
        subtitle='Synapse Flight Recorder: what happened, what changed, what failed, and what recovered.'
        helpText='Trace stores observable action receipts, safe metadata, timings, runtime events, and explicit summaries. It never records private hidden chain-of-thought, keylogging, or continuous screenshots.'
        action={
          <button
            type='button'
            onClick={() => void refresh(true)}
            disabled={refreshing}
            className='inline-flex w-full items-center justify-center gap-2 rounded-xl border border-border bg-secondary px-3 py-2 text-sm font-medium transition-colors hover:bg-accent disabled:opacity-50 sm:w-auto'
          >
            <RefreshCw className={cn('h-4 w-4', refreshing && 'animate-spin')} aria-hidden='true' />
            Analyze now
          </button>
        }
      />

      {error && (
        <div className='flex items-start gap-3 rounded-2xl border border-status-error/30 bg-status-error/10 p-4 text-sm text-status-error'>
          <AlertTriangle className='mt-0.5 h-4 w-4 shrink-0' aria-hidden='true' />
          <div>
            <div className='font-semibold'>Trace could not refresh</div>
            <div className='mt-1 opacity-90'>{error}</div>
          </div>
        </div>
      )}

      <section className='grid gap-3 sm:grid-cols-2 xl:grid-cols-4'>
        {[
          ['Events · 24h', totals?.events ?? 0, Activity],
          ['Errors / warnings', totals?.errors_warnings ?? 0, AlertTriangle],
          ['Recoveries', totals?.recoveries ?? 0, TimerReset],
          ['Slow operations', totals?.slow_operations ?? 0, Gauge],
        ].map(([label, value, Icon]) => {
          const SummaryIcon = Icon as typeof Activity;
          return (
            <div key={String(label)} className='rounded-2xl border border-border bg-card p-4'>
              <div className='flex items-center justify-between gap-3'>
                <div>
                  <div className='text-xs font-medium text-muted-foreground'>{String(label)}</div>
                  <div className='mt-1 text-2xl font-semibold tracking-tight'>{Number(value)}</div>
                </div>
                <SummaryIcon className='h-5 w-5 text-muted-foreground' aria-hidden='true' />
              </div>
            </div>
          );
        })}
      </section>

      <section className='space-y-3'>
        <div className='flex items-center gap-2'>
          <Sparkles className='h-4 w-4 text-muted-foreground' aria-hidden='true' />
          <h2 className='text-base font-semibold'>Trace analysis</h2>
        </div>
        {analysis?.recommendations.length ? (
          <div className='grid gap-3 lg:grid-cols-2'>
            {analysis.recommendations.map((recommendation, index) => (
              <div key={recommendation.kind + index} className='rounded-2xl border border-border bg-card p-4'>
                <div className='flex items-center gap-2'>
                  <span className={cn(
                    'rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide',
                    recommendation.priority === 'high'
                      ? 'border-status-error/30 bg-status-error/10 text-status-error'
                      : 'border-amber-500/30 bg-amber-500/10 text-amber-500'
                  )}>
                    {recommendation.priority}
                  </span>
                  <span className='text-sm font-semibold'>{recommendation.kind}</span>
                </div>
                <p className='mt-2 text-sm leading-relaxed text-muted-foreground'>
                  {recommendation.message}
                </p>
              </div>
            ))}
          </div>
        ) : (
          <div className='flex items-start gap-3 rounded-2xl border border-status-launched/25 bg-status-launched/5 p-4'>
            <ShieldCheck className='mt-0.5 h-4 w-4 shrink-0 text-status-launched' aria-hidden='true' />
            <div>
              <div className='text-sm font-semibold'>No repeated failure pattern detected</div>
              <p className='mt-1 text-sm text-muted-foreground'>
                Trace will surface repeated errors, recovery churn, and slow operations here as evidence accumulates.
              </p>
            </div>
          </div>
        )}
      </section>

      <section className='space-y-4'>
        <div className='flex flex-col gap-3 xl:flex-row xl:items-end xl:justify-between'>
          <div>
            <h2 className='text-base font-semibold'>Timeline</h2>
            <p className='mt-1 text-sm text-muted-foreground'>
              Auto-refreshes every 8 seconds and imports recent monitor, supervisor, and watchdog events.
            </p>
          </div>
          <div className='flex flex-col gap-2 sm:flex-row'>
            <label className='relative block'>
              <Search className='pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground' aria-hidden='true' />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder='Search timeline…'
                className='h-10 w-full rounded-xl border border-border bg-background pl-9 pr-3 text-sm outline-none transition-shadow focus:ring-2 focus:ring-ring sm:w-64'
              />
            </label>
            <select
              value={status}
              onChange={(event) => setStatus(event.target.value)}
              className='h-10 rounded-xl border border-border bg-background px-3 text-sm'
              aria-label='Filter by status'
            >
              <option value=''>All statuses</option>
              <option value='success'>Success</option>
              <option value='error'>Error</option>
              <option value='warning'>Warning</option>
              <option value='recovery'>Recovery</option>
              <option value='info'>Info</option>
            </select>
            <select
              value={source}
              onChange={(event) => setSource(event.target.value)}
              className='h-10 rounded-xl border border-border bg-background px-3 text-sm'
              aria-label='Filter by source'
            >
              <option value=''>All sources</option>
              {sources.map((item) => (
                <option key={item} value={item}>{item}</option>
              ))}
            </select>
          </div>
        </div>

        {loading ? (
          <div className='rounded-2xl border border-border bg-card p-5 text-sm text-muted-foreground'>
            Building the Flight Recorder timeline…
          </div>
        ) : filtered.length === 0 ? (
          <div className='rounded-2xl border border-border bg-card p-5 text-sm text-muted-foreground'>
            No trace events match this filter yet.
          </div>
        ) : (
          <div className='space-y-3'>
            {filtered.map((event) => <EventRow key={event.id} event={event} />)}
          </div>
        )}
      </section>

      <section className='rounded-2xl border border-dashed border-border bg-card/50 p-4'>
        <div className='flex items-start gap-3'>
          <TerminalSquare className='mt-0.5 h-4 w-4 shrink-0 text-muted-foreground' aria-hidden='true' />
          <div className='text-sm text-muted-foreground'>
            <span className='font-medium text-foreground'>Privacy boundary:</span> Trace records observable actions,
            outcomes, safe arguments, timings, and runtime events. Secret-like fields are automatically redacted,
            file-write bodies are omitted, and hidden reasoning is never captured.
          </div>
        </div>
      </section>
    </div>
  );
}
