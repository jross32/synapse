// Live View (ADR-0033) — a truthful operator journal for every connected AI.
// Deep View is the default and shows deliberate reasoning summaries, decisions,
// evidence, tools, MCP receipts, squads, and correlated terminal output. It never
// claims to expose private model chain-of-thought or secrets.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Activity,
  ArrowLeft,
  Bot,
  BrainCircuit,
  CheckCircle2,
  ChevronRight,
  CircleAlert,
  Clock3,
  Cpu,
  Eye,
  Gauge,
  Globe2,
  Lightbulb,
  ListChecks,
  Loader2,
  MonitorPlay,
  Network,
  Pencil,
  Plus,
  Radio,
  RefreshCw,
  Save,
  Sparkles,
  Terminal,
  Trash2,
  Users,
  Wrench,
  X,
} from 'lucide-react';

import {
  createActivityGoal,
  deleteActivityGoal,
  getActivitySessionDetail,
  getActivitySessions,
  updateActivityGoal,
  type ActivityGoal,
  type ActivityAuthority,
  type ActivityJournalCategory,
  type ActivityJournalEvent,
  type ActivityJournalStatus,
  type ActivityLevel,
  type ActivityNotification,
  type ActivitySession,
  type ActivitySessionDetail,
} from '@shared/activity-client';
import { useDaemon } from '@shared/daemon-context';
import { formatLocal } from '@shared/format-time';
import { cn } from '@shared/utils';
import { AppPreview, previewUrl } from '../components/AppPreview';
import { renderInlineBold } from '../components/InlineBold';
import { PageHeader } from '../components/PageHeader';
import { ThreadPresencePanel } from '../components/ThreadPresencePanel';
import { Button } from '../components/ui/button';
import { Card } from '../components/ui/card';
import { Modal } from '../components/ui/modal';

const LEVEL_DOT: Record<ActivityLevel, string> = {
  green: 'bg-status-launched',
  yellow: 'bg-status-launching',
  red: 'bg-status-error',
  info: 'bg-primary',
};

function sessionIndicatorLevel(session: ActivitySession): ActivityLevel {
  if (session.connection_level === 'red') return 'red';
  if (session.stale || session.status === 'gone' || session.status === 'idle') return 'info';
  if (session.connection_level === 'yellow' || session.status === 'blocked' || session.status === 'holding') return 'yellow';
  if (session.status === 'active') return 'green';
  return session.connection_level;
}

const STATUS_STYLE: Record<ActivityJournalStatus, string> = {
  planned: 'border-border bg-muted/40 text-muted-foreground',
  active: 'border-primary/40 bg-primary/10 text-primary',
  success: 'border-status-launched/40 bg-status-launched/10 text-status-launched',
  blocked: 'border-status-launching/40 bg-status-launching/10 text-status-launching',
  failed: 'border-status-error/40 bg-status-error/10 text-status-error',
  info: 'border-border bg-muted/40 text-muted-foreground',
};

const SUMMARY_CATEGORIES = new Set<ActivityJournalCategory>([
  'status',
  'decision',
  'action',
  'blocker',
  'squad',
  'mcp',
  'result',
]);

type ViewMode = 'deep' | 'summary';

interface TimelineEntry {
  id: string;
  at: string;
  category: ActivityJournalCategory | 'notification' | 'terminal';
  status: ActivityJournalStatus;
  level: ActivityLevel;
  text: string;
  detail?: string;
  authority?: ActivityAuthority;
  mcpServerId?: string | null;
  toolName?: string | null;
  sessionId?: string | null;
  squadId?: string | null;
  live?: boolean;
}

interface StatusHelp {
  title: string;
  meaning: string;
  reason: string;
  remedy?: string;
  code: string;
}

const MAX_LIVE_ENTRIES = 300;

function initialMode(): ViewMode {
  try {
    return window.localStorage.getItem('synapse.live-view-mode') === 'summary' ? 'summary' : 'deep';
  } catch {
    return 'deep';
  }
}

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

function elapsedSince(iso: string, now: number): string {
  const started = new Date(iso).getTime();
  if (Number.isNaN(started)) return 'unknown';
  const seconds = Math.max(0, Math.floor((now - started) / 1000));
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const rest = seconds % 60;
  if (hours > 0) return `${hours}h ${minutes}m ${rest}s`;
  if (minutes > 0) return `${minutes}m ${rest}s`;
  return `${rest}s`;
}

function statusLevel(status: ActivityJournalStatus): ActivityLevel {
  if (status === 'failed') return 'red';
  if (status === 'blocked') return 'yellow';
  if (status === 'success') return 'green';
  return 'info';
}

function connectionHelp(session: ActivitySession): StatusHelp {
  if (session.connection_help) {
    return {
      title: `${session.connection_level[0].toUpperCase()}${session.connection_level.slice(1)} · ${session.connection_help.title}`,
      meaning: session.connection_help.explanation,
      reason: session.connection_code === 'ok'
        ? 'Synapse confirmed the session registration, project binding, and expected MCP availability.'
        : session.connection_help.explanation,
      remedy: session.connection_help.remedy || undefined,
      code: session.connection_code,
    };
  }
  const catalog: Record<string, Omit<StatusHelp, 'code'>> = {
    ok: {
      title: 'Green · fully connected',
      meaning: 'The AI registered successfully and had access to its expected Synapse connection.',
      reason: 'Project binding and enabled MCP availability checks passed when this session connected.',
    },
    'degraded.mcp_unavailable': {
      title: 'Yellow · some tools offline',
      meaning: 'The AI is connected, but at least one enabled MCP server was unavailable at registration time.',
      reason: 'Synapse could not confirm every enabled MCP server as connected or ready.',
      remedy: 'Open MCP Servers to identify and restart the unavailable server, then reconnect the AI.',
    },
    'degraded.no_project': {
      title: 'Yellow · no project selected',
      meaning: 'The AI is connected, but project-scoped files, records, and launches are unavailable.',
      reason: 'This session registered without a project_id.',
      remedy: 'Reconnect or register the session with the intended project.',
    },
    'failed.internal': {
      title: 'Red · connection failed',
      meaning: 'Synapse could not finish registering the AI session.',
      reason: 'An internal error occurred during registration.',
      remedy: 'Open daemon logs, resolve the reported error, and retry.',
    },
  };
  const selected = catalog[session.connection_code] ?? catalog['failed.internal'];
  return { ...selected, code: session.connection_code };
}

function workStatusHelp(session: ActivitySession, detail: ActivitySessionDetail | null): StatusHelp {
  const blocker = detail?.journal.find((event) =>
    event.session_id === session.id && (event.category === 'blocker' || event.status === 'blocked')
  );
  if (session.status === 'blocked') {
    return {
      title: 'Blocked · needs something before continuing',
      meaning: 'The AI has explicitly marked its work as unable to progress.',
      reason: blocker?.summary_md || blocker?.title || session.last_intent || 'The AI did not report a blocker reason yet.',
      remedy: blocker ? 'Review the reported blocker and provide the missing decision, access, resource, or fix.' : 'Ask the AI to report a blocker receipt with the specific cause and next requirement.',
      code: 'session.blocked',
    };
  }
  if (session.status === 'holding') {
    return {
      title: 'Holding · intentionally paused',
      meaning: 'The session is preserved but is not actively progressing.',
      reason: session.last_intent || 'No pause reason was reported.',
      remedy: 'Resume the session when the operator or another dependency is ready.',
      code: 'session.holding',
    };
  }
  if (session.status === 'idle') {
    return {
      title: 'Idle · connected and waiting',
      meaning: 'The AI remains connected but is not currently executing work.',
      reason: session.last_intent || session.task || 'No current focus was reported.',
      code: 'session.idle',
    };
  }
  if (session.status === 'gone') {
    return {
      title: 'Gone · session ended',
      meaning: 'The AI session ended or its heartbeat expired; this does not by itself prove the task completed.',
      reason: session.ended_at ? `The session ended at ${formatLocal(session.ended_at, 'long')}.` : 'The session is no longer active.',
      remedy: 'Check the final result or blocker receipt to learn whether the goal completed, then reconnect if more work is needed.',
      code: 'session.gone',
    };
  }
  return {
    title: 'Active · working now',
    meaning: 'The AI is connected and currently marked active.',
    reason: session.last_intent || session.task || 'The AI has not reported its current focus yet.',
    code: 'session.active',
  };
}

