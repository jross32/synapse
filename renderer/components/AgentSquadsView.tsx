import { useEffect, useMemo, useState } from 'react';
import {
  Bot,
  CheckCircle2,
  ChevronRight,
  Loader2,
  Play,
  Plus,
  RefreshCcw,
  Rocket,
  Sparkles,
  Square,
  SquareTerminal,
  Users,
} from 'lucide-react';

import type {
  AgentRoleTemplate,
  AgentSquad,
  AgentSquadDetail,
  AgentWorkItem,
  AgentWorkItemStatus,
  Project,
} from '@shared/generated-types';
import {
  createAgentSquad,
  createAgentWorkItem,
  delegateAgentWorkItem,
  getAgentSquad,
  handoffAgentWorkItem,
  launchAgentWorkItem,
  listAgentRoleTemplates,
  listAgentSquads,
  patchAgentSquad,
  stopAgentSquad,
  updateAgentWorkItemStatus,
} from '@shared/agent-squads-client';
import { useDaemon } from '@shared/daemon-context';
import { formatLocal } from '@shared/format-time';
import { listProjects } from '@shared/projects-client';
import { cn } from '@shared/utils';
import { SessionTerminal } from './SessionTerminal';
import { Badge } from './ui/badge';
import { Button } from './ui/button';
import { Card } from './ui/card';
import { Input } from './ui/input';
import { SquadWizard } from './SquadWizard';

interface OpenTabRef {
  sessionId: string;
  argv: string[];
  scrollback: string | null;
  scrollbackLoaded: boolean;
}

interface AgentSquadsViewProps {
  tabs: OpenTabRef[];
  activeSessionId: string | null;
  onOpenTab: (sessionId: string, argv?: string[]) => Promise<void>;
  onCloseTab: (sessionId: string) => Promise<void>;
  onRestartTab: (sessionId: string) => Promise<void>;
}

type LoadState = 'idle' | 'loading' | 'ready';

const TEXTAREA_CLASS =
  'min-h-[110px] w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50';

function labelForArgv(argv: string[], fallback: string): string {
  const head = argv[0];
  if (!head) return fallback;
  const base = head.split(/[\\/]/).pop() ?? head;
  const stripped = base.replace(/\.(exe|cmd|bat|com)$/i, '');
  return stripped || head;
}

function statusTone(status: AgentWorkItemStatus | AgentSquad['status']): string {
  switch (status) {
    case 'running':
    case 'active':
      return 'border-emerald-500/25 bg-emerald-500/10 text-emerald-300';
    case 'handoff':
      return 'border-sky-500/25 bg-sky-500/10 text-sky-300';
    case 'blocked':
      return 'border-amber-500/25 bg-amber-500/10 text-amber-300';
    case 'completed':
      return 'border-primary/30 bg-primary/10 text-primary';
    case 'paused':
      return 'border-border bg-secondary text-muted-foreground';
    default:
      return 'border-border bg-secondary text-muted-foreground';
  }
}

