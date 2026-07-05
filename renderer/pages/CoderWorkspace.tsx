import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Archive,
  Bot,
  ExternalLink,
  FolderKanban,
  Loader2,
  MessageSquare,
  MessageSquarePlus,
  PanelLeft,
  PanelRight,
  Pin,
  Play,
  Send,
  Sparkles,
  TerminalSquare,
  Trash2,
  Wand2,
} from 'lucide-react';

import type {
  CoderRun,
  CoderThread,
  CoderThreadDetail,
  CoderThreadSummary,
  CoderWorkspaceContext,
  CoderWorkspacePreferences,
  ServiceConnection,
} from '@shared/generated-types';
import { closeSession, getSession } from '@shared/pty-client';
import { useDaemon } from '@shared/daemon-context';
import { cn } from '@shared/utils';
import { formatLocal } from '../lib/format-time';
import { getServiceConnections } from '../lib/profile-client';
import {
  createCoderReviewPass,
  createProjectCoderThread,
  deleteCoderThread,
  dispatchCoderThreadMessage,
  getCoderThread,
  getCoderWorkspaceContext,
  getCoderWorkspacePreferences,
  launchCoderReviewPass,
  listProjectCoderThreads,
  patchCoderThread,
  patchCoderWorkspacePreferences,
  type CoderThreadUpdateInput,
} from '../lib/coder-workspace-client';
import { PageHeader } from '../components/PageHeader';
import { FilesPanel } from '../components/FilesPanel';
import { ProjectRecordsSection } from '../components/ProjectRecordsSection';
import { SessionsPage as LegacySessionsPage } from './Sessions';
import { Badge } from '../components/ui/badge';
import { Button } from '../components/ui/button';
import { Card } from '../components/ui/card';
import { Input } from '../components/ui/input';
import { Modal } from '../components/ui/modal';

type RuntimeId = 'codex' | 'claude' | 'copilot';
type ReviewPresetId = 'general' | 'ux' | 'qa' | 'token-efficiency' | 'judge';
type ContextTab = 'context' | 'files' | 'records' | 'reviews' | 'terminal';

interface RuntimeOption {
  id: RuntimeId;
  label: string;
  provider: string;
  model: string;
  connectionProvider: string;
}

interface ReviewPreset {
  id: ReviewPresetId;
  label: string;
  title: string;
  summary: string;
  reason: string;
  focusPoints: string[];
}

const RUNTIME_OPTIONS: RuntimeOption[] = [
  {
    id: 'codex',
    label: 'Codex',
    provider: 'openai',
    model: 'codex',
    connectionProvider: 'openai-codex',
  },
  {
    id: 'claude',
    label: 'Claude',
    provider: 'anthropic',
    model: 'claude-code',
    connectionProvider: 'claude-code',
  },
  {
    id: 'copilot',
    label: 'Copilot',
    provider: 'github',
    model: 'copilot',
    connectionProvider: 'github-copilot',
  },
];

const REVIEW_PRESETS: ReviewPreset[] = [
  {
    id: 'general',
    label: 'General review',
    title: 'General review',
    summary: 'Review the latest direction, implementation risks, and missing tests.',
    reason: 'A second set of eyes can catch regressions before the main thread hardens the change.',
    focusPoints: ['Implementation risks', 'Missing tests', 'Next best step'],
  },
  {
    id: 'ux',
    label: 'UX pass',
    title: 'UX pass',
    summary: 'Audit clarity, hierarchy, responsiveness, interaction quality, and provenance risk.',
    reason: 'This thread touched user-facing work and needs a targeted UX pass before escalating further.',
    focusPoints: ['Hierarchy and clarity', 'Responsive friction', 'Originality and provenance cues'],
  },
  {
    id: 'qa',
    label: 'QA pass',
    title: 'QA pass',
    summary: 'Hunt for bugs, regressions, verification gaps, and missing coverage.',
    reason: 'Risk is high enough that a concrete bug-hunt is cheaper than discovering failures later.',
    focusPoints: ['Behavior regressions', 'Missing verification', 'Runtime or contract risk'],
  },
  {
    id: 'token-efficiency',
    label: 'Token efficiency',
    title: 'Token-efficiency pass',
    summary: 'Judge whether the loop is spending more tokens than the task risk justifies.',
    reason: 'We want the cheapest next pass that preserves quality, not an automatic full rebuild.',
    focusPoints: ['Cheaper next step', 'Escalation threshold', 'Avoidable overhead'],
  },
  {
    id: 'judge',
    label: 'Judge pass',
    title: 'Judge pass',
    summary: 'Judge the current result across quality, evidence, and token-cost tradeoffs.',
    reason: 'The thread needs an explicit winner or escalation decision before more work is spent.',
    focusPoints: ['Quality tradeoffs', 'Evidence strength', 'Escalate or stop'],
  },
];

const TEXT_DECODER = new TextDecoder();

function canonicalRuntimeId(value: string | null | undefined): RuntimeId {
  const normalized = (value ?? '').trim().toLowerCase();
  if (normalized === 'claude' || normalized === 'claude-code') return 'claude';
  if (normalized === 'copilot' || normalized === 'github-copilot') return 'copilot';
  return 'codex';
}

function runtimeOptionFor(value: string | null | undefined): RuntimeOption {
  const id = canonicalRuntimeId(value);
  return RUNTIME_OPTIONS.find((option) => option.id === id) ?? RUNTIME_OPTIONS[0];
}

function decodeBase64Text(value: string): string {
  try {
    const binary = window.atob(value);
    const bytes = Uint8Array.from(binary, (char) => char.charCodeAt(0));
    return TEXT_DECODER.decode(bytes);
  } catch {
    return '';
  }
}

function metadataString(source: Record<string, unknown> | null | undefined, key: string): string | null {
  const value = source?.[key];
  return typeof value === 'string' && value.trim().length > 0 ? value : null;
}