function notificationToEntry(notification: ActivityNotification): TimelineEntry {
  return {
    id: `n:${notification.id}`,
    at: notification.created_at,
    category: 'notification',
    // Connection health and work status are separate axes. Yellow means a
    // degraded connection (for example no project binding), not blocked work.
    status: notification.level === 'red' ? 'failed' : 'info',
    level: notification.level,
    text: notification.title,
    detail: notification.body_md || undefined,
  };
}

function journalToEntry(event: ActivityJournalEvent, live = false): TimelineEntry {
  return {
    id: `j:${event.id}`,
    at: event.created_at,
    category: event.category,
    status: event.status,
    level: statusLevel(event.status),
    text: event.title,
    detail: event.summary_md || undefined,
    authority: event.authority,
    mcpServerId: event.mcp_server_id,
    toolName: event.tool_name,
    sessionId: event.session_id,
    squadId: event.squad_id,
    live,
  };
}

function decodePty(data: unknown): string {
  if (typeof data !== 'string' || !data) return '';
  try {
    const bytes = Uint8Array.from(window.atob(data), (char) => char.charCodeAt(0));
    return new TextDecoder().decode(bytes).trim();
  } catch {
    return '';
  }
}

function CategoryIcon({ category, toolName }: { category: TimelineEntry['category']; toolName?: string | null }): JSX.Element {
  const cls = 'h-3.5 w-3.5';
  if (toolName?.startsWith('Synapse')) return <img src='/icon.svg' alt='' className={cls} />;
  if (category === 'reasoning' || category === 'plan' || category === 'decision') {
    return <BrainCircuit className={cls} aria-hidden='true' />;
  }
  if (category === 'idea') return <Lightbulb className={cls} aria-hidden='true' />;
  if (category === 'mcp') return <Network className={cls} aria-hidden='true' />;
  if (category === 'search') return <Globe2 className={cls} aria-hidden='true' />;
  if (category === 'tool') return <Wrench className={cls} aria-hidden='true' />;
  if (category === 'squad') return <Users className={cls} aria-hidden='true' />;
  if (category === 'terminal') return <Terminal className={cls} aria-hidden='true' />;
  if (category === 'blocker') return <CircleAlert className={cls} aria-hidden='true' />;
  if (category === 'result' || category === 'evidence') {
    return <CheckCircle2 className={cls} aria-hidden='true' />;
  }
  return <Activity className={cls} aria-hidden='true' />;
}

