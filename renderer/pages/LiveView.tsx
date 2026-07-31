// Live View (ADR-0028 Phase 4) — watch your AIs work in real time.
//
// The reference implementation of the one-window standard (AGENTS.md "Frontend UI
// standard"): a fixed-height shell whose panes scroll independently. The page body
// never scrolls — the session rail and the timeline each own their overflow, with
// the shared .scrollbar-thin treatment.
//
// Left rail  = every AI session ever registered (#001…), with its live connection
//              grade + status.
// Main pane  = the selected session's story: what it did (from the persisted
//              activity feed) plus live events as they arrive over the WebSocket,
//              including the AI's own terminal output.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Activity, Loader2, Radio, RefreshCw, Terminal } from 'lucide-react';

import {
  getActivitySessionDetail,
  getActivitySessions,
  type ActivityLevel,
  type ActivityNotification,
  type ActivitySession,
  type ActivitySessionDetail,
} from '@shared/activity-client';
import { useDaemon } from '@shared/daemon-context';
import { formatLocal } from '@shared/format-time';
import { cn } from '@shared/utils';
import { Card } from '../components/ui/card';
import { PageHeader } from '../components/PageHeader';

const LEVEL_DOT: Record<ActivityLevel, string> = {
  green: 'bg-status-launched',
  yellow: 'bg-status-launching',
  red: 'bg-status-error',
  info: 'bg-primary',
};

/** A line in the live timeline — either a persisted notification or a live event. */
interface TimelineEntry {
  id: string;
  at: string;
  kind: string;
  level: ActivityLevel;
  text: string;
  detail?: string;
  live?: boolean;
}

const MAX_LIVE_ENTRIES = 300;

function shortTime(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleTimeString();
}

function relative(iso: string): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return '';
  const secs = Math.max(0, Math.round((Date.now() - then) / 1000));
  if (secs < 60) return 'just now';
  if (secs < 3600) return `${Math.floor(secs / 60)}m ago`;
  if (secs < 86400) return `${Math.floor(secs / 3600)}h ago`;
  return formatLocal(iso, 'short');
}

function notificationToEntry(n: ActivityNotification): TimelineEntry {
  return {
    id: `n:${n.id}`,
    at: n.created_at,
    kind: n.kind,
    level: n.level,
    text: n.title,
    detail: n.body_md || undefined,
  };
}

