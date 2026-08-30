import { useEffect, useMemo, useState } from 'react';
import {
  Activity,
  AlertTriangle,
  Bot,
  ChevronDown,
  ChevronRight,
  Clock3,
  Network,
  RefreshCw,
  Search,
  ShieldCheck,
  ShieldQuestion,
  TerminalSquare,
  Workflow,
} from 'lucide-react';

import { PageHeader } from '../components/PageHeader';
import {
  fetchWatchdogLog,
  fetchWatchdogs,
  type WatchdogHealth,
  type WatchdogItem,
  type WatchdogLog,
  type WatchdogSnapshot,
} from '../lib/watchdogs-client';
import { cn } from '../lib/utils';

const AUTO_REFRESH_MS = 5000;

function healthLabel(health: WatchdogHealth): string {
  if (health === 'healthy') return 'Healthy';
  if (health === 'armed') return 'Armed';
  if (health === 'warning') return 'Warning';
  return 'Stopped';
}

function healthClass(health: WatchdogHealth): string {
  if (health === 'healthy') return 'border-status-launched/30 bg-status-launched/10 text-status-launched';
  if (health === 'armed') return 'border-primary/30 bg-primary/10 text-primary';
  if (health === 'warning') return 'border-amber-500/30 bg-amber-500/10 text-amber-500';
  return 'border-status-error/30 bg-status-error/10 text-status-error';
}

function formatUptime(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return '—';
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  if (days > 0) return `${days}d ${hours}h`;
  if (hours > 0) return `${hours}h ${minutes}m`;
  return `${Math.max(0, minutes)}m`;
}

function groupLabel(group: string): string {
  if (group === 'synapse') return 'Synapse';
  if (group === 'stock-hunter') return 'Stock Hunter';
  if (group === 'web-scraper') return 'Web Scraper';
  return group
    .split('-')
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
}

function KindIcon({ kind }: { kind: string }): JSX.Element {
  if (kind === 'watchdog') return <ShieldCheck className='h-4 w-4' aria-hidden='true' />;
  if (kind === 'supervisor') return <Bot className='h-4 w-4' aria-hidden='true' />;
  if (kind === 'monitor') return <Activity className='h-4 w-4' aria-hidden='true' />;
  if (kind === 'job') return <Clock3 className='h-4 w-4' aria-hidden='true' />;
  if (kind === 'service') return <Network className='h-4 w-4' aria-hidden='true' />;
  return <ShieldQuestion className='h-4 w-4' aria-hidden='true' />;
}

function ChainNode({
  item,
  byId,
  visited,
}: {
  item: WatchdogItem;
  byId: Map<string, WatchdogItem>;
  visited: Set<string>;
}): JSX.Element {
  const nextVisited = new Set(visited);
  nextVisited.add(item.id);
  const children = item.protects
    .filter((id) => !nextVisited.has(id))
    .map((id) => byId.get(id))
    .filter((entry): entry is WatchdogItem => Boolean(entry));

  return (
    <div className='min-w-0'>
      <div className='flex min-w-0 items-center gap-2'>
        <span
          className={cn(
            'inline-flex shrink-0 items-center gap-1 rounded-full border px-2 py-1 text-[11px] font-medium',
            healthClass(item.health)
          )}
        >
          <KindIcon kind={item.kind} />
          {item.name}
        </span>
        {children.length > 0 && (
          <ChevronRight className='h-4 w-4 shrink-0 text-muted-foreground' aria-hidden='true' />
        )}
      </div>
      {children.length > 0 && (
        <div className='ml-5 mt-2 space-y-2 border-l border-border pl-4'>
          {children.map((child) => (
            <ChainNode key={child.id} item={child} byId={byId} visited={nextVisited} />
          ))}
        </div>
      )}
    </div>
  );
}