export function LiveViewPage(): JSX.Element {
  const { subscribeRaw, connState, projects } = useDaemon();
  const [viewMode, setViewMode] = useState<ViewMode>(initialMode);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [squadsOpen, setSquadsOpen] = useState(false);
  const [goalsOpen, setGoalsOpen] = useState(false);
  const [goalDraft, setGoalDraft] = useState('');
  const [editingGoalId, setEditingGoalId] = useState<string | null>(null);
  const [editingGoalTitle, setEditingGoalTitle] = useState('');
  const [goalBusyId, setGoalBusyId] = useState<string | null>(null);
  const [goalToDelete, setGoalToDelete] = useState<ActivityGoal | null>(null);
  const [goalError, setGoalError] = useState<string | null>(null);
  const [selectedSquadId, setSelectedSquadId] = useState<string | null>(null);
  const [selectedWorkerId, setSelectedWorkerId] = useState<string | null>(null);
  const [expandedEntryId, setExpandedEntryId] = useState<string | null>(null);
  const [statusHelp, setStatusHelp] = useState<StatusHelp | null>(null);
  const [showAllSessions, setShowAllSessions] = useState(false);
  const [clock, setClock] = useState(() => Date.now());
  const [sessions, setSessions] = useState<ActivitySession[] | null>(null);
  const [sessionsError, setSessionsError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<ActivitySessionDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [liveEntries, setLiveEntries] = useState<TimelineEntry[]>([]);
  const timelineRef = useRef<HTMLDivElement | null>(null);
  const lastSquadCountRef = useRef(0);

  const refreshSessions = useCallback(async () => {
    try {
      const { sessions: list } = await getActivitySessions();
      setSessions(list);
      setSessionsError(null);
      setSelectedId((current) => (
        current
        ?? list.find((session) => (
          !session.coder_thread_id
          && Boolean(session.project_id)
          && session.status !== 'gone'
        ))?.id
        ?? list.find((session) => !session.coder_thread_id && session.status !== 'gone')?.id
        ?? list[0]?.id
        ?? null
      ));
    } catch (error) {
      setSessionsError((error as Error).message || 'Could not load sessions.');
      setSessions((previous) => previous ?? []);
    }
  }, []);

  const refreshDetail = useCallback(async (sessionId: string, showLoader = false) => {
    if (showLoader) setDetailLoading(true);
    try {
      const next = await getActivitySessionDetail(sessionId);
      setDetail(next);
    } catch {
      setDetail(null);
    } finally {
      if (showLoader) setDetailLoading(false);
    }
  }, []);

  useEffect(() => {
    if (connState !== 'open') return;
    void refreshSessions();
  }, [connState, refreshSessions]);

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      return;
    }
    setLiveEntries([]);
    setDetail(null);
    setSquadsOpen(false);
    setGoalsOpen(false);
    setGoalDraft('');
    setEditingGoalId(null);
    setGoalError(null);
    lastSquadCountRef.current = 0;
    setSelectedSquadId(null);
    setSelectedWorkerId(null);
    void refreshDetail(selectedId, true);
  }, [refreshDetail, selectedId]);

  const selected = useMemo(
    () => sessions?.find((session) => session.id === selectedId) ?? detail?.session ?? null,
    [detail, selectedId, sessions]
  );

  const displayedSessions = useMemo(
    () => showAllSessions ? (sessions ?? []) : (sessions ?? []).slice(0, 3),
    [sessions, showAllSessions]
  );

  const relevantSquadIds = useMemo(
    () => new Set((detail?.squads ?? []).map((view) => String(view.squad.id ?? ''))),
    [detail]
  );

  const relevantPtyIds = useMemo(() => {
    const ids = new Set<string>();
    if (selected?.coder_thread_id) ids.add(selected.coder_thread_id);
    for (const view of detail?.squads ?? []) {
      for (const item of view.work_items) {
        const id = String(item.pty_session_id ?? '');
        if (id) ids.add(id);
      }
    }
    return ids;
  }, [detail, selected]);

  useEffect(
    () =>
      subscribeRaw((rawEvent) => {
        const name = rawEvent.name;
        const payload = (rawEvent.payload ?? {}) as Record<string, unknown>;

        if (name.startsWith('v1.coordination.session_')) {
          void refreshSessions();
          const eventSessionId = String(payload.id ?? payload.session_id ?? '');
          if (
            name === 'v1.coordination.session_registered'
            && eventSessionId
            && !String(payload.coder_thread_id ?? '').trim()
          ) {
            // A new connection is the most relevant thing happening now. Bring
            // external/root sessions into view immediately. Spawned workers
            // stay visible in the squad roll-up without yanking the operator
            // away from the parent every time a reviewer registers.
            setSelectedId(eventSessionId);
          }
          if (selectedId && (!eventSessionId || eventSessionId === selectedId)) {
            void refreshDetail(selectedId);
          }
          return;
        }

        if (name === 'v1.activity.notification') {
          const notification = payload.notification as ActivityNotification | undefined;
          if (!notification || notification.session_id !== selectedId) return;
          setLiveEntries((previous) =>
            [...previous, { ...notificationToEntry(notification), live: true }].slice(-MAX_LIVE_ENTRIES)
          );
          return;
        }

        if (name === 'v1.activity.journaled') {
          const event = payload.event as ActivityJournalEvent | undefined;
          if (!event) return;
          const matchesSession = event.session_id === selectedId;
          const matchesSquad = Boolean(event.squad_id && relevantSquadIds.has(event.squad_id));
          if (!matchesSession && !matchesSquad) return;
          setLiveEntries((previous) => [...previous, journalToEntry(event, true)].slice(-MAX_LIVE_ENTRIES));
          if (selectedId) void refreshDetail(selectedId);
          return;
        }

        if (name === 'v1.activity.goals_updated') {
          if (String(payload.session_id ?? '') === selectedId && selectedId) {
            void refreshDetail(selectedId);
          }
          return;
        }

        if (name === 'v1.pty.session_output') {
          const ptyId = String(payload.session_id ?? '');
          if (!relevantPtyIds.has(ptyId)) return;
          const text = decodePty(payload.data);
          if (!text) return;
          const entry: TimelineEntry = {
            id: `o:${rawEvent.id}`,
            at: new Date().toISOString(),
            category: 'terminal',
            status: 'info',
            level: 'info',
            text: text.length > 600 ? `${text.slice(0, 600)}…` : text,
            live: true,
          };
          setLiveEntries((previous) => [...previous, entry].slice(-MAX_LIVE_ENTRIES));
          return;
        }

        if (
          name.startsWith('v1.agent_work_item.') ||
          name.startsWith('v1.agent_run.') ||
          name.startsWith('v1.agent_mcp.') ||
          name.startsWith('v1.agent_squad.')
        ) {
          const item = (payload.work_item ?? payload.squad ?? {}) as Record<string, unknown>;
          const squadId = String(item.squad_id ?? item.id ?? payload.squad_id ?? '');
          if (selectedId && (relevantSquadIds.has(squadId) || selected?.project_id === item.project_id)) {
            void refreshDetail(selectedId);
          }
        }
      }),
    [refreshDetail, refreshSessions, relevantPtyIds, relevantSquadIds, selected, selectedId, subscribeRaw]
  );

  const sessionProject = useMemo(
    () => (selected?.project_id ? projects.find((project) => project.id === selected.project_id) ?? null : null),
    [projects, selected]
  );
  const canPreview = previewUrl(sessionProject) !== null;

  const timeline = useMemo<TimelineEntry[]>(() => {
    const persisted = [
      ...(detail?.notifications ?? []).map(notificationToEntry),
      ...(detail?.journal ?? []).map((event) => journalToEntry(event)),
    ];
    const byId = new Map<string, TimelineEntry>();
    for (const entry of [...persisted, ...liveEntries]) byId.set(entry.id, entry);
    return [...byId.values()]
      .filter((entry) => viewMode === 'deep' || (entry.category !== 'terminal' && (
        entry.category === 'notification' || SUMMARY_CATEGORIES.has(entry.category)
      )))
      .sort((a, b) => new Date(a.at).getTime() - new Date(b.at).getTime());
  }, [detail, liveEntries, viewMode]);

  const currentExplanation = useMemo(() => {
    if (viewMode !== 'deep') return null;
    return [...timeline].reverse().find((entry) =>
      (entry.category === 'reasoning' || entry.category === 'decision' || entry.category === 'plan')
      && (entry.sessionId === selectedId || Boolean(entry.squadId && relevantSquadIds.has(entry.squadId)))
      && Boolean(entry.detail)
    ) ?? null;
  }, [relevantSquadIds, selectedId, timeline, viewMode]);

  useEffect(() => {
    const element = timelineRef.current;
    if (element) element.scrollTop = element.scrollHeight;
  }, [timeline.length]);

  useEffect(() => {
    window.dispatchEvent(new CustomEvent('synapse:live-inspector', {
      detail: { open: goalsOpen || squadsOpen || previewOpen },
    }));
    return () => {
      window.dispatchEvent(new CustomEvent('synapse:live-inspector', {
        detail: { open: false },
      }));
    };
  }, [goalsOpen, previewOpen, squadsOpen]);

  const tokenTotal = useMemo(() => {
    let total = 0;
    for (const view of detail?.squads ?? []) {
      total += Number((view.token_usage as { total_tokens?: number }).total_tokens ?? 0);
    }
    return total;
  }, [detail]);

  const goals = detail?.goals ?? [];
  const completedGoalCount = goals.filter((goal) => goal.status === 'completed').length;

  const activeTools = useMemo(() => {
    const values = new Set<string>();
    for (const event of detail?.journal ?? []) {
      if (event.mcp_server_id) values.add(`MCP · ${event.mcp_server_id}`);
      else if (event.tool_name) values.add(event.tool_name);
    }
    return [...values].slice(0, 5);
  }, [detail]);

  useEffect(() => {
    const count = detail?.squads.length ?? 0;
    if (count === 0) setSquadsOpen(false);
    else if (count > lastSquadCountRef.current && !goalsOpen && !previewOpen) setSquadsOpen(true);
    lastSquadCountRef.current = count;
  }, [detail?.squads.length, goalsOpen, previewOpen]);

  const selectedSquadView = useMemo(
    () => detail?.squads.find((view) => String(view.squad.id) === selectedSquadId) ?? null,
    [detail, selectedSquadId]
  );

  const selectedWorker = useMemo(() => {
    if (!selectedSquadView || !selectedWorkerId) return null;
    const item = selectedSquadView.work_items.find((candidate) => String(candidate.id) === selectedWorkerId) ?? null;
    const profile = selectedSquadView.worker_profiles.find((candidate) => candidate.work_item_id === selectedWorkerId) ?? null;
    return item && profile ? { item, profile } : null;
  }, [selectedSquadView, selectedWorkerId]);

  useEffect(() => {
    if (!selectedWorker || String(selectedWorker.item.status) !== 'running') return;
    const timer = window.setInterval(() => setClock(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [selectedWorker]);

  const changeMode = (next: ViewMode) => {
    setViewMode(next);
    try {
      window.localStorage.setItem('synapse.live-view-mode', next);
    } catch {
      // The preference remains valid for this window when storage is unavailable.
    }
  };

  const addGoal = async () => {
    if (!selectedId || !goalDraft.trim()) return;
    setGoalBusyId('new');
    setGoalError(null);
    try {
      await createActivityGoal(selectedId, { title: goalDraft.trim() });
      setGoalDraft('');
      await refreshDetail(selectedId);
    } catch (error) {
      setGoalError((error as Error).message || 'Could not add that goal.');
    } finally {
      setGoalBusyId(null);
    }
  };

  const setGoalStatus = async (goal: ActivityGoal) => {
    if (!selectedId) return;
    setGoalBusyId(goal.id);
    setGoalError(null);
    try {
      await updateActivityGoal(selectedId, goal.id, {
        status: goal.status === 'completed' ? 'pending' : 'completed',
      });
      await refreshDetail(selectedId);
    } catch (error) {
      setGoalError((error as Error).message || 'Could not update that goal.');
    } finally {
      setGoalBusyId(null);
    }
  };

  const saveGoalTitle = async (goal: ActivityGoal) => {
    if (!selectedId || !editingGoalTitle.trim()) return;
    setGoalBusyId(goal.id);
    setGoalError(null);
    try {
      await updateActivityGoal(selectedId, goal.id, { title: editingGoalTitle.trim() });
      setEditingGoalId(null);
      await refreshDetail(selectedId);
    } catch (error) {
      setGoalError((error as Error).message || 'Could not rename that goal.');
    } finally {
      setGoalBusyId(null);
    }
  };

  const confirmDeleteGoal = async () => {
    if (!selectedId || !goalToDelete) return;
    setGoalBusyId(goalToDelete.id);
    setGoalError(null);
    try {
      await deleteActivityGoal(selectedId, goalToDelete.id);
      setGoalToDelete(null);
      await refreshDetail(selectedId);
    } catch (error) {
      setGoalError((error as Error).message || 'Could not remove that goal.');
    } finally {
      setGoalBusyId(null);
    }
  };

  return (
    <div className='flex h-full min-h-0 flex-col gap-4 overflow-hidden'>
      <PageHeader
        title='Live'
        subtitle='Plans, reasoning summaries, actions, squads, and MCP use from every connected AI.'
        action={
          <div className='flex items-center gap-2'>
            <div className='inline-flex rounded-md border border-border p-0.5' aria-label='Live View detail mode'>
              <button
                type='button'
                onClick={() => changeMode('deep')}
                aria-pressed={viewMode === 'deep'}
                className={cn(
                  'inline-flex items-center gap-1 rounded px-2 py-1 text-xs transition',
                  viewMode === 'deep' ? 'bg-primary/15 text-primary' : 'text-muted-foreground hover:text-foreground'
                )}
              >
                <BrainCircuit className='h-3.5 w-3.5' aria-hidden='true' /> Deep
              </button>
              <button
                type='button'
                onClick={() => changeMode('summary')}
                aria-pressed={viewMode === 'summary'}
                className={cn(
                  'inline-flex items-center gap-1 rounded px-2 py-1 text-xs transition',
                  viewMode === 'summary' ? 'bg-primary/15 text-primary' : 'text-muted-foreground hover:text-foreground'
                )}
              >
                <Eye className='h-3.5 w-3.5' aria-hidden='true' /> Summary
              </button>
            </div>
            <button
              type='button'
              onClick={() => void refreshSessions()}
              className='inline-flex items-center gap-1.5 rounded-md border border-border px-2.5 py-1.5 text-xs transition hover:border-primary'
            >
              <RefreshCw className='h-3.5 w-3.5' aria-hidden='true' /> Refresh
            </button>
          </div>
        }
      />

      <ThreadPresencePanel />

      <div className='flex min-h-0 flex-1 flex-col gap-4 overflow-hidden lg:flex-row'>
        <Card className='flex max-h-48 min-h-0 shrink-0 flex-col overflow-hidden p-0 lg:max-h-none lg:w-64'>
          <div className='shrink-0 border-b border-border px-3 py-2'>
            <p className='text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground'>Sessions</p>
          </div>
          <div className='scrollbar-thin min-h-0 flex-1 overflow-y-auto'>
            {sessions === null ? (
              <p className='flex items-center gap-2 px-3 py-4 text-xs text-muted-foreground'>
                <Loader2 className='h-3.5 w-3.5 animate-spin' aria-hidden='true' /> Loading sessions…
              </p>
            ) : sessionsError && sessions.length === 0 ? (
              <p role='alert' className='px-3 py-4 text-xs text-destructive'>{sessionsError}</p>
            ) : sessions.length === 0 ? (
              <div className='px-3 py-6 text-center'>
                <Radio className='mx-auto h-5 w-5 text-muted-foreground' aria-hidden='true' />
                <p className='mt-2 text-xs font-medium'>No AI sessions yet</p>
                <p className='mt-1 text-[11px] text-muted-foreground'>AIs appear here when they connect to Synapse.</p>
              </div>
            ) : (
              <ul className='divide-y divide-border'>
                {displayedSessions.map((session) => (
                  <li key={session.id}>
                    <button
                      type='button'
                      onClick={() => setSelectedId(session.id)}
                      className={cn(
                        'w-full px-3 py-2.5 text-left transition hover:bg-accent/40',
                        session.id === selectedId && 'bg-accent/60'
                      )}
                    >
                      <div className='flex items-center gap-2'>
                        <span
                          className={cn(
                            'h-2 w-2 shrink-0 rounded-full',
                            LEVEL_DOT[sessionIndicatorLevel(session)] ?? LEVEL_DOT.info,
                            session.status === 'active' && !session.stale && 'animate-pulse'
                          )}
                          title={`${workStatusHelp(session, session.id === selectedId ? detail : null).title} · ${connectionHelp(session).title}`}
                          aria-hidden='true'
                        />
                        <span className='font-mono text-xs text-muted-foreground'>
                          {session.seq == null ? '—' : `#${String(session.seq).padStart(3, '0')}`}
                        </span>
                        <span className='truncate text-sm font-medium'>{session.agent_label || session.runtime_id || 'AI'}</span>
                      </div>
                      <p className='mt-0.5 truncate text-[11px] text-muted-foreground'>
                        {session.project_name || session.project_id || 'No project'} · {session.status}{session.stale ? ' · stale' : ''} · {relative(session.last_heartbeat_at)}
                      </p>
                      {(session.last_intent || session.task) && (
                        <p className='mt-1 line-clamp-2 text-[11px] text-foreground/75'>
                          {session.last_intent || session.task}
                        </p>
                      )}
                      {/* Workers run under this AI. They are listed here rather than as
                          their own rail rows -- that duplication is what made the rail
                          unreadable. Full detail stays in the Squads drawer. */}
                      {!!session.child_count && (
                        <ul className='mt-1.5 space-y-0.5 border-l border-border/60 pl-2'>
                          {(session.children ?? []).slice(0, 4).map((child) => (
                            <li key={child.id} className='flex items-center gap-1.5'>
                              <span
                                className={cn(
                                  'h-1.5 w-1.5 shrink-0 rounded-full',
                                  LEVEL_DOT[sessionIndicatorLevel(child)] ?? LEVEL_DOT.info
                                )}
                                aria-hidden='true'
                              />
                              <span className='truncate text-[10px] text-muted-foreground'>
                                {child.chatgpt_worker?.title || child.agent_label || child.runtime_id}
                              </span>
                            </li>
                          ))}
                          {session.child_count > 4 && (
                            <li className='text-[10px] text-muted-foreground/70'>
                              +{session.child_count - 4} more
                            </li>
                          )}
                        </ul>
                      )}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
          {(sessions?.length ?? 0) > 3 && (
            <button
              type='button'
              onClick={() => setShowAllSessions((value) => !value)}
              className='shrink-0 border-t border-border px-3 py-2 text-left text-xs text-primary transition hover:bg-accent/40'
            >
              {showAllSessions ? 'Show 3 recent' : `Show more recent (${(sessions?.length ?? 0) - 3})`}
            </button>
          )}
        </Card>

        <Card className='flex min-h-0 flex-1 flex-col overflow-hidden p-0'>
          {selected && (
            <div className='shrink-0 border-b border-border'>
              <div className='flex flex-wrap items-center justify-between gap-2 px-4 py-2.5'>
                <div className='min-w-0'>
                  <p className='truncate text-sm font-semibold'>
                    Session #{String(selected.seq).padStart(3, '0')} · {selected.agent_label || selected.runtime_id}
                  </p>
                  <div className='mt-1 flex flex-wrap items-center gap-1.5 text-[10px] text-muted-foreground'>
                    <button
                      type='button'
                      onClick={() => setStatusHelp(connectionHelp(detail?.session ?? selected))}
                      title={connectionHelp(detail?.session ?? selected).meaning}
                      aria-live='polite'
                      className={cn(
                        'rounded-full border px-1.5 py-0.5 uppercase tracking-wide',
                        selected.connection_level === 'green' && 'border-status-launched/40 bg-status-launched/10 text-status-launched',
                        selected.connection_level === 'yellow' && 'border-status-launching/40 bg-status-launching/10 text-status-launching',
                        selected.connection_level === 'red' && 'border-status-error/40 bg-status-error/10 text-status-error'
                      )}
                    >
                      {selected.connection_level} connection
                    </button>
                    <button
                      type='button'
                      onClick={() => setStatusHelp(workStatusHelp(detail?.session ?? selected, detail))}
                      title={workStatusHelp(detail?.session ?? selected, detail).meaning}
                      aria-live='polite'
                      className={cn(
                        'rounded-full border px-1.5 py-0.5 uppercase tracking-wide',
                        selected.status === 'active' && 'border-primary/40 bg-primary/10 text-primary',
                        selected.status === 'blocked' && 'border-status-launching/40 bg-status-launching/10 text-status-launching',
                        !['active', 'blocked'].includes(selected.status) && 'border-border bg-muted/40 text-muted-foreground'
                      )}
                    >
                      {selected.status}
                    </button>
                    <span>registered {relative(selected.registered_at)}{selected.project_id ? ` · ${selected.project_name || selected.project_id}` : ''}</span>
                  </div>
                </div>
                <div className='flex items-center gap-2 text-[11px] text-muted-foreground'>
                  {tokenTotal > 0 && <span className='font-mono'>{tokenTotal.toLocaleString()} tokens</span>}
                  <button
                    type='button'
                    onClick={() => {
                      const next = !goalsOpen;
                      setGoalsOpen(next);
                      if (next) {
                        setSquadsOpen(false);
                        setPreviewOpen(false);
                      }
                    }}
                    aria-pressed={goalsOpen}
                    className={cn(
                      'inline-flex items-center gap-1.5 rounded-md border border-border px-2 py-1 transition hover:border-primary',
                      goalsOpen && 'border-primary text-foreground'
                    )}
                  >
                    <ListChecks className='h-3.5 w-3.5' aria-hidden='true' />
                    Goals {goals.length > 0 ? `[${completedGoalCount}/${goals.length}]` : ''}
                  </button>
                  {(detail?.squads.length ?? 0) > 0 && (
                    <button
                      type='button'
                      onClick={() => {
                        const next = !squadsOpen;
                        setSquadsOpen(next);
                        if (next) {
                          setGoalsOpen(false);
                          setPreviewOpen(false);
                        }
                      }}
                      aria-pressed={squadsOpen}
                      className={cn(
                        'inline-flex items-center gap-1.5 rounded-md border border-border px-2 py-1 transition hover:border-primary',
                        squadsOpen && 'border-primary text-foreground'
                      )}
                    >
                      <Users className='h-3.5 w-3.5' aria-hidden='true' /> Squads ({detail?.squads.length ?? 0})
                    </button>
                  )}
                  {canPreview && (
                    <button
                      type='button'
                      onClick={() => {
                        const next = !previewOpen;
                        setPreviewOpen(next);
                        if (next) {
                          setGoalsOpen(false);
                          setSquadsOpen(false);
                        }
                      }}
                      aria-pressed={previewOpen}
                      className={cn(
                        'inline-flex items-center gap-1.5 rounded-md border border-border px-2 py-1 transition hover:border-primary',
                        previewOpen && 'border-primary text-foreground'
                      )}
                    >
                      <MonitorPlay className='h-3.5 w-3.5' aria-hidden='true' /> Preview
                    </button>
                  )}
                </div>
              </div>
              <div className='border-t border-border/60 bg-muted/20 px-4 py-2' aria-live='polite'>
                <div className={cn('grid gap-2', currentExplanation && 'md:grid-cols-2')}>
                  <div className='flex min-w-0 items-start gap-2'>
                    <Gauge className='mt-0.5 h-3.5 w-3.5 shrink-0 text-primary' aria-hidden='true' />
                    <div className='min-w-0'>
                      <p className='text-[10px] font-semibold uppercase tracking-wide text-muted-foreground'>Now</p>
                      <p className='line-clamp-2 text-xs leading-relaxed'>
                        {detail?.session.last_intent || selected.last_intent || selected.task || 'Waiting for the next status update.'}
                      </p>
                    </div>
                  </div>
                  {currentExplanation && (
                    <div className='flex min-w-0 items-start gap-2 border-border/60 md:border-l md:pl-3'>
                      <BrainCircuit className='mt-0.5 h-3.5 w-3.5 shrink-0 text-primary' aria-hidden='true' />
                      <div className='min-w-0'>
                        <p className='text-[10px] font-semibold uppercase tracking-wide text-muted-foreground'>Why this step</p>
                        <p className='line-clamp-2 text-xs leading-relaxed text-muted-foreground' title={currentExplanation.detail}>
                          {currentExplanation.detail}
                        </p>
                      </div>
                    </div>
                  )}
                </div>
                {activeTools.length > 0 && (
                  <div className='mt-2 flex flex-wrap gap-1.5'>
                    {activeTools.map((tool) => (
                      <span key={tool} className='rounded-full border border-border bg-background/60 px-2 py-0.5 text-[10px] text-muted-foreground'>
                        {tool}
                      </span>
                    ))}
                  </div>
                )}
                {(detail?.chatgpt_workers.length ?? 0) > 0 && (
                  <div className='mt-2 flex flex-wrap items-center gap-1.5'>
                    <span className='text-[10px] font-semibold uppercase tracking-wide text-muted-foreground'>
                      Synapse2GPT workers
                    </span>
                    {(detail?.chatgpt_workers ?? []).slice(0, 3).map((worker) => (
                      worker.conversation_url ? (
                        <a
                          key={worker.id}
                          href={worker.conversation_url}
                          target='_blank'
                          rel='noreferrer'
                          title={`Open ${worker.title} in ChatGPT`}
                          className='max-w-56 truncate rounded-full border border-border bg-background/60 px-2 py-0.5 text-[10px] text-primary hover:border-primary'
                        >
                          {worker.title}
                        </a>
                      ) : (
                        <span
                          key={worker.id}
                          title={worker.title}
                          className='max-w-56 truncate rounded-full border border-border bg-background/60 px-2 py-0.5 text-[10px] text-muted-foreground'
                        >
                          {worker.title} · {worker.status}
                        </span>
                      )
                    ))}
                    {(detail?.chatgpt_workers.length ?? 0) > 3 && (
                      <span className='text-[10px] text-muted-foreground'>
                        +{(detail?.chatgpt_workers.length ?? 0) - 3} more
                      </span>
                    )}
                  </div>
                )}
              </div>
              <div className='border-t border-border/60 px-4 py-1.5 text-[10px] text-muted-foreground'>
                {viewMode === 'deep'
                  ? 'Deep View is on by default: rich deliberate summaries and receipts are shown. Private chain-of-thought and secrets are never recorded.'
                  : 'Summary View hides detailed plans, reasoning summaries, ideas, evidence, tools, and terminal output.'}
              </div>
            </div>
          )}

          <div ref={timelineRef} className='scrollbar-thin min-h-0 flex-1 overflow-y-auto px-4 py-3'>
            {!selected ? (
              <p className='py-10 text-center text-sm text-muted-foreground'>Select a session to watch what it is doing.</p>
            ) : detailLoading && timeline.length === 0 ? (
              <p className='flex items-center justify-center gap-2 py-10 text-sm text-muted-foreground'>
                <Loader2 className='h-4 w-4 animate-spin' aria-hidden='true' /> Loading this session…
              </p>
            ) : timeline.length === 0 ? (
              <div className='py-10 text-center'>
                <Bot className='mx-auto h-5 w-5 text-muted-foreground' aria-hidden='true' />
                <p className='mt-2 text-sm font-medium'>Nothing recorded yet</p>
                <p className='mt-1 text-xs text-muted-foreground'>Structured milestones from this AI will stream in here.</p>
              </div>
            ) : (
              <ol className='flex flex-col gap-2.5' aria-label='Live AI activity' aria-live='polite' aria-relevant='additions text'>
                {timeline.map((entry) => (
                  <li key={entry.id} className='flex flex-wrap gap-2.5 sm:flex-nowrap'>
                    <span className='mt-1 shrink-0 font-mono text-[10px] text-muted-foreground'>{shortTime(entry.at)}</span>
                    <div className={cn('mt-0.5 shrink-0 text-muted-foreground', entry.live && 'text-primary')}>
                      <CategoryIcon category={entry.category} toolName={entry.toolName} />
                    </div>
                    <button
                      type='button'
                      onClick={() => setExpandedEntryId((current) => current === entry.id ? null : entry.id)}
                      aria-expanded={expandedEntryId === entry.id}
                      className='min-w-0 basis-full rounded-md border border-border/70 bg-muted/10 px-3 py-2 text-left transition hover:border-primary/50 hover:bg-muted/20 sm:flex-1 sm:basis-auto'
                    >
                      <div className='flex flex-wrap items-center gap-1.5'>
                        <span className='text-[10px] font-semibold uppercase tracking-wide text-muted-foreground'>{entry.category}</span>
                        <span
                          title={`This receipt is ${entry.status}. Click the receipt for its recorded reason and evidence.`}
                          className={cn('rounded-full border px-1.5 py-0.5 text-[9px] uppercase tracking-wide', STATUS_STYLE[entry.status])}
                        >
                          {entry.status}
                        </span>
                        {entry.authority && entry.authority !== 'none' && (
                          <span className='rounded-full border border-border px-1.5 py-0.5 text-[9px] uppercase tracking-wide text-muted-foreground'>
                            authority: {entry.authority}
                          </span>
                        )}
                        {entry.live && <span className='text-[9px] uppercase tracking-wide text-primary'>live</span>}
                      </div>
                      <p className={cn('mt-1 break-words text-sm', entry.category === 'terminal' && 'whitespace-pre-wrap font-mono text-xs text-muted-foreground')}>
                        {entry.text}
                      </p>
                      {entry.detail && (
                        <p className='mt-1 whitespace-pre-wrap break-words text-xs leading-relaxed text-muted-foreground'>
                          {renderInlineBold(entry.detail)}
                        </p>
                      )}
                      {(entry.mcpServerId || entry.toolName) && (
                        <p className='mt-1.5 text-[10px] text-muted-foreground'>
                          {entry.mcpServerId ? `MCP server: ${entry.mcpServerId}` : `Tool: ${entry.toolName}`}
                        </p>
                      )}
                      {expandedEntryId === entry.id && (
                        <div className='mt-2 grid gap-1 border-t border-border/70 pt-2 text-[10px] text-muted-foreground sm:grid-cols-2'>
                          <span>Recorded: {formatLocal(entry.at, 'long')}</span>
                          <span>Source: {entry.category === 'notification' ? 'Synapse notification' : 'operator journal'}</span>
                          <span>Status: {entry.status}</span>
                          <span>Authority: {entry.authority ?? 'none'}</span>
                        </div>
                      )}
                    </button>
                  </li>
                ))}
              </ol>
            )}
          </div>
        </Card>

        {goalsOpen && selected && (
          <Card className='fixed inset-4 z-40 flex min-h-0 flex-col overflow-hidden p-0 shadow-xl lg:static lg:z-auto lg:w-80 lg:shadow-none'>
            <div className='shrink-0 border-b border-border px-3 py-2.5'>
              <div className='flex items-start justify-between gap-2'>
                <div className='min-w-0'>
                  <p className='flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground'>
                    <ListChecks className='h-3.5 w-3.5 text-primary' aria-hidden='true' /> Goals
                  </p>
                  <p className='mt-1 text-xs font-medium' aria-live='polite'>
                    [{completedGoalCount}/{goals.length}] complete
                  </p>
                </div>
                <button
                  type='button'
                  onClick={() => setGoalsOpen(false)}
                  aria-label='Collapse goals panel'
                  className='rounded p-0.5 text-muted-foreground transition hover:bg-accent hover:text-foreground'
                >
                  <X className='h-3.5 w-3.5' aria-hidden='true' />
                </button>
              </div>
              <div className='mt-2 h-1.5 overflow-hidden rounded-full bg-muted' aria-hidden='true'>
                <div
                  className='h-full rounded-full bg-primary transition-all'
                  style={{ width: `${goals.length ? Math.round((completedGoalCount / goals.length) * 100) : 0}%` }}
                />
              </div>
            </div>

            <div className='scrollbar-thin min-h-0 flex-1 overflow-y-auto p-3'>
              {goals.length === 0 ? (
                <div className='rounded-md border border-dashed border-border px-3 py-6 text-center'>
                  <ListChecks className='mx-auto h-5 w-5 text-muted-foreground' aria-hidden='true' />
                  <p className='mt-2 text-xs font-medium'>No goals captured yet</p>
                  <p className='mt-1 text-[11px] leading-relaxed text-muted-foreground'>
                    Add the milestones that matter. The AI can update the same list through Synapse.
                  </p>
                </div>
              ) : (
                <ol className='space-y-2' aria-label='Session goals'>
                  {goals.map((goal, index) => (
                    <li key={goal.id} className='rounded-md border border-border bg-muted/10 p-2.5'>
                      <div className='flex items-start gap-2'>
                        <button
                          type='button'
                          onClick={() => void setGoalStatus(goal)}
                          disabled={goalBusyId === goal.id}
                          aria-label={goal.status === 'completed' ? `Mark ${goal.title} incomplete` : `Complete ${goal.title}`}
                          className={cn(
                            'mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded border transition',
                            goal.status === 'completed'
                              ? 'border-primary bg-primary text-primary-foreground'
                              : 'border-border text-transparent hover:border-primary'
                          )}
                        >
                          {goalBusyId === goal.id
                            ? <Loader2 className='h-3 w-3 animate-spin text-primary' aria-hidden='true' />
                            : <CheckCircle2 className='h-3 w-3' aria-hidden='true' />}
                        </button>

                        <div className='min-w-0 flex-1'>
                          {editingGoalId === goal.id ? (
                            <form
                              className='flex items-center gap-1.5'
                              onSubmit={(event) => {
                                event.preventDefault();
                                void saveGoalTitle(goal);
                              }}
                            >
                              <input
                                autoFocus
                                value={editingGoalTitle}
                                onChange={(event) => setEditingGoalTitle(event.target.value)}
                                onKeyDown={(event) => {
                                  if (event.key === 'Escape') {
                                    event.preventDefault();
                                    setEditingGoalId(null);
                                    setEditingGoalTitle('');
                                  }
                                }}
                                maxLength={160}
                                aria-label={`Rename goal ${index + 1}`}
                                className='min-w-0 flex-1 rounded border border-border bg-background px-2 py-1 text-xs outline-none transition focus:border-primary focus:ring-1 focus:ring-primary'
                              />
                              <button
                                type='submit'
                                disabled={!editingGoalTitle.trim() || goalBusyId === goal.id}
                                aria-label='Save goal name'
                                className='rounded p-1 text-primary transition hover:bg-accent disabled:opacity-50'
                              >
                                <Save className='h-3.5 w-3.5' aria-hidden='true' />
                              </button>
                            </form>
                          ) : (
                            <p className={cn(
                              'break-words text-xs font-medium leading-relaxed',
                              goal.status === 'completed' && 'text-muted-foreground line-through'
                            )}>
                              {goal.title}
                            </p>
                          )}
                          <div className='mt-1 flex items-center gap-1.5'>
                            <span className={cn(
                              'rounded-full border px-1.5 py-0.5 text-[9px] uppercase tracking-wide',
                              goal.status === 'completed' && STATUS_STYLE.success,
                              goal.status === 'active' && STATUS_STYLE.active,
                              goal.status === 'blocked' && STATUS_STYLE.blocked,
                              goal.status === 'pending' && STATUS_STYLE.planned
                            )}>
                              {goal.status}
                            </span>
                            <span className='text-[9px] text-muted-foreground'>Goal {index + 1}</span>
                          </div>
                        </div>

                        {editingGoalId !== goal.id && (
                          <div className='flex shrink-0 items-center'>
                            <button
                              type='button'
                              onClick={() => {
                                setEditingGoalId(goal.id);
                                setEditingGoalTitle(goal.title);
                              }}
                              aria-label={`Rename ${goal.title}`}
                              className='rounded p-1 text-muted-foreground transition hover:bg-accent hover:text-foreground'
                            >
                              <Pencil className='h-3 w-3' aria-hidden='true' />
                            </button>
                            <button
                              type='button'
                              onClick={() => setGoalToDelete(goal)}
                              aria-label={`Remove ${goal.title}`}
                              className='rounded p-1 text-muted-foreground transition hover:bg-accent hover:text-destructive'
                            >
                              <Trash2 className='h-3 w-3' aria-hidden='true' />
                            </button>
                          </div>
                        )}
                      </div>
                    </li>
                  ))}
                </ol>
              )}

              {goalError && <p role='alert' className='mt-2 text-[11px] text-destructive'>{goalError}</p>}
            </div>

            <form
              className='shrink-0 border-t border-border p-3'
              onSubmit={(event) => {
                event.preventDefault();
                void addGoal();
              }}
            >
              <label htmlFor='new-live-goal' className='text-[10px] font-semibold uppercase tracking-wide text-muted-foreground'>
                Add a milestone
              </label>
              <div className='mt-1.5 flex items-center gap-2'>
                <input
                  id='new-live-goal'
                  value={goalDraft}
                  onChange={(event) => setGoalDraft(event.target.value)}
                  placeholder='What needs to be true?'
                  maxLength={160}
                  className='min-w-0 flex-1 rounded-md border border-border bg-background px-2.5 py-1.5 text-xs outline-none transition placeholder:text-muted-foreground focus:border-primary focus:ring-1 focus:ring-primary'
                />
                <button
                  type='submit'
                  disabled={!goalDraft.trim() || goalBusyId === 'new'}
                  aria-label='Add goal'
                  className='flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-primary text-primary-foreground transition hover:opacity-90 disabled:opacity-50'
                >
                  {goalBusyId === 'new'
                    ? <Loader2 className='h-3.5 w-3.5 animate-spin' aria-hidden='true' />
                    : <Plus className='h-3.5 w-3.5' aria-hidden='true' />}
                </button>
              </div>
            </form>
          </Card>
        )}

        {squadsOpen && selected && (detail?.squads.length ?? 0) > 0 && (
          <Card className='fixed inset-4 z-40 flex min-h-0 flex-col overflow-hidden p-0 shadow-xl lg:static lg:z-auto lg:w-80 lg:shadow-none'>
            <div className='shrink-0 border-b border-border px-3 py-2'>
              <div className='flex items-center justify-between'>
                <div className='flex items-center gap-1.5'>
                  {(selectedSquadView || selectedWorker) && (
                    <button
                      type='button'
                      aria-label={selectedWorker ? 'Back to squad' : 'Back to all squads'}
                      onClick={() => {
                        if (selectedWorker) setSelectedWorkerId(null);
                        else setSelectedSquadId(null);
                      }}
                      className='rounded p-0.5 text-muted-foreground transition hover:bg-accent hover:text-foreground'
                    >
                      <ArrowLeft className='h-3.5 w-3.5' aria-hidden='true' />
                    </button>
                  )}
                  <p className='text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground'>
                    {selectedWorker ? 'Worker profile' : selectedSquadView ? 'Squad detail' : 'AI squads'}
                  </p>
                </div>
                {!selectedSquadView && !selectedWorker && (
                  <span className='text-[10px] text-muted-foreground'>{detail?.squads.length ?? 0} total</span>
                )}
                <button
                  type='button'
                  onClick={() => setSquadsOpen(false)}
                  aria-label='Collapse squad inspector'
                  className='rounded p-0.5 text-muted-foreground transition hover:bg-accent hover:text-foreground'
                >
                  <X className='h-3.5 w-3.5' aria-hidden='true' />
                </button>
              </div>
            </div>
            <div className='scrollbar-thin min-h-0 flex-1 overflow-y-auto p-3'>
              {selectedWorker ? (
                <div className='space-y-3'>
                  <div className='rounded-md border border-primary/30 bg-primary/5 p-3 text-center'>
                    <div className='mx-auto flex h-10 w-10 items-center justify-center rounded-full border border-primary/40 bg-primary/10 text-primary'>
                      <Bot className='h-5 w-5' aria-hidden='true' />
                    </div>
                    <p className='mt-2 text-sm font-semibold'>
                      {String(selectedWorker.profile.role?.name ?? selectedWorker.item.assigned_role_id ?? 'Unassigned worker')}
                    </p>
                    <p className='mt-0.5 text-[10px] uppercase tracking-wide text-muted-foreground'>
                      {String(selectedWorker.profile.role?.role_tier ?? 'worker')} · {String(selectedWorker.item.status ?? 'queued')}
                    </p>
                  </div>

                  <div className='grid grid-cols-2 gap-2'>
                    <div className='rounded-md border border-border bg-muted/10 p-2'>
                      <p className='flex items-center gap-1 text-[10px] uppercase tracking-wide text-muted-foreground'>
                        <Cpu className='h-3 w-3' aria-hidden='true' /> Runtime
                      </p>
                      <p className='mt-1 text-xs font-medium'>{selectedWorker.profile.runtime || 'Not launched'}</p>
                    </div>
                    <div className='rounded-md border border-border bg-muted/10 p-2'>
                      <p className='flex items-center gap-1 text-[10px] uppercase tracking-wide text-muted-foreground'>
                        <Clock3 className='h-3 w-3' aria-hidden='true' /> In status
                      </p>
                      <p className='mt-1 font-mono text-xs'>
                        {elapsedSince(selectedWorker.profile.status_changed_at, clock)}
                      </p>
                    </div>
                  </div>

                  <section className='rounded-md border border-border bg-muted/10 p-2.5'>
                    <p className='text-[10px] font-semibold uppercase tracking-wide text-muted-foreground'>Job</p>
                    <p className='mt-1 text-xs font-medium'>{String(selectedWorker.item.title ?? 'Work item')}</p>
                    {Boolean(selectedWorker.item.instructions_md) && (
                      <p className='mt-1.5 whitespace-pre-wrap text-[11px] leading-relaxed text-muted-foreground'>
                        {String(selectedWorker.item.instructions_md)}
                      </p>
                    )}
                  </section>

                  <section className='rounded-md border border-border bg-muted/10 p-2.5'>
                    <p className='flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground'>
                      <Sparkles className='h-3 w-3' aria-hidden='true' /> Personality
                    </p>
                    <p className='mt-1 text-xs font-medium'>
                      {String(selectedWorker.profile.personality?.name ?? selectedWorker.item.personality_id ?? 'Balanced default')}
                    </p>
                    {Boolean(selectedWorker.profile.personality?.blurb) && (
                      <p className='mt-1 text-[11px] text-muted-foreground'>{String(selectedWorker.profile.personality?.blurb)}</p>
                    )}
                    {Array.isArray(selectedWorker.profile.personality?.traits) && (
                      <div className='mt-2 flex flex-wrap gap-1'>
                        {(selectedWorker.profile.personality.traits as unknown[]).map((trait) => (
                          <span key={String(trait)} className='rounded-full border border-border px-1.5 py-0.5 text-[9px] text-muted-foreground'>
                            {String(trait)}
                          </span>
                        ))}
                      </div>
                    )}
                  </section>

                  <section className='rounded-md border border-border bg-muted/10 p-2.5'>
                    <div className='flex items-center justify-between gap-2'>
                      <p className='text-[10px] font-semibold uppercase tracking-wide text-muted-foreground'>Tokens</p>
                      <span className='font-mono text-xs'>{selectedWorker.profile.token_usage.total_tokens.toLocaleString()}</span>
                    </div>
                    <div className='mt-1 grid grid-cols-2 gap-2 text-[10px] text-muted-foreground'>
                      <span>Input {selectedWorker.profile.token_usage.input_tokens.toLocaleString()}</span>
                      <span>Output {selectedWorker.profile.token_usage.output_tokens.toLocaleString()}</span>
                    </div>
                  </section>

                  <section className='rounded-md border border-border bg-muted/10 p-2.5 text-[10px] text-muted-foreground'>
                    <p>PTY session: <span className='font-mono text-foreground'>{selectedWorker.profile.pty_session_id ?? 'not started'}</span></p>
                    <p className='mt-1'>Live session: <span className='font-mono text-foreground'>
                      {!selectedWorker.profile.coordination_session
                        ? 'not registered'
                        : selectedWorker.profile.coordination_session.seq == null
                          // Workers are nested under their parent and no longer take an
                          // operator-facing number, so there is nothing to render as "#NNN".
                          ? 'nested under this session'
                          : `#${String(selectedWorker.profile.coordination_session.seq).padStart(3, '0')}`}
                    </span></p>
                    <p className='mt-1'>MCP scope: <span className='text-foreground'>
                      {Array.isArray(selectedWorker.profile.role?.mcp_server_ids)
                        ? `${(selectedWorker.profile.role?.mcp_server_ids as unknown[]).length} selected`
                        : 'all enabled servers'}
                    </span></p>
                  </section>
                </div>
              ) : selectedSquadView ? (
                <div className='space-y-3'>
                  <section className='rounded-md border border-primary/30 bg-primary/5 p-3'>
                    <div className='flex items-start justify-between gap-2'>
                      <div className='min-w-0'>
                        <p className='text-sm font-semibold'>{String(selectedSquadView.squad.name ?? 'Unnamed squad')}</p>
                        <p className='mt-0.5 text-[10px] uppercase tracking-wide text-muted-foreground'>
                          {String(selectedSquadView.squad.status ?? 'active')} · {selectedSquadView.work_items.length} workers
                        </p>
                      </div>
                      <div className='flex h-8 w-8 items-center justify-center rounded-full border border-primary/40 bg-primary/10 text-primary'>
                        <Users className='h-4 w-4' aria-hidden='true' />
                      </div>
                    </div>
                    {Boolean(selectedSquadView.squad.goal_md) && (
                      <p className='mt-2 text-[11px] leading-relaxed text-muted-foreground'>{String(selectedSquadView.squad.goal_md)}</p>
                    )}
                  </section>

                  <div className='flex items-center justify-center gap-1 py-1' aria-label='Squad worker topology'>
                    {selectedSquadView.worker_profiles.slice(0, 8).map((profile, index) => (
                      <div key={profile.work_item_id} className='flex items-center gap-1'>
                        {index > 0 && <span className='h-px w-2 bg-border' aria-hidden='true' />}
                        <span className='flex h-7 w-7 items-center justify-center rounded-full border border-border bg-muted/30' title={String(profile.role?.name ?? 'Worker')}>
                          {profile.role?.role_tier === 'boss' ? <Sparkles className='h-3.5 w-3.5 text-primary' /> : <Bot className='h-3.5 w-3.5 text-muted-foreground' />}
                        </span>
                      </div>
                    ))}
                  </div>

                  <div className='space-y-2'>
                    {selectedSquadView.work_items.map((item) => {
                      const profile = selectedSquadView.worker_profiles.find((candidate) => candidate.work_item_id === String(item.id));
                      return (
                        <button
                          key={String(item.id)}
                          type='button'
                          onClick={() => setSelectedWorkerId(String(item.id))}
                          className='flex w-full items-start gap-2 rounded-md border border-border bg-muted/10 p-2.5 text-left transition hover:border-primary/50 hover:bg-muted/20'
                        >
                          <span className={cn(
                            'mt-1 h-2 w-2 shrink-0 rounded-full',
                            item.status === 'running' ? 'animate-pulse bg-primary' :
                              item.status === 'blocked' ? 'bg-status-launching' :
                                item.status === 'completed' ? 'bg-status-launched' : 'bg-status-idle'
                          )} aria-hidden='true' />
                          <div className='min-w-0 flex-1'>
                            <p className='truncate text-xs font-medium'>{String(item.title ?? 'Work item')}</p>
                            <p className='mt-0.5 truncate text-[10px] text-muted-foreground'>
                              {String(profile?.role?.name ?? item.assigned_role_id ?? 'Unassigned')} · {String(item.status ?? 'queued')}
                            </p>
                            <p className='mt-0.5 truncate text-[10px] text-muted-foreground'>
                              {profile?.runtime ?? 'not launched'} · {String(profile?.personality?.name ?? item.personality_id ?? 'balanced')}
                            </p>
                          </div>
                          <ChevronRight className='mt-1 h-3.5 w-3.5 shrink-0 text-muted-foreground' aria-hidden='true' />
                        </button>
                      );
                    })}
                  </div>
                </div>
              ) : (detail?.squads.length ?? 0) === 0 ? (
                <div className='py-8 text-center'>
                  <Users className='mx-auto h-5 w-5 text-muted-foreground' aria-hidden='true' />
                  <p className='mt-2 text-xs font-medium'>No squad on this project yet</p>
                  <p className='mt-1 text-[11px] text-muted-foreground'>When this AI creates or launches one, its roles and work appear here live.</p>
                </div>
              ) : (
                <div className='space-y-3'>
                  {detail?.squads.map((view) => {
                    const name = String(view.squad.name ?? 'Unnamed squad');
                    const goal = String(view.squad.goal_md ?? '');
                    const status = String(view.squad.status ?? 'active');
                    const tokens = Number((view.token_usage as { total_tokens?: number }).total_tokens ?? 0);
                    return (
                      <button
                        key={String(view.squad.id)}
                        type='button'
                        onClick={() => setSelectedSquadId(String(view.squad.id))}
                        className='w-full rounded-md border border-border bg-muted/10 p-2.5 text-left transition hover:border-primary/50 hover:bg-muted/20'
                      >
                        <div className='flex items-start justify-between gap-2'>
                          <div className='min-w-0'>
                            <p className='truncate text-xs font-semibold'>{name}</p>
                            <p className='text-[10px] text-muted-foreground'>{status}{tokens ? ` · ${tokens.toLocaleString()} tokens` : ''}</p>
                          </div>
                          <Users className='h-4 w-4 shrink-0 text-primary' aria-hidden='true' />
                        </div>
                        {goal && <p className='mt-2 line-clamp-3 text-[11px] text-muted-foreground'>{goal}</p>}
                        <div className='mt-2 flex items-center justify-between text-[10px] text-muted-foreground'>
                          <span>{view.work_items.length} worker{view.work_items.length === 1 ? '' : 's'}</span>
                          <span className='inline-flex items-center gap-0.5 text-primary'>Explore <ChevronRight className='h-3 w-3' aria-hidden='true' /></span>
                        </div>
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          </Card>
        )}

        {previewOpen && canPreview && sessionProject && (
          <Card className='fixed inset-4 z-40 flex min-h-0 flex-col overflow-hidden p-0 shadow-xl lg:static lg:z-auto lg:w-[28rem] lg:shadow-none xl:w-[34rem]'>
            <AppPreview project={sessionProject} onClose={() => setPreviewOpen(false)} />
          </Card>
        )}
      </div>

      <Modal
        open={goalToDelete !== null}
        onClose={() => setGoalToDelete(null)}
        labelledBy='delete-live-goal-title'
        className='max-w-sm'
      >
        {goalToDelete && (
          <>
            <div>
              <p className='text-[10px] font-semibold uppercase tracking-wide text-muted-foreground'>Remove milestone</p>
              <h2 id='delete-live-goal-title' className='mt-1 text-lg font-semibold'>Remove this goal?</h2>
            </div>
            <p className='rounded-md border border-border bg-muted/10 p-3 text-sm'>{goalToDelete.title}</p>
            <p className='text-xs leading-relaxed text-muted-foreground'>
              This removes the goal from this session’s progress list. It does not delete the session or its activity history.
            </p>
            <div className='flex justify-end gap-2'>
              <Button type='button' variant='secondary' onClick={() => setGoalToDelete(null)}>Keep goal</Button>
              <Button
                type='button'
                variant='destructive'
                disabled={goalBusyId === goalToDelete.id}
                onClick={() => void confirmDeleteGoal()}
              >
                {goalBusyId === goalToDelete.id ? 'Removing…' : 'Remove goal'}
              </Button>
            </div>
          </>
        )}
      </Modal>

      <Modal
        open={statusHelp !== null}
        onClose={() => setStatusHelp(null)}
        labelledBy='live-status-help-title'
        className='max-w-md'
      >
        {statusHelp && (
          <>
            <div>
              <p className='text-[10px] font-semibold uppercase tracking-wide text-muted-foreground'>Status explained</p>
              <h2 id='live-status-help-title' className='mt-1 text-lg font-semibold'>{statusHelp.title}</h2>
              <p className='mt-1 font-mono text-[10px] text-muted-foreground'>{statusHelp.code}</p>
            </div>
            <section className='rounded-md border border-border bg-muted/10 p-3'>
              <p className='text-[10px] font-semibold uppercase tracking-wide text-muted-foreground'>What it means</p>
              <p className='mt-1 text-sm'>{statusHelp.meaning}</p>
            </section>
            <section className='rounded-md border border-border bg-muted/10 p-3'>
              <p className='text-[10px] font-semibold uppercase tracking-wide text-muted-foreground'>Why this session has it</p>
              <p className='mt-1 whitespace-pre-wrap text-sm'>{statusHelp.reason}</p>
            </section>
            {statusHelp.remedy && (
              <section className='rounded-md border border-primary/30 bg-primary/5 p-3'>
                <p className='text-[10px] font-semibold uppercase tracking-wide text-primary'>What you can do</p>
                <p className='mt-1 text-sm'>{statusHelp.remedy}</p>
              </section>
            )}
            <div className='flex justify-end'>
              <Button type='button' onClick={() => setStatusHelp(null)}>Got it</Button>
            </div>
          </>
        )}
      </Modal>
    </div>
  );
}