export function LiveViewPage(): JSX.Element {
  const { subscribeRaw, connState } = useDaemon();
  const [sessions, setSessions] = useState<ActivitySession[] | null>(null);
  const [sessionsError, setSessionsError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<ActivitySessionDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [liveEntries, setLiveEntries] = useState<TimelineEntry[]>([]);
  const timelineRef = useRef<HTMLDivElement | null>(null);

  const refreshSessions = useCallback(async () => {
    try {
      const { sessions: list } = await getActivitySessions();
      setSessions(list);
      setSessionsError(null);
      setSelectedId((current) => current ?? list[0]?.id ?? null);
    } catch (e) {
      setSessionsError((e as Error).message || 'Could not load sessions.');
      setSessions((prev) => prev ?? []);
    }
  }, []);

  useEffect(() => {
    if (connState !== 'open') return;
    void refreshSessions();
  }, [connState, refreshSessions]);

  // Load the selected session's persisted story.
  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      return;
    }
    let cancelled = false;
    setDetailLoading(true);
    setLiveEntries([]);
    getActivitySessionDetail(selectedId)
      .then((d) => {
        if (!cancelled) setDetail(d);
      })
      .catch(() => {
        if (!cancelled) setDetail(null);
      })
      .finally(() => {
        if (!cancelled) setDetailLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedId]);

  // Live stream: append events as they happen (the "watch it work" part).
  useEffect(
    () =>
      subscribeRaw((event) => {
        const name = event.name;
        const payload = (event.payload ?? {}) as Record<string, unknown>;
        let entry: TimelineEntry | null = null;
        const now = new Date().toISOString();

        if (name === 'v1.activity.notification') {
          const n = payload.notification as ActivityNotification | undefined;
          if (n) entry = { ...notificationToEntry(n), live: true };
          void refreshSessions();
        } else if (name === 'v1.pty.session_output') {
          const chunk = String(payload.chunk ?? payload.data ?? '').trim();
          if (chunk) {
            entry = {
              id: `o:${event.id}`,
              at: now,
              kind: 'pty.output',
              level: 'info',
              text: chunk.length > 400 ? `${chunk.slice(0, 400)}…` : chunk,
              live: true,
            };
          }
        } else if (name.startsWith('v1.agent_work_item.') || name.startsWith('v1.agent_run.')) {
          const item = (payload.work_item ?? {}) as Record<string, unknown>;
          const label = String(item.title ?? payload.work_item_id ?? '');
          entry = {
            id: `e:${event.id}`,
            at: now,
            kind: name.replace('v1.', ''),
            level: 'info',
            text: label ? `${name.split('.').pop()}: ${label}` : name.replace('v1.', ''),
            live: true,
          };
        }

        if (entry) {
          setLiveEntries((prev) => [...prev, entry as TimelineEntry].slice(-MAX_LIVE_ENTRIES));
        }
      }),
    [subscribeRaw, refreshSessions]
  );

  const selected = useMemo(
    () => sessions?.find((s) => s.id === selectedId) ?? null,
    [sessions, selectedId]
  );

  const timeline = useMemo<TimelineEntry[]>(() => {
    const persisted = (detail?.notifications ?? []).map(notificationToEntry);
    // Persisted rows arrive newest-first; show the story oldest -> newest, then live.
    return [...persisted.reverse(), ...liveEntries];
  }, [detail, liveEntries]);

  // Follow the stream as new entries land.
  useEffect(() => {
    const el = timelineRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [timeline.length]);

  const tokenTotal = useMemo(() => {
    let total = 0;
    for (const s of detail?.squads ?? []) {
      const usage = s.token_usage as { total_tokens?: number } | undefined;
      total += usage?.total_tokens ?? 0;
    }
    return total;
  }, [detail]);

  return (
    // One-window shell: fixed height, no page scroll — the panes below scroll.
    <div className='flex h-full min-h-0 flex-col gap-4'>
      <PageHeader
        title='Live'
        subtitle='Every AI that connected to Synapse, and what it is doing right now.'
        action={
          <button
            type='button'
            onClick={() => void refreshSessions()}
            className='inline-flex items-center gap-1.5 rounded-md border border-border px-2.5 py-1.5 text-xs transition hover:border-primary'
          >
            <RefreshCw className='h-3.5 w-3.5' aria-hidden='true' /> Refresh
          </button>
        }
      />

      <div className='flex min-h-0 flex-1 flex-col gap-4 lg:flex-row'>
        {/* Session rail — its own scroll container. */}
        <Card className='flex min-h-0 shrink-0 flex-col overflow-hidden p-0 lg:w-72'>
          <div className='shrink-0 border-b border-border px-3 py-2'>
            <p className='text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground'>
              Sessions
            </p>
          </div>
          <div className='scrollbar-thin min-h-0 flex-1 overflow-y-auto'>
            {sessions === null ? (
              <p className='flex items-center gap-2 px-3 py-4 text-xs text-muted-foreground'>
                <Loader2 className='h-3.5 w-3.5 animate-spin' aria-hidden='true' /> Loading sessions…
              </p>
            ) : sessionsError && sessions.length === 0 ? (
              <p role='alert' className='px-3 py-4 text-xs text-destructive'>
                {sessionsError}
              </p>
            ) : sessions.length === 0 ? (
              <div className='px-3 py-6 text-center'>
                <Radio className='mx-auto h-5 w-5 text-muted-foreground' aria-hidden='true' />
                <p className='mt-2 text-xs font-medium'>No AI sessions yet</p>
                <p className='mt-1 text-[11px] text-muted-foreground'>
                  When an AI connects to Synapse it appears here with its own number.
                </p>
              </div>
            ) : (
              <ul className='divide-y divide-border'>
                {sessions.map((s) => (
                  <li key={s.id}>
                    <button
                      type='button'
                      onClick={() => setSelectedId(s.id)}
                      className={cn(
                        'w-full px-3 py-2.5 text-left transition hover:bg-accent/40',
                        s.id === selectedId && 'bg-accent/60'
                      )}
                    >
                      <div className='flex items-center gap-2'>
                        <span
                          className={cn(
                            'h-2 w-2 shrink-0 rounded-full',
                            LEVEL_DOT[s.connection_level] ?? LEVEL_DOT.info,
                            s.status === 'active' && !s.stale && 'animate-pulse'
                          )}
                          aria-hidden='true'
                        />
                        <span className='font-mono text-xs text-muted-foreground'>
                          #{String(s.seq).padStart(3, '0')}
                        </span>
                        <span className='truncate text-sm font-medium'>
                          {s.agent_label || s.runtime_id || 'AI'}
                        </span>
                      </div>
                      <p className='mt-0.5 truncate text-[11px] text-muted-foreground'>
                        {s.status}
                        {s.stale ? ' · stale' : ''} · {relative(s.last_heartbeat_at)}
                      </p>
                      {s.task && (
                        <p className='mt-0.5 truncate text-[11px] text-muted-foreground'>{s.task}</p>
                      )}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </Card>

        {/* Timeline — the other independent scroll container. */}
        <Card className='flex min-h-0 flex-1 flex-col overflow-hidden p-0'>
          {selected && (
            <div className='flex shrink-0 flex-wrap items-center justify-between gap-2 border-b border-border px-4 py-2.5'>
              <div className='min-w-0'>
                <p className='truncate text-sm font-semibold'>
                  Session #{String(selected.seq).padStart(3, '0')} ·{' '}
                  {selected.agent_label || selected.runtime_id}
                </p>
                <p className='truncate text-[11px] text-muted-foreground'>
                  {selected.connection_code} · registered {relative(selected.registered_at)}
                  {selected.project_id ? ` · ${selected.project_id}` : ''}
                </p>
              </div>
              <div className='flex items-center gap-3 text-[11px] text-muted-foreground'>
                {tokenTotal > 0 && (
                  <span className='font-mono' title='Tokens recorded for this session’s squads'>
                    {tokenTotal.toLocaleString()} tokens
                  </span>
                )}
                {liveEntries.length > 0 && (
                  <span className='inline-flex items-center gap-1 text-primary'>
                    <Activity className='h-3.5 w-3.5 animate-pulse' aria-hidden='true' /> live
                  </span>
                )}
              </div>
            </div>
          )}

          <div ref={timelineRef} className='scrollbar-thin min-h-0 flex-1 overflow-y-auto px-4 py-3'>
            {!selected ? (
              <p className='py-10 text-center text-sm text-muted-foreground'>
                Select a session to watch what it is doing.
              </p>
            ) : detailLoading && timeline.length === 0 ? (
              <p className='flex items-center justify-center gap-2 py-10 text-sm text-muted-foreground'>
                <Loader2 className='h-4 w-4 animate-spin' aria-hidden='true' /> Loading this session…
              </p>
            ) : timeline.length === 0 ? (
              <div className='py-10 text-center'>
                <p className='text-sm font-medium'>Nothing recorded yet</p>
                <p className='mt-1 text-xs text-muted-foreground'>
                  Milestones and live output from this AI will stream in here.
                </p>
              </div>
            ) : (
              <ol className='flex flex-col gap-2'>
                {timeline.map((entry) => (
                  <li key={entry.id} className='flex gap-2'>
                    <span className='mt-1 shrink-0 font-mono text-[10px] text-muted-foreground'>
                      {shortTime(entry.at)}
                    </span>
                    <span
                      className={cn('mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full', LEVEL_DOT[entry.level] ?? LEVEL_DOT.info)}
                      aria-hidden='true'
                    />
                    <div className='min-w-0 flex-1'>
                      <p
                        className={cn(
                          'text-sm',
                          entry.kind === 'pty.output' && 'whitespace-pre-wrap break-words font-mono text-xs text-muted-foreground'
                        )}
                      >
                        {entry.kind === 'pty.output' && (
                          <Terminal className='mr-1 inline h-3 w-3' aria-hidden='true' />
                        )}
                        {entry.text}
                      </p>
                      {entry.detail && (
                        <p className='mt-0.5 whitespace-pre-wrap text-xs text-muted-foreground'>
                          {entry.detail}
                        </p>
                      )}
                    </div>
                  </li>
                ))}
              </ol>
            )}
          </div>
        </Card>
      </div>
    </div>
  );
}