function connectionStatus(
  option: RuntimeOption,
  connections: ServiceConnection[]
): { label: string; tone: string } {
  const connection = connections.find((item) => item.provider === option.connectionProvider);
  if (!connection) return { label: 'unknown', tone: 'border-border text-muted-foreground' };
  if (connection.status === 'connected' || connection.status === 'ready') {
    return { label: 'ready', tone: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300' };
  }
  if (connection.status === 'error') {
    return { label: 'attention', tone: 'border-rose-500/30 bg-rose-500/10 text-rose-300' };
  }
  return { label: connection.status, tone: 'border-amber-500/30 bg-amber-500/10 text-amber-300' };
}

export interface CoderWorkspacePageProps {
  initialSessionId?: string | null;
  onConsumedInitial?: () => void;
  headerless?: boolean;
}

export function CoderWorkspacePage({
  initialSessionId,
  onConsumedInitial,
  headerless = false,
}: CoderWorkspacePageProps): JSX.Element {
  const { projects, recentEvents } = useDaemon();
  const [threadsByProject, setThreadsByProject] = useState<Record<string, CoderThreadSummary[]>>({});
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const [selectedThreadId, setSelectedThreadId] = useState<string | null>(null);
  const [detail, setDetail] = useState<CoderThreadDetail | null>(null);
  const [context, setContext] = useState<CoderWorkspaceContext | null>(null);
  const [preferences, setPreferences] = useState<CoderWorkspacePreferences | null>(null);
  const [connections, setConnections] = useState<ServiceConnection[]>([]);
  const [draft, setDraft] = useState('');
  const [search, setSearch] = useState('');
  const [runtimeId, setRuntimeId] = useState<RuntimeId>('codex');
  const [contextTab, setContextTab] = useState<ContextTab>('context');
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [mobileRailOpen, setMobileRailOpen] = useState(false);
  const [mobileContextOpen, setMobileContextOpen] = useState(false);
  const [legacyOpen, setLegacyOpen] = useState(false);
  const [legacySessionId, setLegacySessionId] = useState<string | null>(null);
  const [legacyNonce, setLegacyNonce] = useState(0);
  const lastThreadEventIdRef = useRef(0);

  const sortedProjects = useMemo(() => {
    return [...projects].sort((a, b) => {
      if (a.pinned !== b.pinned) return a.pinned ? -1 : 1;
      return a.name.localeCompare(b.name);
    });
  }, [projects]);

  const selectedProject = useMemo(
    () => sortedProjects.find((project) => project.id === selectedProjectId) ?? null,
    [selectedProjectId, sortedProjects]
  );

  const selectedThreadSummary = useMemo(() => {
    if (!selectedProjectId || !selectedThreadId) return null;
    return (threadsByProject[selectedProjectId] ?? []).find(
      (item) => item.thread.id === selectedThreadId
    ) ?? null;
  }, [selectedProjectId, selectedThreadId, threadsByProject]);

  const runMap = useMemo(() => {
    const map = new Map<string, CoderRun>();
    for (const run of detail?.linked_runs ?? []) map.set(run.id, run);
    return map;
  }, [detail]);

  const activeSessionIds = useMemo(
    () =>
      new Set(
        (detail?.linked_runs ?? [])
          .map((run) => run.pty_session_id)
          .filter((value): value is string => Boolean(value))
      ),
    [detail]
  );

  const visibleProjects = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (!query) return sortedProjects;
    return sortedProjects.filter((project) => {
      const threads = threadsByProject[project.id] ?? [];
      return (
        project.name.toLowerCase().includes(query) ||
        project.path.toLowerCase().includes(query) ||
        threads.some(
          (summary) =>
            summary.thread.title.toLowerCase().includes(query) ||
            summary.last_message_preview.toLowerCase().includes(query)
        )
      );
    });
  }, [search, sortedProjects, threadsByProject]);

  const availableTabs: ContextTab[] = preferences?.advanced_terminal_enabled
    ? ['context', 'files', 'records', 'reviews', 'terminal']
    : ['context', 'files', 'records', 'reviews'];

  const latestRunningRun = useMemo(
    () =>
      (detail?.linked_runs ?? []).find(
        (run) => run.status === 'running' && !!run.pty_session_id
      ) ?? null,
    [detail]
  );

  const refreshConnections = useCallback(async () => {
    try {
      setConnections(await getServiceConnections());
    } catch {
      /* keep the workspace usable even if readiness fails */
    }
  }, []);

  const refreshPreferences = useCallback(async () => {
    try {
      setPreferences(await getCoderWorkspacePreferences());
    } catch {
      /* handled elsewhere if the user toggles */
    }
  }, []);

  const refreshThreads = useCallback(async () => {
    const entries = await Promise.all(
      sortedProjects.map(async (project) => {
        const threads = await listProjectCoderThreads(project.id);
        return [project.id, threads] as const;
      })
    );
    setThreadsByProject(Object.fromEntries(entries));
  }, [sortedProjects]);

  const refreshThreadState = useCallback(async (threadId: string) => {
    const [threadDetail, threadContext] = await Promise.all([
      getCoderThread(threadId),
      getCoderWorkspaceContext(threadId),
    ]);
    setDetail(threadDetail);
    setContext(threadContext);
    setRuntimeId(canonicalRuntimeId(threadDetail.thread.active_runtime_id));
  }, []);

  useEffect(() => {
    void refreshConnections();
    void refreshPreferences();
  }, [refreshConnections, refreshPreferences]);

  useEffect(() => {
    if (sortedProjects.length === 0) {
      setSelectedProjectId(null);
      setSelectedThreadId(null);
      setDetail(null);
      setContext(null);
      return;
    }
    if (!selectedProjectId || !sortedProjects.some((project) => project.id === selectedProjectId)) {
      setSelectedProjectId(sortedProjects[0]?.id ?? null);
    }
  }, [selectedProjectId, sortedProjects]);

  useEffect(() => {
    if (sortedProjects.length === 0) return;
    void refreshThreads().catch((err) => {
      setError((err as Error).message || 'Could not load thread list.');
    });
  }, [refreshThreads, sortedProjects.length]);

  useEffect(() => {
    if (!selectedProjectId) return;
    const threads = threadsByProject[selectedProjectId] ?? [];
    if (selectedThreadId && threads.some((summary) => summary.thread.id === selectedThreadId)) {
      return;
    }
    setSelectedThreadId(threads[0]?.thread.id ?? null);
  }, [selectedProjectId, selectedThreadId, threadsByProject]);

  useEffect(() => {
    if (!selectedThreadId) {
      setDetail(null);
      setContext(null);
      return;
    }
    void refreshThreadState(selectedThreadId).catch((err) => {
      setError((err as Error).message || 'Could not load the selected thread.');
    });
  }, [refreshThreadState, selectedThreadId]);

  useEffect(() => {
    if (!initialSessionId) return;
    setLegacySessionId(initialSessionId);
    setLegacyOpen(true);
    setLegacyNonce((value) => value + 1);
    onConsumedInitial?.();
  }, [initialSessionId, onConsumedInitial]);

  useEffect(() => {
    if (!selectedThreadId || activeSessionIds.size === 0) return;
    const freshEvents = recentEvents
      .filter((event) => event.id > lastThreadEventIdRef.current)
      .sort((a, b) => a.id - b.id);
    if (freshEvents.length === 0) return;
    lastThreadEventIdRef.current = Math.max(
      lastThreadEventIdRef.current,
      ...freshEvents.map((event) => event.id)
    );
    const relevant = freshEvents.some((event) => {
      if (
        event.name !== 'v1.pty.session_exited' &&
        event.name !== 'v1.pty.session_finalized'
      ) {
        return false;
      }
      const payload = (event.payload ?? {}) as { session_id?: string };
      return activeSessionIds.has(String(payload.session_id ?? ''));
    });
    if (!relevant) return;
    void Promise.all([refreshThreadState(selectedThreadId), refreshThreads()]).catch(() => undefined);
  }, [activeSessionIds, recentEvents, refreshThreadState, refreshThreads, selectedThreadId]);

  const selectProject = (projectId: string): void => {
    setSelectedProjectId(projectId);
    setMobileRailOpen(false);
  };

  const selectThread = (threadId: string): void => {
    setSelectedThreadId(threadId);
    setMobileRailOpen(false);
  };

  async function createThread(projectId: string): Promise<CoderThread> {
    const runtime = runtimeOptionFor(runtimeId);
    const created = await createProjectCoderThread(projectId, {
      title: 'New thread',
      active_runtime_id: runtime.id,
      active_provider: runtime.provider,
      active_model: runtime.model,
      workspace_context_mode: 'project',
    });
    setSelectedProjectId(projectId);
    setSelectedThreadId(created.id);
    await refreshThreads();
    await refreshThreadState(created.id);
    return created;
  }

  async function updateThread(
    threadId: string,
    patch: CoderThreadUpdateInput
  ): Promise<void> {
    await patchCoderThread(threadId, patch);
    await refreshThreads();
    if (selectedThreadId === threadId) {
      await refreshThreadState(threadId);
    }
  }

  async function handleRenameThread(summary: CoderThreadSummary): Promise<void> {
    const nextTitle = window.prompt('Rename thread', summary.thread.title)?.trim();
    if (!nextTitle || nextTitle === summary.thread.title) return;
    setBusy(`rename:${summary.thread.id}`);
    setError(null);
    try {
      await updateThread(summary.thread.id, { title: nextTitle });
    } catch (err) {
      setError((err as Error).message || 'Could not rename the thread.');
    } finally {
      setBusy(null);
    }
  }

  async function handleDeleteThread(summary: CoderThreadSummary): Promise<void> {
    if (!window.confirm(`Delete "${summary.thread.title}"?`)) return;
    setBusy(`delete:${summary.thread.id}`);
    setError(null);
    try {
      await deleteCoderThread(summary.thread.id);
      if (selectedThreadId === summary.thread.id) {
        setSelectedThreadId(null);
      }
      await refreshThreads();
    } catch (err) {
      setError((err as Error).message || 'Could not delete the thread.');
    } finally {
      setBusy(null);
    }
  }

  async function handleSend(): Promise<void> {
    const prompt = draft.trim();
    if (!prompt) return;
    const projectId = selectedProjectId ?? sortedProjects[0]?.id ?? null;
    if (!projectId) {
      setError('Add a project in Synapse first so the workspace has somewhere to anchor the thread.');
      return;
    }
    setBusy('send');
    setError(null);
    try {
      const runtime = runtimeOptionFor(runtimeId);
      const threadId =
        selectedThreadId ??
        (await createProjectCoderThread(projectId, {
          title: 'New thread',
          active_runtime_id: runtime.id,
          active_provider: runtime.provider,
          active_model: runtime.model,
          workspace_context_mode: 'project',
        })).id;
      setSelectedProjectId(projectId);
      setSelectedThreadId(threadId);
      const dispatched = await dispatchCoderThreadMessage(threadId, {
        content_md: prompt,
        runtime_id: runtime.id,
        provider: runtime.provider,
        model: runtime.model,
      });
      setDraft('');
      setDetail(dispatched.detail);
      setRuntimeId(runtime.id);
      await Promise.all([refreshThreads(), refreshThreadState(threadId)]);
    } catch (err) {
      setError((err as Error).message || 'Could not send the prompt.');
    } finally {
      setBusy(null);
    }
  }

  async function handleQuickReview(runtime: RuntimeOption, preset: ReviewPreset = REVIEW_PRESETS[0]!): Promise<void> {
    if (!selectedThreadId) {
      setError('Create or select a thread before launching a review pass.');
      return;
    }
    setBusy(`review:${runtime.id}:${preset.id}`);
    setError(null);
    try {
      const review = await createCoderReviewPass(selectedThreadId, {
        requested_runtime_id: runtime.id,
        requested_provider: runtime.provider,
        requested_model: runtime.model,
        title: `${runtime.label} ${preset.title}`,
        summary_md: preset.summary,
        metadata: {
          preset_id: preset.id,
          preset_label: preset.label,
          review_kind: preset.id,
          reason: preset.reason,
          focus_points: preset.focusPoints,
          escalation_policy: 'cheap-first-targeted-review',
        },
      });
      const launched = await launchCoderReviewPass(selectedThreadId, review.id, {
        runtime_id: runtime.id,
        provider: runtime.provider,
        model: runtime.model,
        metadata: {
          preset_id: preset.id,
          preset_label: preset.label,
          review_kind: preset.id,
          reason: preset.reason,
          focus_points: preset.focusPoints,
          escalation_policy: 'cheap-first-targeted-review',
        },
      });
      setDetail(launched.detail);
      await Promise.all([refreshThreads(), refreshThreadState(selectedThreadId)]);
    } catch (err) {
      setError((err as Error).message || 'Could not launch the review pass.');
    } finally {
      setBusy(null);
    }
  }

  async function handleStopRun(run: CoderRun): Promise<void> {
    if (!run.pty_session_id) return;
    setBusy(`stop:${run.id}`);
    setError(null);
    try {
      await closeSession(run.pty_session_id);
      if (selectedThreadId) {
        await Promise.all([refreshThreads(), refreshThreadState(selectedThreadId)]);
      }
    } catch (err) {
      setError((err as Error).message || 'Could not stop the linked runtime session.');
    } finally {
      setBusy(null);
    }
  }

  async function handleToggleAdvancedTerminal(enabled: boolean): Promise<void> {
    setBusy('prefs');
    setError(null);
    try {
      const next = await patchCoderWorkspacePreferences({
        advanced_terminal_enabled: enabled,
      });
      setPreferences(next);
      if (!enabled && contextTab === 'terminal') setContextTab('context');
    } catch (err) {
      setError((err as Error).message || 'Could not update terminal preferences.');
    } finally {
      setBusy(null);
    }
  }

  function openLegacy(sessionId: string | null = null): void {
    setLegacySessionId(sessionId);
    setLegacyNonce((value) => value + 1);
    setLegacyOpen(true);
  }

  const header = headerless ? null : (
    <PageHeader
      title='Coder Workspace'
      subtitle='A Codex-style project-and-thread shell for Codex, Claude, and Copilot, with Synapse files, records, reviews, and legacy PTY access still available when you want it.'
    />
  );

  return (
    <div className='flex h-full flex-col gap-4'>
      {header}

      <div className='flex flex-wrap items-center gap-2 lg:hidden'>
        <Button type='button' variant='outline' size='sm' onClick={() => setMobileRailOpen(true)}>
          <PanelLeft className='h-4 w-4' /> Projects
        </Button>
        <Button
          type='button'
          variant='outline'
          size='sm'
          disabled={!selectedThreadId}
          onClick={() => setMobileContextOpen(true)}
        >
          <PanelRight className='h-4 w-4' /> Context
        </Button>
        {preferences?.advanced_terminal_enabled && (
          <Button type='button' variant='outline' size='sm' onClick={() => openLegacy()}>
            <TerminalSquare className='h-4 w-4' /> Terminal
          </Button>
        )}
      </div>

      {error && (
        <Card className='border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive'>
          {error}
        </Card>
      )}

      <div className='grid min-h-[72vh] gap-4 lg:grid-cols-[280px_minmax(0,1fr)_340px]'>
        <div className='hidden min-h-0 lg:block'>
          <ProjectThreadRail
            projects={visibleProjects}
            threadsByProject={threadsByProject}
            selectedProjectId={selectedProjectId}
            selectedThreadId={selectedThreadId}
            search={search}
            onSearchChange={setSearch}
            onSelectProject={selectProject}
            onSelectThread={selectThread}
            onCreateThread={createThread}
            onRenameThread={handleRenameThread}
            onDeleteThread={handleDeleteThread}
            onTogglePin={(summary) =>
              updateThread(summary.thread.id, { pinned: !summary.thread.pinned })
            }
            onToggleArchive={(summary) =>
              updateThread(summary.thread.id, {
                archived: !summary.thread.archived,
                status: summary.thread.archived ? 'active' : 'archived',
              })
            }
            busyKey={busy}
          />
        </div>

        <Card className='flex min-h-0 flex-col overflow-hidden'>
          <div className='border-b border-border px-4 py-4'>
            <div className='flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between'>
              <div className='min-w-0'>
                <p className='text-xs font-semibold uppercase tracking-[0.18em] text-primary/85'>
                  {selectedProject?.name ?? 'No project selected'}
                </p>
                <h2 className='truncate text-xl font-semibold tracking-tight'>
                  {detail?.thread.title ?? 'Coder Workspace'}
                </h2>
                <p className='mt-1 text-sm text-muted-foreground'>
                  {selectedProject
                    ? `Working in ${selectedProject.path}`
                    : 'Pick a project on the left to start a thread.'}
                </p>
              </div>
              <div className='flex flex-wrap items-center gap-2'>
                <RuntimePicker
                  value={runtimeId}
                  connections={connections}
                  busy={busy === 'send'}
                  onChange={setRuntimeId}
                />
                <Button
                  type='button'
                  variant='outline'
                  size='sm'
                  disabled={!selectedProjectId || busy === 'new-thread'}
                  onClick={() => {
                    if (!selectedProjectId) return;
                    setBusy('new-thread');
                    void createThread(selectedProjectId)
                      .catch((err) =>
                        setError((err as Error).message || 'Could not create a new thread.')
                      )
                      .finally(() => setBusy(null));
                  }}
                >
                  <MessageSquarePlus className='h-4 w-4' /> New thread
                </Button>
                <Button
                  type='button'
                  variant='outline'
                  size='sm'
                  disabled={busy === 'prefs'}
                  onClick={() =>
                    void handleToggleAdvancedTerminal(
                      !(preferences?.advanced_terminal_enabled ?? false)
                    )
                  }
                >
                  <TerminalSquare className='h-4 w-4' />
                  {preferences?.advanced_terminal_enabled ? 'Hide terminal tools' : 'Enable terminal tools'}
                </Button>
                {preferences?.advanced_terminal_enabled && (
                  <Button type='button' variant='outline' size='sm' onClick={() => openLegacy()}>
                    <ExternalLink className='h-4 w-4' /> Legacy cockpit
                  </Button>
                )}
              </div>
            </div>
            <div className='mt-3 flex flex-wrap items-center gap-2'>
              {RUNTIME_OPTIONS.map((option) => {
                const status = connectionStatus(option, connections);
                return (
                  <Badge key={option.id} className={cn('border text-[11px]', status.tone)}>
                    {option.label}: {status.label}
                  </Badge>
                );
              })}
              {latestRunningRun && (
                <Badge variant='outline' className='text-[11px]'>
                  Live run: {runtimeOptionFor(latestRunningRun.runtime_id).label}
                </Badge>
              )}
            </div>
          </div>

          <div className='flex min-h-0 flex-1 flex-col'>
            <div className='min-h-0 flex-1 overflow-y-auto px-4 py-4'>
              {!detail ? (
                <EmptyWorkspace
                  selectedProject={selectedProject}
                  onCreateThread={() => {
                    if (!selectedProjectId) return;
                    setBusy('new-thread');
                    void createThread(selectedProjectId)
                      .catch((err) =>
                        setError((err as Error).message || 'Could not create a new thread.')
                      )
                      .finally(() => setBusy(null));
                  }}
                />
              ) : detail.messages.length === 0 ? (
                <Card className='border-dashed p-8 text-center text-sm text-muted-foreground'>
                  <MessageSquare className='mx-auto mb-3 h-8 w-8 text-primary/70' />
                  Send the first prompt to start this thread. The linked runtime session will launch in
                  the project folder and the workspace will keep the thread, files, reviews, and terminal
                  access tied together.
                </Card>
              ) : (
                <div className='flex flex-col gap-4'>
                  {detail.messages.map((message) => {
                    const run = message.coder_run_id ? runMap.get(message.coder_run_id) ?? null : null;
                    return (
                      <div key={message.id} className='flex flex-col gap-2'>
                        <MessageBubble message={message} />
                        {run && (
                          <RunOutputCard
                            run={run}
                            onOpenTerminal={(sessionId) => openLegacy(sessionId)}
                            onStop={(linkedRun) => void handleStopRun(linkedRun)}
                          />
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            <div className='border-t border-border bg-card/95 px-4 py-4 backdrop-blur'>
              <div className='rounded-xl border border-border bg-secondary/20 p-3'>
                <textarea
                  value={draft}
                  onChange={(event) => setDraft(event.target.value)}
                  rows={4}
                  placeholder='Tell the runtime what to build, change, or review...'
                  className='w-full resize-none bg-transparent text-sm outline-none placeholder:text-muted-foreground'
                />
                <div className='mt-3 flex flex-wrap items-center justify-between gap-2'>
                  <p className='text-xs text-muted-foreground'>
                    Thread runtime: <span className='font-medium text-foreground'>{runtimeOptionFor(runtimeId).label}</span>
                  </p>
                  <div className='flex flex-wrap items-center gap-2'>
                    {latestRunningRun && latestRunningRun.pty_session_id && (
                      <Button
                        type='button'
                        variant='outline'
                        size='sm'
                        disabled={busy === `stop:${latestRunningRun.id}`}
                        onClick={() => void handleStopRun(latestRunningRun)}
                      >
                        <TerminalSquare className='h-4 w-4' /> Stop live run
                      </Button>
                    )}
                    <Button
                      type='button'
                      size='sm'
                      disabled={busy === 'send' || !draft.trim() || projects.length === 0}
                      onClick={() => void handleSend()}
                    >
                      {busy === 'send' ? (
                        <Loader2 className='h-4 w-4 animate-spin' />
                      ) : (
                        <Send className='h-4 w-4' />
                      )}
                      Send prompt
                    </Button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </Card>

        <div className='hidden min-h-0 lg:block'>
          <WorkspaceContextPane
            detail={detail}
            context={context}
            selectedProject={selectedProject}
            selectedThreadSummary={selectedThreadSummary}
            selectedRuntime={runtimeOptionFor(detail?.thread.active_runtime_id ?? runtimeId)}
            contextTab={contextTab}
            availableTabs={availableTabs}
            preferences={preferences}
            connections={connections}
            busy={busy}
            onSelectTab={setContextTab}
            onToggleAdvancedTerminal={handleToggleAdvancedTerminal}
            onOpenLegacy={openLegacy}
            onQuickReview={(runtime, preset) => void handleQuickReview(runtime, preset)}
          />
        </div>
      </div>

      <Modal
        open={mobileRailOpen}
        onClose={() => setMobileRailOpen(false)}
        labelledBy='coder-workspace-projects'
        className='max-w-xl'
      >
        <h2 id='coder-workspace-projects' className='text-lg font-semibold'>
          Projects and threads
        </h2>
        <ProjectThreadRail
          projects={visibleProjects}
          threadsByProject={threadsByProject}
          selectedProjectId={selectedProjectId}
          selectedThreadId={selectedThreadId}
          search={search}
          onSearchChange={setSearch}
          onSelectProject={selectProject}
          onSelectThread={selectThread}
          onCreateThread={createThread}
          onRenameThread={handleRenameThread}
          onDeleteThread={handleDeleteThread}
          onTogglePin={(summary) =>
            updateThread(summary.thread.id, { pinned: !summary.thread.pinned })
          }
          onToggleArchive={(summary) =>
            updateThread(summary.thread.id, {
              archived: !summary.thread.archived,
              status: summary.thread.archived ? 'active' : 'archived',
            })
          }
          busyKey={busy}
          compact
        />
      </Modal>

      <Modal
        open={mobileContextOpen}
        onClose={() => setMobileContextOpen(false)}
        labelledBy='coder-workspace-context'
        className='max-w-2xl'
      >
        <h2 id='coder-workspace-context' className='text-lg font-semibold'>
          Thread context
        </h2>
        <WorkspaceContextPane
          detail={detail}
          context={context}
          selectedProject={selectedProject}
          selectedThreadSummary={selectedThreadSummary}
          selectedRuntime={runtimeOptionFor(detail?.thread.active_runtime_id ?? runtimeId)}
          contextTab={contextTab}
          availableTabs={availableTabs}
          preferences={preferences}
          connections={connections}
          busy={busy}
          onSelectTab={setContextTab}
          onToggleAdvancedTerminal={handleToggleAdvancedTerminal}
          onOpenLegacy={openLegacy}
          onQuickReview={(runtime, preset) => void handleQuickReview(runtime, preset)}
        />
      </Modal>

      <Modal
        open={legacyOpen}
        onClose={() => setLegacyOpen(false)}
        labelledBy='legacy-sessions-title'
        className='max-w-7xl'
      >
        <div className='flex min-h-[80vh] flex-col gap-3 overflow-hidden'>
          <div className='flex items-start justify-between gap-4'>
            <div>
              <h2 id='legacy-sessions-title' className='text-lg font-semibold'>
                Legacy terminal cockpit
              </h2>
              <p className='text-sm text-muted-foreground'>
                The raw PTY surface stays available for power use, but the new workspace remains the default.
              </p>
            </div>
            <Button type='button' variant='outline' size='sm' onClick={() => setLegacyOpen(false)}>
              Close
            </Button>
          </div>
          <div className='min-h-0 flex-1 overflow-y-auto'>
            <LegacySessionsPage
              key={`${legacyNonce}:${legacySessionId ?? 'none'}`}
              headerless
              initialSessionId={legacySessionId}
            />
          </div>
        </div>
      </Modal>
    </div>
  );
}

function EmptyWorkspace({
  selectedProject,
  onCreateThread,
}: {
  selectedProject: { name: string } | null;
  onCreateThread: () => void;
}): JSX.Element {
  return (
    <Card className='border-dashed p-8 text-center text-sm text-muted-foreground'>
      <Sparkles className='mx-auto mb-3 h-8 w-8 text-primary/70' />
      <h3 className='text-base font-semibold text-foreground'>
        {selectedProject ? `Start a thread for ${selectedProject.name}` : 'Start by choosing a project'}
      </h3>
      <p className='mt-2'>
        Threads keep your prompts, runtime switches, review passes, and linked terminal sessions grouped under the same project.
      </p>
      {selectedProject && (
        <Button type='button' size='sm' className='mt-4' onClick={onCreateThread}>
          <MessageSquarePlus className='h-4 w-4' /> Create thread
        </Button>
      )}
    </Card>
  );
}

function ProjectThreadRail({
  projects,
  threadsByProject,
  selectedProjectId,
  selectedThreadId,
  search,
  onSearchChange,
  onSelectProject,
  onSelectThread,
  onCreateThread,
  onRenameThread,
  onDeleteThread,
  onTogglePin,
  onToggleArchive,
  busyKey,
  compact = false,
}: {
  projects: Array<{ id: string; name: string; path: string }>;
  threadsByProject: Record<string, CoderThreadSummary[]>;
  selectedProjectId: string | null;
  selectedThreadId: string | null;
  search: string;
  onSearchChange: (value: string) => void;
  onSelectProject: (projectId: string) => void;
  onSelectThread: (threadId: string) => void;
  onCreateThread: (projectId: string) => Promise<CoderThread>;
  onRenameThread: (summary: CoderThreadSummary) => Promise<void>;
  onDeleteThread: (summary: CoderThreadSummary) => Promise<void>;
  onTogglePin: (summary: CoderThreadSummary) => Promise<void>;
  onToggleArchive: (summary: CoderThreadSummary) => Promise<void>;
  busyKey: string | null;
  compact?: boolean;
}): JSX.Element {
  return (
    <Card className='flex h-full min-h-0 flex-col overflow-hidden'>
      <div className='border-b border-border px-4 py-4'>
        <div className='flex items-center justify-between gap-2'>
          <div>
            <p className='text-xs font-semibold uppercase tracking-[0.18em] text-primary/85'>
              Workspace
            </p>
            <h2 className='text-lg font-semibold'>Projects</h2>
          </div>
        </div>
        <Input
          value={search}
          onChange={(event) => onSearchChange(event.target.value)}
          placeholder='Search projects or threads'
          className='mt-3'
          aria-label='Search projects or threads'
        />
      </div>
      <div className='min-h-0 flex-1 overflow-y-auto p-3'>
        <div className='flex flex-col gap-3'>
          {projects.map((project) => {
            const active = project.id === selectedProjectId;
            const threads = threadsByProject[project.id] ?? [];
            return (
              <div key={project.id} className='rounded-xl border border-border/70 bg-secondary/15'>
                <button
                  type='button'
                  onClick={() => onSelectProject(project.id)}
                  className={cn(
                    'flex w-full items-start gap-3 rounded-xl px-3 py-3 text-left transition-colors',
                    active ? 'bg-accent/70' : 'hover:bg-accent/40'
                  )}
                >
                  <FolderKanban className='mt-0.5 h-4 w-4 text-primary' />
                  <div className='min-w-0 flex-1'>
                    <p className='truncate text-sm font-medium'>{project.name}</p>
                    <p className='truncate text-[11px] text-muted-foreground'>{project.path}</p>
                  </div>
                  <Badge variant='outline'>{threads.length}</Badge>
                </button>
                <div className='flex items-center justify-between px-3 pb-2'>
                  <p className='text-[11px] uppercase tracking-[0.16em] text-muted-foreground'>
                    Threads
                  </p>
                  <Button
                    type='button'
                    variant='ghost'
                    size='sm'
                    disabled={busyKey === `new:${project.id}`}
                    onClick={() => {
                      void onCreateThread(project.id);
                    }}
                  >
                    <MessageSquarePlus className='h-4 w-4' />
                  </Button>
                </div>
                {threads.length === 0 ? (
                  <p className='px-3 pb-3 text-xs text-muted-foreground'>
                    No threads yet. Start one from this project.
                  </p>
                ) : (
                  <div className='flex flex-col gap-1 px-2 pb-2'>
                    {threads.map((summary) => {
                      const thread = summary.thread;
                      const selected = thread.id === selectedThreadId;
                      return (
                        <div
                          key={thread.id}
                          className={cn(
                            'rounded-lg border px-2 py-2 transition-colors',
                            selected
                              ? 'border-primary/40 bg-primary/10'
                              : 'border-transparent hover:border-border hover:bg-accent/30'
                          )}
                        >
                          <button
                            type='button'
                            onClick={() => onSelectThread(thread.id)}
                            className='flex w-full flex-col items-start gap-1 text-left'
                          >
                            <div className='flex w-full items-center gap-2'>
                              <p className='min-w-0 flex-1 truncate text-sm font-medium'>
                                {thread.title}
                              </p>
                              {thread.pinned && <Pin className='h-3.5 w-3.5 text-primary' />}
                              {thread.archived && <Archive className='h-3.5 w-3.5 text-muted-foreground' />}
                            </div>
                            <p className='line-clamp-2 text-[11px] text-muted-foreground'>
                              {summary.last_message_preview || 'No messages yet'}
                            </p>
                            <div className='flex flex-wrap items-center gap-2 text-[10px] text-muted-foreground'>
                              <span>{summary.message_count} msg</span>
                              <span>{summary.run_count} run</span>
                              <span>{formatLocal(thread.updated_at, 'relative')}</span>
                            </div>
                          </button>
                          <div className='mt-2 flex flex-wrap items-center gap-1'>
                            <Button
                              type='button'
                              variant='ghost'
                              size='sm'
                              className='h-7 px-2'
                              onClick={() => {
                                void onRenameThread(summary);
                              }}
                            >
                              Rename
                            </Button>
                            <Button
                              type='button'
                              variant='ghost'
                              size='sm'
                              className='h-7 px-2'
                              onClick={() => {
                                void onTogglePin(summary);
                              }}
                            >
                              {thread.pinned ? 'Unpin' : 'Pin'}
                            </Button>
                            <Button
                              type='button'
                              variant='ghost'
                              size='sm'
                              className='h-7 px-2'
                              onClick={() => {
                                void onToggleArchive(summary);
                              }}
                            >
                              {thread.archived ? 'Restore' : 'Archive'}
                            </Button>
                            {!compact && (
                              <Button
                                type='button'
                                variant='ghost'
                                size='sm'
                                className='h-7 px-2 text-destructive hover:bg-destructive/10'
                                onClick={() => {
                                  void onDeleteThread(summary);
                                }}
                              >
                                <Trash2 className='h-3.5 w-3.5' />
                              </Button>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
          {projects.length === 0 && (
            <Card className='border-dashed p-6 text-center text-sm text-muted-foreground'>
              No projects yet. Add one in Apps first, then return here to create threads against it.
            </Card>
          )}
        </div>
      </div>
    </Card>
  );
}

function RuntimePicker({
  value,
  connections,
  busy,
  onChange,
}: {
  value: RuntimeId;
  connections: ServiceConnection[];
  busy: boolean;
  onChange: (value: RuntimeId) => void;
}): JSX.Element {
  return (
    <label className='flex items-center gap-2 rounded-lg border border-border bg-secondary/20 px-3 py-2 text-sm'>
      <Wand2 className='h-4 w-4 text-primary' />
      <span className='text-muted-foreground'>Runtime</span>
      <select
        value={value}
        disabled={busy}
        onChange={(event) => onChange(event.target.value as RuntimeId)}
        className='bg-transparent text-sm outline-none'
        aria-label='Active runtime'
      >
        {RUNTIME_OPTIONS.map((option) => {
          const status = connectionStatus(option, connections);
          return (
            <option key={option.id} value={option.id}>
              {option.label} ({status.label})
            </option>
          );
        })}
      </select>
    </label>
  );
}

function MessageBubble({
  message,
}: {
  message: CoderThreadDetail['messages'][number];
}): JSX.Element {
  const isUser = message.role === 'user';
  return (
    <div className={cn('flex', isUser ? 'justify-end' : 'justify-start')}>
      <div
        className={cn(
          'max-w-[85%] rounded-2xl px-4 py-3 text-sm shadow-sm',
          isUser
            ? 'bg-primary text-primary-foreground'
            : 'border border-border bg-secondary/20 text-foreground'
        )}
      >
        <div className='mb-1 flex items-center gap-2 text-[11px] uppercase tracking-[0.16em] opacity-80'>
          <span>{message.role}</span>
          {message.runtime_id && <span>{runtimeOptionFor(message.runtime_id).label}</span>}
          <span>{formatLocal(message.created_at, 'relative')}</span>
        </div>
        <div className='whitespace-pre-wrap leading-6'>{message.content_md}</div>
      </div>
    </div>
  );
}

function RunOutputCard({
  run,
  onOpenTerminal,
  onStop,
}: {
  run: CoderRun;
  onOpenTerminal: (sessionId: string | null) => void;
  onStop: (run: CoderRun) => void;
}): JSX.Element {
  const { recentEvents } = useDaemon();
  const [output, setOutput] = useState('');
  const [loading, setLoading] = useState(Boolean(run.pty_session_id));
  const [loadError, setLoadError] = useState<string | null>(null);
  const seenEventId = useRef(0);

  useEffect(() => {
    seenEventId.current = recentEvents.reduce(
      (max, event) => Math.max(max, event.id),
      0
    );
  }, [run.pty_session_id]);

  useEffect(() => {
    if (!run.pty_session_id) {
      setOutput('');
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setLoadError(null);
    void getSession(run.pty_session_id)
      .then((session) => {
        if (cancelled) return;
        setOutput(decodeBase64Text(session.scrollback));
        setLoading(false);
      })
      .catch((err) => {
        if (cancelled) return;
        setLoadError((err as Error).message || 'Could not read session output.');
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [run.pty_session_id]);

  useEffect(() => {
    if (!run.pty_session_id) return;
    const freshEvents = recentEvents
      .filter((event) => event.id > seenEventId.current)
      .sort((a, b) => a.id - b.id);
    if (freshEvents.length === 0) return;
    seenEventId.current = Math.max(
      seenEventId.current,
      ...freshEvents.map((event) => event.id)
    );
    for (const event of freshEvents) {
      if (event.name !== 'v1.pty.session_output') continue;
      const payload = (event.payload ?? {}) as { session_id?: string; data?: string };
      if (String(payload.session_id ?? '') !== run.pty_session_id) continue;
      const chunk = decodeBase64Text(String(payload.data ?? ''));
      if (!chunk) continue;
      setOutput((current) => current + chunk);
    }
  }, [recentEvents, run.pty_session_id]);

  const runtime = runtimeOptionFor(run.runtime_id);
  const runReason = metadataString(run.metadata as Record<string, unknown>, 'reason');
  const presetLabel = metadataString(run.metadata as Record<string, unknown>, 'preset_label');
  const benchmarkAttemptId = run.benchmark_attempt_id;
  const statusTone =
    run.status === 'completed'
      ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300'
      : run.status === 'failed' || run.status === 'crashed'
        ? 'border-rose-500/30 bg-rose-500/10 text-rose-300'
        : 'border-amber-500/30 bg-amber-500/10 text-amber-300';

  return (
    <Card className='ml-2 border-dashed p-3'>
      <div className='flex flex-wrap items-center justify-between gap-2'>
        <div className='flex min-w-0 items-center gap-2'>
          <Badge className={cn('border', statusTone)}>{run.status}</Badge>
          <p className='truncate text-sm font-medium'>
            {runtime.label} run
          </p>
          <span className='text-xs text-muted-foreground'>
            {formatLocal(run.started_at, 'relative')}
          </span>
        </div>
        <div className='flex flex-wrap items-center gap-2'>
          {run.pty_session_id && (
            <Button
              type='button'
              variant='outline'
              size='sm'
              onClick={() => onOpenTerminal(run.pty_session_id)}
            >
              <TerminalSquare className='h-4 w-4' /> Open terminal
            </Button>
          )}
          {run.pty_session_id && run.status === 'running' && (
            <Button type='button' variant='outline' size='sm' onClick={() => onStop(run)}>
              Stop
            </Button>
          )}
        </div>
      </div>
      <div className='mt-3 flex flex-wrap gap-2 text-[11px] text-muted-foreground'>
        {presetLabel && <Badge variant='outline'>{presetLabel}</Badge>}
        {benchmarkAttemptId && <Badge variant='outline'>Benchmark linked</Badge>}
        <Badge variant='outline'>{run.provider || 'unknown provider'}</Badge>
        <Badge variant='outline'>{run.workspace_overhead_bytes} context bytes</Badge>
      </div>
      {runReason && (
        <p className='mt-2 text-xs text-muted-foreground'>
          Why this pass ran: {runReason}
        </p>
      )}
      <div className='mt-3 rounded-xl border border-border bg-background/70 p-3 text-xs'>
        {loading ? (
          <div className='flex items-center gap-2 text-muted-foreground'>
            <Loader2 className='h-4 w-4 animate-spin' /> Waiting for runtime output...
          </div>
        ) : loadError && !output ? (
          <p className='text-muted-foreground'>{loadError}</p>
        ) : (
          <pre className='max-h-64 overflow-y-auto whitespace-pre-wrap break-words font-mono leading-5 text-foreground'>
            {output || 'The runtime session has been created. Open the terminal if you want the raw PTY view.'}
          </pre>
        )}
      </div>
    </Card>
  );
}

function WorkspaceContextPane({
  detail,
  context,
  selectedProject,
  selectedThreadSummary,
  selectedRuntime,
  contextTab,
  availableTabs,
  preferences,
  connections,
  busy,
  onSelectTab,
  onToggleAdvancedTerminal,
  onOpenLegacy,
  onQuickReview,
}: {
  detail: CoderThreadDetail | null;
  context: CoderWorkspaceContext | null;
  selectedProject: { id: string; name: string } | null;
  selectedThreadSummary: CoderThreadSummary | null;
  selectedRuntime: RuntimeOption;
  contextTab: ContextTab;
  availableTabs: ContextTab[];
  preferences: CoderWorkspacePreferences | null;
  connections: ServiceConnection[];
  busy: string | null;
  onSelectTab: (tab: ContextTab) => void;
  onToggleAdvancedTerminal: (enabled: boolean) => Promise<void>;
  onOpenLegacy: (sessionId?: string | null) => void;
  onQuickReview: (runtime: RuntimeOption, preset?: ReviewPreset) => void;
}): JSX.Element {
  return (
    <Card className='flex h-full min-h-0 flex-col overflow-hidden'>
      <div className='border-b border-border px-4 py-4'>
        <p className='text-xs font-semibold uppercase tracking-[0.18em] text-primary/85'>
          Context
        </p>
        <h2 className='text-lg font-semibold'>Thread tools</h2>
        <div className='mt-3 flex flex-wrap gap-2'>
          {availableTabs.map((tab) => (
            <button
              key={tab}
              type='button'
              onClick={() => onSelectTab(tab)}
              className={cn(
                'rounded-full border px-3 py-1 text-xs font-medium capitalize transition-colors',
                contextTab === tab
                  ? 'border-primary/40 bg-primary/10 text-foreground'
                  : 'border-border text-muted-foreground hover:text-foreground'
              )}
            >
              {tab}
            </button>
          ))}
        </div>
      </div>

      <div className='min-h-0 flex-1 overflow-y-auto p-4'>
        {contextTab === 'context' && (
          <div className='flex flex-col gap-4 text-sm'>
            <Card className='border-dashed p-4'>
              <p className='text-xs uppercase tracking-[0.16em] text-muted-foreground'>
                Active thread
              </p>
              <p className='mt-2 font-medium'>{detail?.thread.title ?? 'No thread selected'}</p>
              {selectedProject && (
                <p className='mt-1 text-xs text-muted-foreground'>{selectedProject.name}</p>
              )}
              {selectedThreadSummary && (
                <div className='mt-3 flex flex-wrap gap-2 text-xs text-muted-foreground'>
                  <Badge variant='outline'>{selectedThreadSummary.message_count} messages</Badge>
                  <Badge variant='outline'>{selectedThreadSummary.run_count} runs</Badge>
                  <Badge variant='outline'>{selectedThreadSummary.review_pass_count} reviews</Badge>
                </div>
              )}
            </Card>

            {selectedProject?.id === 'synapse-self' && (
              <Card className='border-dashed p-4'>
                <p className='font-medium'>Self-improvement cockpit</p>
                <p className='mt-1 text-xs text-muted-foreground'>
                  This project is the bundled Synapse self-workspace. Keep the loop explicit: improve, review, benchmark when needed, then record the result in project memory.
                </p>
                <div className='mt-3 flex flex-wrap gap-2 text-xs text-muted-foreground'>
                  <Badge variant='outline'>{detail?.thread.thread_kind ?? 'chat'} thread</Badge>
                  <Badge variant='outline'>{context?.records_summary.adrs ?? 0} ADRs visible</Badge>
                  <Badge variant='outline'>{context?.records_summary.backlog ?? 0} backlog items</Badge>
                  <Badge variant='outline'>{context?.files_count ?? 0} files in scope</Badge>
                </div>
              </Card>
            )}

            <Card className='border-dashed p-4'>
              <div className='flex items-center justify-between gap-3'>
                <div>
                  <p className='font-medium'>Advanced terminal</p>
                  <p className='mt-1 text-xs text-muted-foreground'>
                    Keep the raw PTY out of the way by default, but make it available when you need to inspect or steer the runtime directly.
                  </p>
                </div>
                <Button
                  type='button'
                  variant='outline'
                  size='sm'
                  disabled={busy === 'prefs'}
                  onClick={() =>
                    void onToggleAdvancedTerminal(!(preferences?.advanced_terminal_enabled ?? false))
                  }
                >
                  {preferences?.advanced_terminal_enabled ? 'Hide' : 'Enable'}
                </Button>
              </div>
              {preferences?.advanced_terminal_enabled && (
                <Button type='button' size='sm' className='mt-3' onClick={() => onOpenLegacy()}>
                  <ExternalLink className='h-4 w-4' /> Open legacy cockpit
                </Button>
              )}
            </Card>

            <Card className='border-dashed p-4'>
              <p className='font-medium'>Runtime switches</p>
              {detail?.runtime_switches.length ? (
                <div className='mt-3 flex flex-col gap-2'>
                  {detail.runtime_switches.map((item) => (
                    <div key={item.id} className='rounded-lg border border-border px-3 py-2 text-xs'>
                      <p className='font-medium'>
                        {runtimeOptionFor(item.from_runtime_id).label}
                        {' -> '}
                        {runtimeOptionFor(item.to_runtime_id).label}
                      </p>
                      <p className='mt-1 text-muted-foreground'>
                        {item.reason || 'Manual switch'} · {formatLocal(item.created_at, 'relative')}
                      </p>
                    </div>
                  ))}
                </div>
              ) : (
                <p className='mt-2 text-xs text-muted-foreground'>
                  No runtime switches yet.
                </p>
              )}
            </Card>
          </div>
        )}

        {contextTab === 'files' && (
          <div className='min-h-[360px]'>
            {selectedProject ? (
              <FilesPanel projectId={selectedProject.id} />
            ) : (
              <Card className='border-dashed p-6 text-sm text-muted-foreground'>
                Select a project to view its files.
              </Card>
            )}
          </div>
        )}

        {contextTab === 'records' && (
          <div className='min-h-[360px]'>
            {selectedProject ? (
              <ProjectRecordsSection projectId={selectedProject.id} />
            ) : (
              <Card className='border-dashed p-6 text-sm text-muted-foreground'>
                Select a project to view ADRs, backlog, and version history.
              </Card>
            )}
          </div>
        )}

        {contextTab === 'reviews' && (
          <div className='flex flex-col gap-4 text-sm'>
            <Card className='border-dashed p-4'>
              <p className='font-medium'>Sidecar reviewers</p>
              <p className='mt-1 text-xs text-muted-foreground'>
                Launch a separate AI runtime to critique the current thread without replacing the main runtime.
              </p>
              <div className='mt-3 flex flex-wrap gap-2'>
                {RUNTIME_OPTIONS.map((option) => {
                  const status = connectionStatus(option, connections);
                  return (
                    <Button
                      key={option.id}
                      type='button'
                      variant='outline'
                      size='sm'
                      disabled={busy === `review:${option.id}:general`}
                      onClick={() => onQuickReview(option, REVIEW_PRESETS[0]!)}
                    >
                      {busy === `review:${option.id}:general` ? (
                        <Loader2 className='h-4 w-4 animate-spin' />
                      ) : (
                        <Play className='h-4 w-4' />
                      )}
                      Review with {option.label} ({status.label})
                    </Button>
                  );
                })}
              </div>
            </Card>

            <Card className='border-dashed p-4'>
              <p className='font-medium'>Synapse UX Lab presets</p>
              <p className='mt-1 text-xs text-muted-foreground'>
                Start cheap with targeted review, then escalate only when the thread or benchmark evidence says it is worth it.
              </p>
              <div className='mt-3 flex flex-col gap-2'>
                {REVIEW_PRESETS.filter((preset) => preset.id !== 'general').map((preset) => (
                  <button
                    key={preset.id}
                    type='button'
                    disabled={busy === `review:${selectedRuntime.id}:${preset.id}`}
                    onClick={() => onQuickReview(selectedRuntime, preset)}
                    className='rounded-xl border border-border bg-secondary/20 px-3 py-3 text-left transition hover:border-primary/40 hover:bg-primary/5 disabled:cursor-not-allowed disabled:opacity-60'
                  >
                    <div className='flex items-center justify-between gap-3'>
                      <p className='font-medium'>{preset.label}</p>
                      {busy === `review:${selectedRuntime.id}:${preset.id}` ? (
                        <Loader2 className='h-4 w-4 animate-spin text-primary' />
                      ) : (
                        <Badge variant='outline'>{selectedRuntime.label}</Badge>
                      )}
                    </div>
                    <p className='mt-1 text-xs text-muted-foreground'>{preset.reason}</p>
                  </button>
                ))}
              </div>
            </Card>

            <Card className='border-dashed p-4'>
              <p className='font-medium'>Review passes</p>
              {detail?.review_passes.length ? (
                <div className='mt-3 flex flex-col gap-2'>
                  {detail.review_passes.map((reviewPass) => {
                    const run = reviewPass.coder_run_id
                      ? detail.linked_runs.find((item) => item.id === reviewPass.coder_run_id) ?? null
                      : null;
                    return (
                      <div key={reviewPass.id} className='rounded-lg border border-border px-3 py-3 text-xs'>
                        <div className='flex items-center justify-between gap-2'>
                          <p className='font-medium'>{reviewPass.title}</p>
                          <Badge variant='outline'>{reviewPass.status}</Badge>
                        </div>
                        <p className='mt-1 text-muted-foreground'>
                          {runtimeOptionFor(reviewPass.requested_runtime_id).label} · {formatLocal(reviewPass.created_at, 'relative')}
                        </p>
                        <div className='mt-2 flex flex-wrap gap-2 text-[11px] text-muted-foreground'>
                          {metadataString(reviewPass.metadata as Record<string, unknown>, 'preset_label') && (
                            <Badge variant='outline'>
                              {metadataString(reviewPass.metadata as Record<string, unknown>, 'preset_label')}
                            </Badge>
                          )}
                          {run?.benchmark_attempt_id && <Badge variant='outline'>Benchmark linked</Badge>}
                          {run && <Badge variant='outline'>{run.provider || 'unknown provider'}</Badge>}
                        </div>
                        {metadataString(reviewPass.metadata as Record<string, unknown>, 'reason') && (
                          <p className='mt-2 text-muted-foreground'>
                            Why this pass ran:{' '}
                            {metadataString(reviewPass.metadata as Record<string, unknown>, 'reason')}
                          </p>
                        )}
                        {reviewPass.summary_md && (
                          <p className='mt-2 whitespace-pre-wrap text-foreground'>{reviewPass.summary_md}</p>
                        )}
                        {run?.pty_session_id && preferences?.advanced_terminal_enabled && (
                          <Button
                            type='button'
                            variant='outline'
                            size='sm'
                            className='mt-3'
                            onClick={() => onOpenLegacy(run.pty_session_id)}
                          >
                            <TerminalSquare className='h-4 w-4' /> Open reviewer terminal
                          </Button>
                        )}
                      </div>
                    );
                  })}
                </div>
              ) : (
                <p className='mt-2 text-xs text-muted-foreground'>
                  No review passes yet.
                </p>
              )}
            </Card>

            {context && (
              <Card className='border-dashed p-4'>
                <p className='font-medium'>Workspace context snapshot</p>
                <div className='mt-3 grid grid-cols-3 gap-2 text-xs text-muted-foreground'>
                  <Badge variant='outline'>{context.files_count} files</Badge>
                  <Badge variant='outline'>{context.records_summary.adrs ?? 0} ADRs</Badge>
                  <Badge variant='outline'>{context.records_summary.backlog ?? 0} backlog</Badge>
                </div>
                <p className='mt-3 text-xs text-muted-foreground'>
                  Preferred loop: targeted reviewer first, stronger judge only when the risk or benchmark calls for it.
                </p>
              </Card>
            )}
          </div>
        )}

        {contextTab === 'terminal' && (
          <div className='flex flex-col gap-4 text-sm'>
            <Card className='border-dashed p-4'>
              <p className='font-medium'>Terminal tools are enabled</p>
              <p className='mt-1 text-xs text-muted-foreground'>
                Use the legacy cockpit when you want the full PTY, session tabs, squads, or manual shell steering.
              </p>
              <Button type='button' className='mt-3' size='sm' onClick={() => onOpenLegacy()}>
                <ExternalLink className='h-4 w-4' /> Open legacy cockpit
              </Button>
            </Card>
          </div>
        )}
      </div>
    </Card>
  );
}