function ProtectionChain({ items }: { items: WatchdogItem[] }): JSX.Element {
  const byId = useMemo(() => new Map(items.map((item) => [item.id, item])), [items]);
  const roots = useMemo(() => {
    const childIds = new Set(items.flatMap((item) => item.protects));
    return items.filter((item) => item.protects.length > 0 && !childIds.has(item.id));
  }, [items]);

  if (roots.length === 0) {
    return <p className='text-sm text-muted-foreground'>No protection links are registered yet.</p>;
  }

  return (
    <div className='grid gap-4 lg:grid-cols-2'>
      {roots.map((root) => (
        <div key={root.id} className='rounded-2xl border border-border bg-card p-4'>
          <ChainNode item={root} byId={byId} visited={new Set()} />
        </div>
      ))}
    </div>
  );
}

function LogPanel({ item }: { item: WatchdogItem }): JSX.Element {
  const [open, setOpen] = useState(false);
  const [log, setLog] = useState<WatchdogLog | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load(): Promise<void> {
    if (!item.log_available) return;
    setLoading(true);
    setError(null);
    try {
      setLog(await fetchWatchdogLog(item.id, 160));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  function toggle(): void {
    const next = !open;
    setOpen(next);
    if (next && !log && !loading) void load();
  }

  if (!item.log_available) {
    return (
      <div className='mt-3 text-xs text-muted-foreground'>
        No log file is registered for this service yet.
      </div>
    );
  }

  return (
    <div className='mt-3 border-t border-border pt-3'>
      <div className='flex flex-wrap items-center gap-2'>
        <button
          type='button'
          onClick={toggle}
          className='inline-flex items-center gap-1.5 rounded-lg border border-border bg-secondary px-2.5 py-1.5 text-xs font-medium transition-colors hover:bg-accent'
        >
          {open ? (
            <ChevronDown className='h-3.5 w-3.5' aria-hidden='true' />
          ) : (
            <ChevronRight className='h-3.5 w-3.5' aria-hidden='true' />
          )}
          <TerminalSquare className='h-3.5 w-3.5' aria-hidden='true' />
          View live output
        </button>
        {open && (
          <button
            type='button'
            onClick={() => void load()}
            disabled={loading}
            className='rounded-lg px-2 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground disabled:opacity-50'
          >
            Refresh
          </button>
        )}
      </div>
      {open && (
        <div className='mt-3'>
          {error && (
            <div className='rounded-xl border border-status-error/30 bg-status-error/10 p-3 text-xs text-status-error'>
              {error}
            </div>
          )}
          {loading && !log ? (
            <div className='rounded-xl border border-border bg-background p-4 text-xs text-muted-foreground'>
              Loading output…
            </div>
          ) : (
            <pre className='max-h-72 overflow-auto rounded-xl border border-border bg-background p-3 text-[11px] leading-relaxed text-muted-foreground'>
              {(log?.lines ?? []).length > 0
                ? (log?.lines ?? []).join('\n')
                : 'The log exists but has no lines yet.'}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}

function WatchdogCard({ item }: { item: WatchdogItem }): JSX.Element {
  const pids = item.processes.map((process) => process.pid);
  const uptime = item.processes.length > 0 ? Math.max(...item.processes.map((p) => p.uptime_seconds)) : null;

  return (
    <article className='rounded-2xl border border-border bg-card p-4 shadow-sm'>
      <div className='flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between'>
        <div className='min-w-0'>
          <div className='flex flex-wrap items-center gap-2'>
            <span className='inline-flex items-center gap-1.5 text-sm font-semibold'>
              <KindIcon kind={item.kind} />
              {item.name}
            </span>
            <span className='rounded-full border border-border bg-secondary px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-muted-foreground'>
              {item.kind}
            </span>
            <span
              className={cn(
                'rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide',
                healthClass(item.health)
              )}
            >
              {healthLabel(item.health)}
            </span>
          </div>
          <p className='mt-2 text-sm leading-relaxed text-muted-foreground'>{item.description}</p>
        </div>
        <div className='shrink-0 text-left text-xs text-muted-foreground sm:text-right'>
          <div>{groupLabel(item.group)}</div>
          <div className='mt-1 font-mono'>
            {pids.length > 0 ? `PID ${pids.join(', ')}` : item.task ? item.task.state ?? 'Scheduled' : 'No process'}
          </div>
        </div>
      </div>

      <div className='mt-4 grid gap-2 sm:grid-cols-2 xl:grid-cols-4'>
        <div className='rounded-xl border border-border bg-background/60 p-3'>
          <div className='text-[10px] font-semibold uppercase tracking-wide text-muted-foreground'>Runtime</div>
          <div className='mt-1 text-sm font-medium'>
            {uptime !== null ? `Up ${formatUptime(uptime)}` : item.health === 'armed' ? 'Scheduled / idle' : 'Not running'}
          </div>
        </div>
        <div className='rounded-xl border border-border bg-background/60 p-3'>
          <div className='text-[10px] font-semibold uppercase tracking-wide text-muted-foreground'>Protection</div>
          <div className='mt-1 text-sm font-medium'>
            {item.protects.length > 0
              ? `Protects ${item.protects.length}`
              : item.protected_by.length > 0
                ? `Protected by ${item.protected_by.length}`
                : 'No protection link'}
          </div>
        </div>
        <div className='rounded-xl border border-border bg-background/60 p-3'>
          <div className='text-[10px] font-semibold uppercase tracking-wide text-muted-foreground'>Schedule</div>
          <div className='mt-1 truncate text-sm font-medium' title={item.task?.task_name ?? undefined}>
            {item.task ? `${item.task.task_name} · ${item.task.state ?? 'Unknown'}` : 'Continuous / direct'}
          </div>
        </div>
        <div className='rounded-xl border border-border bg-background/60 p-3'>
          <div className='text-[10px] font-semibold uppercase tracking-wide text-muted-foreground'>Desktop</div>
          <div className={cn('mt-1 text-sm font-medium', item.console_risk && 'text-amber-500')}>
            {item.console_risk ? 'Console can surface' : 'Background-safe'}
          </div>
        </div>
      </div>

      {item.latest_log_line && (
        <div className='mt-3 overflow-hidden rounded-xl border border-border bg-background/60 px-3 py-2'>
          <div className='mb-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground'>Latest log</div>
          <div className='truncate font-mono text-[11px] text-muted-foreground' title={item.latest_log_line}>
            {item.latest_log_line}
          </div>
        </div>
      )}

      <LogPanel item={item} />
    </article>
  );
}

export function WatchdogsPage(): JSX.Element {
  const [snapshot, setSnapshot] = useState<WatchdogSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [onlyIssues, setOnlyIssues] = useState(false);

  async function refresh(force = false): Promise<void> {
    if (force) setRefreshing(true);
    try {
      const next = await fetchWatchdogs(force);
      setSnapshot(next);
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

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (snapshot?.items ?? []).filter((item) => {
      if (onlyIssues && (item.health === 'healthy' || item.health === 'armed')) return false;
      if (!q) return true;
      return [
        item.name,
        item.description,
        item.kind,
        item.group,
        ...item.tags,
        ...item.protects,
        ...item.protected_by,
      ]
        .join(' ')
        .toLowerCase()
        .includes(q);
    });
  }, [onlyIssues, query, snapshot]);

  const groups = useMemo(() => {
    const map = new Map<string, WatchdogItem[]>();
    for (const item of filtered) {
      const group = map.get(item.group) ?? [];
      group.push(item);
      map.set(item.group, group);
    }
    return [...map.entries()];
  }, [filtered]);

  const counts = snapshot?.counts;

  return (
    <div className='space-y-6'>
      <PageHeader
        title='Watchdogs'
        subtitle='One place to see the whole protection chain, background services, schedules, and live output.'
        helpText='Supervisors watch services. Supervisor watchdogs watch supervisors. Periodic watchdogs can be armed without staying resident. This page is built to grow as more watchdogs are added.'
        action={
          <button
            type='button'
            onClick={() => void refresh(true)}
            disabled={refreshing}
            className='inline-flex w-full items-center justify-center gap-2 rounded-xl border border-border bg-secondary px-3 py-2 text-sm font-medium transition-colors hover:bg-accent disabled:opacity-50 sm:w-auto'
          >
            <RefreshCw className={cn('h-4 w-4', refreshing && 'animate-spin')} aria-hidden='true' />
            Refresh now
          </button>
        }
      />

      {error && (
        <div className='flex items-start gap-3 rounded-2xl border border-status-error/30 bg-status-error/10 p-4 text-sm text-status-error'>
          <AlertTriangle className='mt-0.5 h-4 w-4 shrink-0' aria-hidden='true' />
          <div>
            <div className='font-semibold'>Watchdog status could not refresh</div>
            <div className='mt-1 opacity-90'>{error}</div>
          </div>
        </div>
      )}

      <section className='grid gap-3 sm:grid-cols-2 xl:grid-cols-5'>
        {[
          ['Total', counts?.total ?? 0, Workflow],
          ['Healthy', counts?.healthy ?? 0, ShieldCheck],
          ['Armed', counts?.armed ?? 0, Clock3],
          ['Needs attention', (counts?.warning ?? 0) + (counts?.stopped ?? 0), AlertTriangle],
          ['Console risk', counts?.console_risk ?? 0, TerminalSquare],
        ].map(([label, value, Icon]) => {
          const SummaryIcon = Icon as typeof Workflow;
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
        <div>
          <h2 className='text-base font-semibold'>Protection chain</h2>
          <p className='mt-1 text-sm text-muted-foreground'>
            Follow each recovery layer down to the service it protects.
          </p>
        </div>
        {snapshot ? (
          <ProtectionChain items={snapshot.items} />
        ) : (
          <div className='rounded-2xl border border-border bg-card p-5 text-sm text-muted-foreground'>
            Loading protection chain…
          </div>
        )}
      </section>

      <section className='space-y-4'>
        <div className='flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between'>
          <div>
            <h2 className='text-base font-semibold'>All watchdogs & background services</h2>
            <p className='mt-1 text-sm text-muted-foreground'>
              Auto-refreshes every 5 seconds. Expand any item to see its log without opening a terminal.
            </p>
          </div>
          <div className='flex flex-col gap-2 sm:flex-row sm:items-center'>
            <label className='relative block'>
              <Search className='pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground' aria-hidden='true' />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder='Search watchdogs…'
                className='h-10 w-full rounded-xl border border-border bg-background pl-9 pr-3 text-sm outline-none transition-shadow focus:ring-2 focus:ring-ring sm:w-64'
              />
            </label>
            <button
              type='button'
              onClick={() => setOnlyIssues((value) => !value)}
              className={cn(
                'h-10 rounded-xl border px-3 text-sm font-medium transition-colors',
                onlyIssues
                  ? 'border-primary/35 bg-accent text-foreground'
                  : 'border-border bg-secondary text-muted-foreground hover:text-foreground'
              )}
            >
              {onlyIssues ? 'Showing issues' : 'Only issues'}
            </button>
          </div>
        </div>

        {loading && !snapshot ? (
          <div className='rounded-2xl border border-border bg-card p-5 text-sm text-muted-foreground'>
            Discovering watchdogs and services…
          </div>
        ) : groups.length === 0 ? (
          <div className='rounded-2xl border border-border bg-card p-5 text-sm text-muted-foreground'>
            No watchdogs match this filter.
          </div>
        ) : (
          <div className='space-y-6'>
            {groups.map(([group, items]) => (
              <div key={group} className='space-y-3'>
                <div className='flex items-center gap-2'>
                  <h3 className='text-sm font-semibold'>{groupLabel(group)}</h3>
                  <span className='rounded-full bg-secondary px-2 py-0.5 text-[10px] font-medium text-muted-foreground'>
                    {items.length}
                  </span>
                </div>
                <div className='grid gap-3'>
                  {items.map((item) => (
                    <WatchdogCard key={item.id} item={item} />
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className='rounded-2xl border border-dashed border-border bg-card/50 p-4 text-sm text-muted-foreground'>
        <div className='flex items-start gap-3'>
          <Workflow className='mt-0.5 h-4 w-4 shrink-0' aria-hidden='true' />
          <div>
            <span className='font-medium text-foreground'>Built to scale:</span> future watchdogs can be
            registered in the backend inventory and they will automatically appear here with the same status,
            protection, schedule, and log UI.
          </div>
        </div>
      </section>
    </div>
  );
}