export function AgentSquadsView({
  tabs,
  activeSessionId,
  onOpenTab,
  onCloseTab,
  onRestartTab,
}: AgentSquadsViewProps): JSX.Element {
  const { recentEvents } = useDaemon();
  const [projects, setProjects] = useState<Project[]>([]);
  const [roles, setRoles] = useState<AgentRoleTemplate[]>([]);
  const [squads, setSquads] = useState<AgentSquad[]>([]);
  const [wizardOpen, setWizardOpen] = useState(false);
  const [detail, setDetail] = useState<AgentSquadDetail | null>(null);
  const [selectedSquadId, setSelectedSquadId] = useState<string | null>(null);
  const [selectedWorkItemId, setSelectedWorkItemId] = useState<string | null>(null);
  const [loadState, setLoadState] = useState<LoadState>('loading');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const [squadForm, setSquadForm] = useState({
    project_id: '',
    name: '',
    goal_md: '',
    lead_role_id: 'planner',
  });
  const [workItemForm, setWorkItemForm] = useState({
    title: '',
    instructions_md: '',
    assigned_role_id: 'implementer',
    preferred_runtime: '',
  });
  const [delegateForm, setDelegateForm] = useState({
    title: '',
    instructions_md: '',
    assigned_role_id: 'reviewer',
    preferred_runtime: '',
  });
  const [launchRuntime, setLaunchRuntime] = useState('');
  const [handoffForm, setHandoffForm] = useState({
    status: 'handoff' as AgentWorkItemStatus,
    summary_md: '',
    blockers_md: '',
    files_touched: '',
    suggested_next_role: 'reviewer',
  });

  async function refreshOverview(): Promise<void> {
    setLoadState((prev) => (prev === 'ready' ? prev : 'loading'));
    // allSettled, not all: a single failing fetch must not zero the whole HUD
    // (that produced a misleading "0 projects / 0 roles / 0 squads" state even
    // when only one call hiccuped). Each section degrades independently.
    const [projectsRes, rolesRes, squadsRes] = await Promise.allSettled([
      listProjects(),
      listAgentRoleTemplates(),
      listAgentSquads(),
    ]);
    const issues: string[] = [];

    if (projectsRes.status === 'fulfilled') {
      setProjects(projectsRes.value);
      setSquadForm((prev) => ({
        ...prev,
        project_id: prev.project_id || projectsRes.value[0]?.id || '',
      }));
    } else {
      issues.push((projectsRes.reason as Error).message);
    }

    if (rolesRes.status === 'fulfilled') setRoles(rolesRes.value);
    else issues.push((rolesRes.reason as Error).message);

    if (squadsRes.status === 'fulfilled') {
      const loadedSquads = squadsRes.value;
      setSquads(loadedSquads);
      setSelectedSquadId((prev) => {
        if (prev && loadedSquads.some((item) => item.id === prev)) return prev;
        return loadedSquads[0]?.id ?? null;
      });
    } else {
      issues.push((squadsRes.reason as Error).message);
    }

    setError(issues.length ? issues.join(' ') : null);
    setLoadState('ready');
  }

  useEffect(() => {
    void refreshOverview();
  }, []);

  useEffect(() => {
    const shouldRefresh = recentEvents.some((event) =>
      [
        'v1.agent_squad.created',
        'v1.agent_squad.updated',
        'v1.agent_work_item.created',
        'v1.agent_work_item.updated',
        'v1.agent_work_item.handoff',
        'v1.agent_run.started',
        'v1.agent_run.ended',
      ].includes(event.name)
    );
    if (shouldRefresh) void refreshOverview();
  }, [recentEvents]);

  useEffect(() => {
    if (!selectedSquadId) {
      setDetail(null);
      return;
    }
    let cancelled = false;
    void getAgentSquad(selectedSquadId)
      .then((nextDetail) => {
        if (cancelled) return;
        setDetail(nextDetail);
        setSelectedWorkItemId((prev) => {
          if (prev && nextDetail.work_items.some((item) => item.id === prev)) return prev;
          return nextDetail.work_items[0]?.id ?? null;
        });
      })
      .catch((err) => {
        if (!cancelled) setError((err as Error).message || 'Failed to load squad detail.');
      });
    return () => {
      cancelled = true;
    };
  }, [selectedSquadId]);

  const selectedWorkItem = useMemo(
    () => detail?.work_items.find((item) => item.id === selectedWorkItemId) ?? null,
    [detail, selectedWorkItemId]
  );
  const selectedSquad = useMemo(
    () => squads.find((item) => item.id === selectedSquadId) ?? null,
    [selectedSquadId, squads]
  );
  const rolesById = useMemo(
    () => new Map(roles.map((role) => [role.id, role])),
    [roles]
  );
  const selectedProject = useMemo(
    () => projects.find((item) => item.id === selectedSquad?.project_id) ?? null,
    [projects, selectedSquad]
  );
  const squadSessionIds = useMemo(
    () =>
      new Set(
        (detail?.work_items ?? [])
          .map((item) => item.pty_session_id)
          .filter((value): value is string => Boolean(value))
      ),
    [detail]
  );
  const squadTabs = useMemo(
    () => tabs.filter((tab) => squadSessionIds.has(tab.sessionId)),
    [squadSessionIds, tabs]
  );
  const visibleTab =
    squadTabs.find((tab) => tab.sessionId === activeSessionId) ?? squadTabs[0] ?? null;

  useEffect(() => {
    if (!selectedWorkItem) return;
    setLaunchRuntime(selectedWorkItem.preferred_runtime ?? '');
    setHandoffForm((prev) => ({
      ...prev,
      summary_md: selectedWorkItem.summary_md ?? '',
      blockers_md: selectedWorkItem.blockers_md ?? '',
      files_touched: selectedWorkItem.files_touched.join(', '),
      suggested_next_role:
        selectedWorkItem.suggested_next_role ?? prev.suggested_next_role,
    }));
  }, [selectedWorkItem]);

  async function reloadDetail(): Promise<void> {
    if (!selectedSquadId) return;
    const nextDetail = await getAgentSquad(selectedSquadId);
    setDetail(nextDetail);
    setSelectedWorkItemId((prev) => {
      if (prev && nextDetail.work_items.some((item) => item.id === prev)) return prev;
      return nextDetail.work_items[0]?.id ?? null;
    });
  }

  async function handleCreateSquad(): Promise<void> {
    if (!squadForm.project_id || !squadForm.name.trim()) return;
    setBusy('create-squad');
    setError(null);
    try {
      const created = await createAgentSquad({
        project_id: squadForm.project_id,
        name: squadForm.name.trim(),
        goal_md: squadForm.goal_md.trim(),
        lead_role_id: squadForm.lead_role_id || null,
      });
      setSquadForm((prev) => ({ ...prev, name: '', goal_md: '' }));
      await refreshOverview();
      setSelectedSquadId(created.id);
    } catch (err) {
      setError((err as Error).message || 'Could not create squad.');
    } finally {
      setBusy(null);
    }
  }

  async function handleCreateWorkItem(): Promise<void> {
    if (!selectedSquadId || !workItemForm.title.trim()) return;
    setBusy('create-work-item');
    setError(null);
    try {
      const created = await createAgentWorkItem(selectedSquadId, {
        title: workItemForm.title.trim(),
        instructions_md: workItemForm.instructions_md.trim(),
        assigned_role_id: workItemForm.assigned_role_id || null,
        preferred_runtime: workItemForm.preferred_runtime.trim() || null,
      });
      setWorkItemForm((prev) => ({
        ...prev,
        title: '',
        instructions_md: '',
        preferred_runtime: '',
      }));
      await reloadDetail();
      setSelectedWorkItemId(created.id);
    } catch (err) {
      setError((err as Error).message || 'Could not create work item.');
    } finally {
      setBusy(null);
    }
  }

  async function handleDelegate(): Promise<void> {
    if (!selectedWorkItem || !delegateForm.title.trim()) return;
    setBusy('delegate-work-item');
    setError(null);
    try {
      const created = await delegateAgentWorkItem(selectedWorkItem.id, {
        title: delegateForm.title.trim(),
        instructions_md: delegateForm.instructions_md.trim(),
        assigned_role_id: delegateForm.assigned_role_id || null,
        preferred_runtime: delegateForm.preferred_runtime.trim() || null,
      });
      setDelegateForm((prev) => ({
        ...prev,
        title: '',
        instructions_md: '',
        preferred_runtime: '',
      }));
      await reloadDetail();
      setSelectedWorkItemId(created.id);
    } catch (err) {
      setError((err as Error).message || 'Could not delegate helper work.');
    } finally {
      setBusy(null);
    }
  }

  async function handleLaunch(
    item: AgentWorkItem,
    opts: { openInTab: boolean }
  ): Promise<void> {
    setBusy(`launch-${item.id}`);
    setError(null);
    try {
      const launched = await launchAgentWorkItem(item.id, {
        preferred_runtime: launchRuntime.trim() || undefined,
        open_in_tab: opts.openInTab,
      });
      await reloadDetail();
      if (opts.openInTab) await onOpenTab(launched.session_id, launched.argv);
    } catch (err) {
      setError((err as Error).message || 'Could not launch work item.');
    } finally {
      setBusy(null);
    }
  }

  async function handleOpenExisting(item: AgentWorkItem): Promise<void> {
    if (!item.pty_session_id) return;
    setBusy(`open-${item.id}`);
    try {
      await onOpenTab(item.pty_session_id);
    } catch (err) {
      setError((err as Error).message || 'Could not open the helper tab.');
    } finally {
      setBusy(null);
    }
  }

  async function handleHandoff(): Promise<void> {
    if (!selectedWorkItem || !handoffForm.summary_md.trim()) return;
    setBusy('handoff');
    setError(null);
    try {
      const updated = await handoffAgentWorkItem(selectedWorkItem.id, {
        status: handoffForm.status,
        summary_md: handoffForm.summary_md.trim(),
        blockers_md: handoffForm.blockers_md.trim() || null,
        files_touched: handoffForm.files_touched
          .split(',')
          .map((item) => item.trim())
          .filter(Boolean),
        suggested_next_role: handoffForm.suggested_next_role || null,
      });
      await reloadDetail();
      setSelectedWorkItemId(updated.id);
    } catch (err) {
      setError((err as Error).message || 'Could not save the handoff.');
    } finally {
      setBusy(null);
    }
  }

  async function handleQuickStatus(status: AgentWorkItemStatus): Promise<void> {
    if (!selectedWorkItem) return;
    setBusy(`status-${status}`);
    setError(null);
    try {
      await updateAgentWorkItemStatus(selectedWorkItem.id, { status });
      await reloadDetail();
    } catch (err) {
      setError((err as Error).message || 'Could not update the work item status.');
    } finally {
      setBusy(null);
    }
  }

  async function handleStopSquad(): Promise<void> {
    if (!selectedSquad) return;
    setBusy('squad-stop');
    setError(null);
    try {
      // Kill switch: close every live PTY session this squad owns. The daemon
      // finalizes the work items via the session_finalized event.
      await stopAgentSquad(selectedSquad.id);
      await reloadDetail();
    } catch (err) {
      setError((err as Error).message || 'Could not stop the squad.');
    } finally {
      setBusy(null);
    }
  }

  async function handlePauseSquad(nextStatus: AgentSquad['status']): Promise<void> {
    if (!selectedSquad) return;
    setBusy(`squad-${nextStatus}`);
    setError(null);
    try {
      const updated = await patchAgentSquad(selectedSquad.id, { status: nextStatus });
      setSquads((prev) => prev.map((item) => (item.id === updated.id ? updated : item)));
      await reloadDetail();
    } catch (err) {
      setError((err as Error).message || 'Could not update the squad.');
    } finally {
      setBusy(null);
    }
  }

  return (
    <>
    <div className='grid gap-4 xl:grid-cols-[320px,minmax(0,1fr),360px]'>
      <div className='flex min-h-[70vh] flex-col gap-4'>
        <Card className='overflow-hidden border-primary/15 bg-[radial-gradient(circle_at_top_left,rgba(122,90,248,0.18),transparent_45%),linear-gradient(180deg,rgba(17,24,39,0.96),rgba(9,12,24,0.98))] p-4'>
          <div className='flex items-start justify-between gap-3'>
            <div>
              <p className='text-[11px] font-semibold uppercase tracking-[0.22em] text-primary/80'>
                Agent Squads
              </p>
              <h2 className='mt-1 text-xl font-semibold tracking-tight'>
                Human-led, multi-AI sessions
              </h2>
              <p className='mt-2 text-sm text-muted-foreground'>
                One visible lead, real helper PTYs, explicit handoffs, and shared
                project memory.
              </p>
            </div>
            <Users className='mt-1 h-5 w-5 text-primary' />
          </div>
          <div className='mt-4 grid grid-cols-3 gap-2 text-xs text-muted-foreground'>
            <StatPill label='Projects' value={String(projects.length)} />
            <StatPill label='Roles' value={String(roles.length)} />
            <StatPill label='Squads' value={String(squads.length)} />
          </div>
          <Button className='mt-4 w-full' onClick={() => setWizardOpen(true)}>
            <Users className='h-4 w-4' /> Build a team
          </Button>
          <p className='mt-2 text-center text-[11px] text-muted-foreground'>
            Guided setup -- pick a goal, a starter team, tweak the roster, done.
          </p>
        </Card>

        <details className='rounded-xl border border-border/60 bg-card/40'>
          <summary className='cursor-pointer list-none px-4 py-3 text-sm font-medium text-muted-foreground hover:text-foreground'>
            Advanced: build a squad manually
          </summary>
        <Card className='flex flex-col gap-3 border-0 bg-transparent p-4 pt-0'>
          <div className='flex items-center justify-between gap-2'>
            <div>
              <h3 className='text-sm font-semibold'>Create a squad</h3>
              <p className='text-xs text-muted-foreground'>
                Start from a real project, choose a lead role, then add work.
              </p>
            </div>
            <Button
              variant='ghost'
              size='sm'
              onClick={() => void refreshOverview()}
              title='Refresh squads and role templates'
            >
              <RefreshCcw className='h-4 w-4' />
            </Button>
          </div>
          <select
            value={squadForm.project_id}
            onChange={(e) => setSquadForm((prev) => ({ ...prev, project_id: e.target.value }))}
            className='h-9 rounded-md border border-input bg-transparent px-3 text-sm'
          >
            {projects.map((project) => (
              <option key={project.id} value={project.id}>
                {project.name}
              </option>
            ))}
          </select>
          <Input
            value={squadForm.name}
            onChange={(e) => setSquadForm((prev) => ({ ...prev, name: e.target.value }))}
            placeholder='Release hardening squad'
          />
          <select
            value={squadForm.lead_role_id}
            onChange={(e) => setSquadForm((prev) => ({ ...prev, lead_role_id: e.target.value }))}
            className='h-9 rounded-md border border-input bg-transparent px-3 text-sm'
          >
            {roles.map((role) => (
              <option key={role.id} value={role.id}>
                {role.name}
              </option>
            ))}
          </select>
          <textarea
            value={squadForm.goal_md}
            onChange={(e) => setSquadForm((prev) => ({ ...prev, goal_md: e.target.value }))}
            className={TEXTAREA_CLASS}
            placeholder='Goal: ship the feature, run the checks, and leave a clean handoff.'
          />
          <Button
            onClick={() => void handleCreateSquad()}
            disabled={busy === 'create-squad' || !squadForm.project_id || !squadForm.name.trim()}
          >
            {busy === 'create-squad' ? (
              <Loader2 className='h-4 w-4 animate-spin' />
            ) : (
              <Plus className='h-4 w-4' />
            )}
            Create squad
          </Button>
        </Card>
        </details>

        <Card className='flex min-h-0 flex-1 flex-col p-3'>
          <div className='mb-3 flex items-center justify-between gap-2 px-1'>
            <div>
              <h3 className='text-sm font-semibold'>Active squads</h3>
              <p className='text-xs text-muted-foreground'>
                Pick a squad to inspect its helper roster and work queue.
              </p>
            </div>
            {loadState === 'loading' && <Loader2 className='h-4 w-4 animate-spin text-primary' />}
          </div>
          <div className='flex flex-1 flex-col gap-2 overflow-y-auto'>
            {squads.length === 0 ? (
              <div className='rounded-xl border border-dashed border-border p-4 text-sm text-muted-foreground'>
                No squads yet. Create one above to turn Sessions into a coordinated
                multi-agent workspace.
              </div>
            ) : (
              squads.map((squad) => {
                const workCount =
                  detail?.squad.id === squad.id
                    ? detail.work_items.length
                    : undefined;
                return (
                  <button
                    key={squad.id}
                    type='button'
                    onClick={() => setSelectedSquadId(squad.id)}
                    className={cn(
                      'rounded-2xl border px-4 py-3 text-left transition-colors',
                      selectedSquadId === squad.id
                        ? 'border-primary/40 bg-primary/10'
                        : 'border-border bg-card hover:border-primary/20 hover:bg-accent/40'
                    )}
                  >
                    <div className='flex items-start justify-between gap-3'>
                      <div>
                        <p className='font-medium'>{squad.name}</p>
                        <p className='mt-1 text-xs text-muted-foreground'>
                          {projects.find((project) => project.id === squad.project_id)?.name ??
                            squad.project_id}
                        </p>
                      </div>
                      <Badge className={cn('border', statusTone(squad.status))}>
                        {squad.status}
                      </Badge>
                    </div>
                    <div className='mt-3 flex items-center justify-between text-xs text-muted-foreground'>
                      <span>{workCount ?? 'Open'} work items</span>
                      <span>{formatLocal(squad.last_activity_at, 'relative')}</span>
                    </div>
                  </button>
                );
              })
            )}
          </div>
        </Card>
      </div>

      <div className='flex min-h-[70vh] flex-col gap-4'>
        <Card className='flex flex-col gap-3 p-4'>
          <div className='flex flex-wrap items-start justify-between gap-3'>
            <div>
              <p className='text-[11px] font-semibold uppercase tracking-[0.22em] text-primary/80'>
                Squad cockpit
              </p>
              <h2 className='mt-1 text-xl font-semibold tracking-tight'>
                {selectedSquad?.name ?? 'Select a squad'}
              </h2>
              <p className='mt-2 text-sm text-muted-foreground'>
                {selectedProject
                  ? `Project: ${selectedProject.name}`
                  : 'Choose a squad to see its real PTY sessions, work queue, and handoffs.'}
              </p>
            </div>
            {selectedSquad && (
              <div className='flex flex-wrap gap-2'>
                <Button
                  variant='outline'
                  size='sm'
                  onClick={() =>
                    void handlePauseSquad(
                      selectedSquad.status === 'paused' ? 'active' : 'paused'
                    )
                  }
                  disabled={busy === `squad-${selectedSquad.status === 'paused' ? 'active' : 'paused'}`}
                >
                  {selectedSquad.status === 'paused' ? 'Resume squad' : 'Pause squad'}
                </Button>
                <Button
                  variant='outline'
                  size='sm'
                  onClick={() => void handlePauseSquad('completed')}
                  disabled={busy === 'squad-completed'}
                >
                  <CheckCircle2 className='h-4 w-4' />
                  Mark complete
                </Button>
                <Button
                  variant='destructive'
                  size='sm'
                  onClick={() => void handleStopSquad()}
                  disabled={busy === 'squad-stop'}
                  title='Close every running session in this squad'
                >
                  {busy === 'squad-stop' ? (
                    <Loader2 className='h-4 w-4 animate-spin' />
                  ) : (
                    <Square className='h-4 w-4' />
                  )}
                  Stop all
                </Button>
              </div>
            )}
          </div>
          {selectedSquad?.goal_md ? (
            <div className='rounded-2xl border border-border bg-secondary/30 p-3 text-sm text-muted-foreground'>
              {selectedSquad.goal_md}
            </div>
          ) : (
            <div className='rounded-2xl border border-dashed border-border p-3 text-sm text-muted-foreground'>
              No squad goal yet. Add one from the left panel so the lead and helpers
              share the same north star.
            </div>
          )}
          {error && (
            <p role='alert' className='text-sm text-destructive'>
              {error}
            </p>
          )}
        </Card>

        <Card className='flex flex-col gap-3 p-4'>
          <div className='flex items-center justify-between gap-2'>
            <div>
              <h3 className='text-sm font-semibold'>Work queue</h3>
              <p className='text-xs text-muted-foreground'>
                Helpers can stay collapsed here while still being real PTY sessions.
              </p>
            </div>
            {selectedSquad && (
              <Button variant='ghost' size='sm' onClick={() => void reloadDetail()}>
                <RefreshCcw className='h-4 w-4' />
              </Button>
            )}
          </div>
          <div className='grid gap-3 lg:grid-cols-[minmax(0,1fr),320px]'>
            <div className='flex flex-col gap-2'>
              {detail?.work_items.length ? (
                detail.work_items.map((item) => {
                  const role = item.assigned_role_id ? rolesById.get(item.assigned_role_id) : null;
                  const isSelected = selectedWorkItemId === item.id;
                  return (
                    <div
                      key={item.id}
                      role='button'
                      tabIndex={0}
                      onClick={() => {
                        setSelectedWorkItemId(item.id);
                      }}
                      onKeyDown={(event) => {
                        if (event.key === 'Enter' || event.key === ' ') {
                          event.preventDefault();
                          setSelectedWorkItemId(item.id);
                        }
                      }}
                      className={cn(
                        'rounded-2xl border px-4 py-3 text-left transition-colors',
                        'cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                        isSelected
                          ? 'border-primary/35 bg-primary/10'
                          : 'border-border bg-card hover:border-primary/20 hover:bg-accent/40'
                      )}
                    >
                      <div className='flex items-start justify-between gap-3'>
                        <div>
                          <p className='font-medium'>{item.title}</p>
                          <p className='mt-1 text-xs text-muted-foreground'>
                            {role?.name ?? 'Unassigned role'}
                          </p>
                        </div>
                        <Badge className={cn('border', statusTone(item.status))}>
                          {item.status}
                        </Badge>
                      </div>
                      <div className='mt-3 flex flex-wrap gap-2'>
                        {item.pty_session_id ? (
                          <Button
                            type='button'
                            size='sm'
                            variant='outline'
                            onClick={(event) => {
                              event.stopPropagation();
                              void handleOpenExisting(item);
                            }}
                            disabled={busy === `open-${item.id}`}
                          >
                            <SquareTerminal className='h-4 w-4' />
                            Open tab
                          </Button>
                        ) : (
                          <Button
                            type='button'
                            size='sm'
                            onClick={(event) => {
                              event.stopPropagation();
                              void handleLaunch(item, { openInTab: role?.default_visibility !== 'helper' });
                            }}
                            disabled={busy === `launch-${item.id}`}
                          >
                            {busy === `launch-${item.id}` ? (
                              <Loader2 className='h-4 w-4 animate-spin' />
                            ) : (
                              <Rocket className='h-4 w-4' />
                            )}
                            Launch
                          </Button>
                        )}
                        {item.pty_session_id && (
                          <Button
                            type='button'
                            size='sm'
                            variant='ghost'
                            onClick={(event) => {
                              event.stopPropagation();
                              void handleLaunch(item, { openInTab: false });
                            }}
                            disabled={busy === `launch-${item.id}`}
                          >
                            <Play className='h-4 w-4' />
                            Relaunch collapsed
                          </Button>
                        )}
                      </div>
                    </div>
                  );
                })
              ) : (
                <div className='rounded-2xl border border-dashed border-border p-4 text-sm text-muted-foreground'>
                  No work items yet. Add the first lead or helper task from the panel on
                  the right.
                </div>
              )}
            </div>

            <div className='rounded-2xl border border-border bg-secondary/20 p-4'>
              <h3 className='text-sm font-semibold'>New work item</h3>
              <p className='mt-1 text-xs text-muted-foreground'>
                Create top-level work in the squad queue. Helpers inherit the same
                project memory and handoff model.
              </p>
              <div className='mt-3 flex flex-col gap-2'>
                <Input
                  value={workItemForm.title}
                  onChange={(e) =>
                    setWorkItemForm((prev) => ({ ...prev, title: e.target.value }))
                  }
                  placeholder='Implement the toolbar state model'
                />
                <select
                  value={workItemForm.assigned_role_id}
                  onChange={(e) =>
                    setWorkItemForm((prev) => ({
                      ...prev,
                      assigned_role_id: e.target.value,
                    }))
                  }
                  className='h-9 rounded-md border border-input bg-transparent px-3 text-sm'
                >
                  {roles.map((role) => (
                    <option key={role.id} value={role.id}>
                      {role.name}
                    </option>
                  ))}
                </select>
                <Input
                  value={workItemForm.preferred_runtime}
                  onChange={(e) =>
                    setWorkItemForm((prev) => ({
                      ...prev,
                      preferred_runtime: e.target.value,
                    }))
                  }
                  placeholder='Optional runtime override'
                />
                <textarea
                  value={workItemForm.instructions_md}
                  onChange={(e) =>
                    setWorkItemForm((prev) => ({
                      ...prev,
                      instructions_md: e.target.value,
                    }))
                  }
                  className={TEXTAREA_CLASS}
                  placeholder='Explain what this worker should own.'
                />
                <Button
                  onClick={() => void handleCreateWorkItem()}
                  disabled={!selectedSquadId || busy === 'create-work-item' || !workItemForm.title.trim()}
                >
                  {busy === 'create-work-item' ? (
                    <Loader2 className='h-4 w-4 animate-spin' />
                  ) : (
                    <Plus className='h-4 w-4' />
                  )}
                  Add work item
                </Button>
              </div>
            </div>
          </div>
        </Card>

        <Card className='flex min-h-[420px] flex-col gap-3 p-4'>
          <div className='flex items-center justify-between gap-3'>
            <div>
              <h3 className='text-sm font-semibold'>Live sessions</h3>
              <p className='text-xs text-muted-foreground'>
                Every helper is a normal PTY session you can reopen and inspect.
              </p>
            </div>
            <Badge variant='outline'>{squadTabs.length} open tab(s)</Badge>
          </div>

          {squadTabs.length > 0 && (
            <div className='flex flex-wrap items-center gap-1'>
              {squadTabs.map((tab) => {
                const isActive = tab.sessionId === visibleTab?.sessionId;
                const label = labelForArgv(tab.argv, tab.sessionId);
                return (
                  <div
                    key={tab.sessionId}
                    className={cn(
                      'group flex items-center gap-1 rounded-md border px-2 py-1 text-xs transition-colors',
                      isActive
                        ? 'border-primary bg-card text-foreground'
                        : 'border-border bg-secondary/40 text-muted-foreground hover:text-foreground'
                    )}
                  >
                    <button
                      type='button'
                      onClick={() => void onOpenTab(tab.sessionId, tab.argv)}
                      className='flex items-center gap-1.5 font-mono'
                    >
                      <SquareTerminal className='h-3 w-3' />
                      {label}
                    </button>
                    <button
                      type='button'
                      onClick={() => void onRestartTab(tab.sessionId)}
                      className='rounded p-0.5 opacity-60 hover:bg-accent hover:opacity-100'
                      aria-label={`Restart ${label}`}
                    >
                      <RefreshCcw className='h-3 w-3' />
                    </button>
                    <button
                      type='button'
                      onClick={() => void onCloseTab(tab.sessionId)}
                      className='rounded p-0.5 opacity-60 hover:bg-accent hover:opacity-100'
                      aria-label={`Close ${label}`}
                    >
                      <ChevronRight className='h-3 w-3 rotate-45' />
                    </button>
                  </div>
                );
              })}
            </div>
          )}

          {visibleTab ? (
            <div className='h-[48vh] min-h-[360px]'>
              <SessionTerminal
                key={visibleTab.sessionId}
                sessionId={visibleTab.sessionId}
                initialScrollback={visibleTab.scrollback ?? undefined}
              />
            </div>
          ) : (
            <div className='flex flex-1 flex-col items-center justify-center rounded-2xl border border-dashed border-border p-8 text-center'>
              <SquareTerminal className='h-8 w-8 text-muted-foreground' />
              <h4 className='mt-3 text-base font-semibold'>No squad session visible yet</h4>
              <p className='mt-2 max-w-md text-sm text-muted-foreground'>
                Launch a lead or helper from the work queue. Lead sessions open in a tab
                immediately; helper sessions can launch collapsed and still be reopened later.
              </p>
            </div>
          )}
        </Card>
      </div>

      <div className='flex min-h-[70vh] flex-col gap-4'>
        <Card className='flex flex-col gap-3 p-4'>
          <div className='flex items-center gap-2'>
            <Bot className='h-4 w-4 text-primary' />
            <h3 className='text-sm font-semibold'>Selected work item</h3>
          </div>
          {selectedWorkItem ? (
            <>
              <div>
                <h4 className='text-lg font-semibold tracking-tight'>{selectedWorkItem.title}</h4>
                <div className='mt-2 flex flex-wrap gap-2'>
                  <Badge className={cn('border', statusTone(selectedWorkItem.status))}>
                    {selectedWorkItem.status}
                  </Badge>
                  {selectedWorkItem.assigned_role_id && (
                    <Badge variant='outline'>
                      {rolesById.get(selectedWorkItem.assigned_role_id)?.name ??
                        selectedWorkItem.assigned_role_id}
                    </Badge>
                  )}
                  {selectedWorkItem.preferred_runtime && (
                    <Badge variant='outline'>{selectedWorkItem.preferred_runtime}</Badge>
                  )}
                </div>
              </div>
              <p className='text-sm text-muted-foreground'>
                {selectedWorkItem.instructions_md || 'No instructions on this work item yet.'}
              </p>
              <div className='grid gap-2'>
                <Input
                  value={launchRuntime}
                  onChange={(e) => setLaunchRuntime(e.target.value)}
                  placeholder='Optional runtime override before launch'
                />
                <div className='flex flex-wrap gap-2'>
                  <Button
                    onClick={() =>
                      void handleLaunch(selectedWorkItem, {
                        openInTab:
                          rolesById.get(selectedWorkItem.assigned_role_id ?? '')?.default_visibility !==
                          'helper',
                      })
                    }
                    disabled={busy === `launch-${selectedWorkItem.id}`}
                  >
                    {busy === `launch-${selectedWorkItem.id}` ? (
                      <Loader2 className='h-4 w-4 animate-spin' />
                    ) : (
                      <Rocket className='h-4 w-4' />
                    )}
                    Launch worker
                  </Button>
                  {selectedWorkItem.pty_session_id && (
                    <Button
                      variant='outline'
                      onClick={() => void handleOpenExisting(selectedWorkItem)}
                      disabled={busy === `open-${selectedWorkItem.id}`}
                    >
                      <SquareTerminal className='h-4 w-4' />
                      Open session
                    </Button>
                  )}
                </div>
                <div className='flex flex-wrap gap-2'>
                  <Button variant='ghost' size='sm' onClick={() => void handleQuickStatus('running')}>
                    Mark running
                  </Button>
                  <Button variant='ghost' size='sm' onClick={() => void handleQuickStatus('blocked')}>
                    Mark blocked
                  </Button>
                  <Button variant='ghost' size='sm' onClick={() => void handleQuickStatus('completed')}>
                    Mark completed
                  </Button>
                </div>
              </div>
            </>
          ) : (
            <div className='rounded-2xl border border-dashed border-border p-4 text-sm text-muted-foreground'>
              Select a work item to launch it, inspect the handoff, or delegate helper work.
            </div>
          )}
        </Card>

        <Card className='flex flex-col gap-3 p-4'>
          <div className='flex items-center gap-2'>
            <Sparkles className='h-4 w-4 text-primary' />
            <h3 className='text-sm font-semibold'>Delegate helper</h3>
          </div>
          <Input
            value={delegateForm.title}
            onChange={(e) =>
              setDelegateForm((prev) => ({ ...prev, title: e.target.value }))
            }
            placeholder='Review the changed files for regressions'
          />
          <select
            value={delegateForm.assigned_role_id}
            onChange={(e) =>
              setDelegateForm((prev) => ({
                ...prev,
                assigned_role_id: e.target.value,
              }))
            }
            className='h-9 rounded-md border border-input bg-transparent px-3 text-sm'
          >
            {roles.map((role) => (
              <option key={role.id} value={role.id}>
                {role.name}
              </option>
            ))}
          </select>
          <Input
            value={delegateForm.preferred_runtime}
            onChange={(e) =>
              setDelegateForm((prev) => ({
                ...prev,
                preferred_runtime: e.target.value,
              }))
            }
            placeholder='Optional runtime override'
          />
          <textarea
            value={delegateForm.instructions_md}
            onChange={(e) =>
              setDelegateForm((prev) => ({
                ...prev,
                instructions_md: e.target.value,
              }))
            }
            className={TEXTAREA_CLASS}
            placeholder='Tell the helper exactly what to own, review, or research.'
          />
          <Button
            onClick={() => void handleDelegate()}
            disabled={!selectedWorkItem || !delegateForm.title.trim() || busy === 'delegate-work-item'}
          >
            {busy === 'delegate-work-item' ? (
              <Loader2 className='h-4 w-4 animate-spin' />
            ) : (
              <ChevronRight className='h-4 w-4' />
            )}
            Create helper item
          </Button>
        </Card>

        <Card className='flex flex-col gap-3 p-4'>
          <div className='flex items-center gap-2'>
            <CheckCircle2 className='h-4 w-4 text-primary' />
            <h3 className='text-sm font-semibold'>Explicit handoff</h3>
          </div>
          <select
            value={handoffForm.status}
            onChange={(e) =>
              setHandoffForm((prev) => ({
                ...prev,
                status: e.target.value as AgentWorkItemStatus,
              }))
            }
            className='h-9 rounded-md border border-input bg-transparent px-3 text-sm'
          >
            <option value='handoff'>Ready for handoff</option>
            <option value='blocked'>Blocked</option>
            <option value='completed'>Completed</option>
          </select>
          <textarea
            value={handoffForm.summary_md}
            onChange={(e) =>
              setHandoffForm((prev) => ({ ...prev, summary_md: e.target.value }))
            }
            className={TEXTAREA_CLASS}
            placeholder='Summarize what changed, what was learned, and what the next worker should know.'
          />
          <textarea
            value={handoffForm.blockers_md}
            onChange={(e) =>
              setHandoffForm((prev) => ({ ...prev, blockers_md: e.target.value }))
            }
            className={TEXTAREA_CLASS}
            placeholder='Blockers, missing credentials, flaky tests, or open decisions.'
          />
          <Input
            value={handoffForm.files_touched}
            onChange={(e) =>
              setHandoffForm((prev) => ({ ...prev, files_touched: e.target.value }))
            }
            placeholder='Comma-separated files touched'
          />
          <select
            value={handoffForm.suggested_next_role}
            onChange={(e) =>
              setHandoffForm((prev) => ({
                ...prev,
                suggested_next_role: e.target.value,
              }))
            }
            className='h-9 rounded-md border border-input bg-transparent px-3 text-sm'
          >
            {roles.map((role) => (
              <option key={role.id} value={role.id}>
                {role.name}
              </option>
            ))}
          </select>
          <Button
            onClick={() => void handleHandoff()}
            disabled={!selectedWorkItem || !handoffForm.summary_md.trim() || busy === 'handoff'}
          >
            {busy === 'handoff' ? (
              <Loader2 className='h-4 w-4 animate-spin' />
            ) : (
              <Sparkles className='h-4 w-4' />
            )}
            Save handoff
          </Button>
          {selectedWorkItem?.transcript_file_id && (
            <p className='text-xs text-muted-foreground'>
              Transcript artifact linked: <span className='font-mono'>{selectedWorkItem.transcript_file_id}</span>
            </p>
          )}
        </Card>
      </div>
    </div>
    <SquadWizard
      open={wizardOpen}
      onClose={() => setWizardOpen(false)}
      projects={projects}
      roles={roles}
      onCreated={(squadId) => {
        setWizardOpen(false);
        setSelectedSquadId(squadId);
        void refreshOverview();
      }}
    />
    </>
  );
}

function StatPill({ label, value }: { label: string; value: string }): JSX.Element {
  return (
    <div className='rounded-2xl border border-white/10 bg-white/5 px-3 py-2'>
      <p className='text-[10px] uppercase tracking-[0.18em] text-muted-foreground'>{label}</p>
      <p className='mt-1 text-base font-semibold text-foreground'>{value}</p>
    </div>
  );
}
