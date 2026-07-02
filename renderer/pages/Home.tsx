// Home page (Milestone F · v0.1.10) -- the Synapse command-center overview.
//
// A featured slideshow over the user's apps sits up top, then the heartbeat
// HUD, then live activity + quick jumps. The slideshow can launch a project
// straight from the hero.

import { useMemo, useState } from 'react';
import { Activity, CircleAlert, CirclePlay, CircleStop, Loader2 } from 'lucide-react';

import { useDaemon } from '@shared/daemon-context';
import { launchProject } from '@shared/projects-client';
import { formatLocal } from '@shared/format-time';
import type { Project } from '@shared/generated-types';
import type { NavigationIntent } from '@shared/nav';
import { Card } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { PageHeader } from '../components/PageHeader';
import { FeaturedSlideshow } from '../components/FeaturedSlideshow';

const FEATURED_CAP = 5;

export interface HomePageProps {
  onNavigate: (intent: NavigationIntent) => void;
}

export function HomePage({ onNavigate }: HomePageProps): JSX.Element {
  const { projects, recentEvents, health, upsertProjectLocal } = useDaemon();

  const [launchBusyId, setLaunchBusyId] = useState<string | null>(null);
  const [launchError, setLaunchError] = useState<string | null>(null);
  const [activityExpanded, setActivityExpanded] = useState(false);

  // Status breakdown -- Contract #2's six states. Per v0.1.36 A3 we
  // collapse idle + stopped into a single "Not running" tile because
  // the distinction wasn't load-bearing in the HUD. transitioning
  // (launching / stopping) stays separate since "mid-flight" is
  // visually distinct.
  const running = projects.filter((p) => p.status === 'launched').length;
  const errored = projects.filter((p) => p.status === 'error').length;
  const notRunning = projects.filter(
    (p) => p.status === 'idle' || p.status === 'stopped'
  ).length;
  const transitioning = projects.filter(
    (p) => p.status === 'launching' || p.status === 'stopping'
  ).length;

  // Featured = pinned projects first, then the most-recently-active ones.
  const featured = useMemo(() => {
    const pinned = projects
      .filter((p) => p.pinned)
      .sort((a, b) => a.name.localeCompare(b.name));
    const rest = projects
      .filter((p) => !p.pinned)
      .sort((a, b) => b.last_transition_at.localeCompare(a.last_transition_at));
    return [...pinned, ...rest].slice(0, FEATURED_CAP);
  }, [projects]);

  // The WS replay buffer can redeliver an event the client already has
  // (e.g. on reconnect), which duplicated `evt.id` and triggered React's
  // "two children with the same key" warning. Dedupe by id so keys are
  // unique and the list never shows the same event twice.
  const uniqueEvents = useMemo(() => {
    const seen = new Set<string>();
    return recentEvents.filter((evt) => {
      const key = String(evt.id);
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  }, [recentEvents]);

  async function handleLaunch(project: Project): Promise<void> {
    setLaunchBusyId(project.id);
    setLaunchError(null);
    try {
      upsertProjectLocal(await launchProject(project.id));
    } catch (err) {
      setLaunchError(`Couldn't launch ${project.name}: ${(err as Error).message}`);
    } finally {
      setLaunchBusyId(null);
    }
  }

  return (
    <div className='flex flex-col gap-6'>
      <PageHeader
        title='Home'
        subtitle={
          health
            ? `Synapse daemon v${health.version} — ${projects.length} project${projects.length === 1 ? '' : 's'} registered.`
            : 'Connecting to the Synapse daemon…'
        }
      />

      {featured.length > 0 ? (
        <FeaturedSlideshow
          projects={featured}
          busyId={launchBusyId}
          onLaunch={(p) => void handleLaunch(p)}
          onView={() => onNavigate({ page: 'apps', section: 'projects' })}
        />
      ) : (
        <Card className='flex flex-col items-center gap-3 border-dashed p-10 text-center'>
          <h2 className='text-lg font-semibold'>Welcome to Synapse</h2>
          <p className='max-w-md text-sm text-muted-foreground'>
            Add your first project — or scan a folder and let auto-discovery find them all —
            and it'll headline here.
          </p>
          <Button onClick={() => onNavigate({ page: 'apps', section: 'projects' })}>Go to Apps</Button>
        </Card>
      )}

      {launchError && (
        <p role='alert' className='text-sm text-destructive'>
          {launchError}
        </p>
      )}

      {/* Heartbeat HUD -- one tile per Contract #2 status.
          Idle = "never started", Stopped = "ran, now exited". Transitioning
          only appears while it's > 0 so the row doesn't grow into noise. */}
      <div className='grid grid-cols-[repeat(auto-fit,minmax(180px,1fr))] gap-4'>
        <StatCard
          icon={<CirclePlay className='h-5 w-5 text-status-launched' />}
          label='Running'
          value={running}
          title='launched -- heartbeat OK, ports answering.'
        />
        <StatCard
          icon={<CircleStop className='h-5 w-5 text-status-stopped' />}
          label='Not running'
          value={notRunning}
          title="Synapse isn't managing this project right now -- either it was never started this install or it exited."
        />
        {transitioning > 0 && (
          <StatCard
            icon={<Loader2 className='h-5 w-5 animate-spin text-status-launching' />}
            label='Transitioning'
            value={transitioning}
            title='launching or stopping -- mid-state, will settle soon.'
          />
        )}
        <StatCard
          icon={<CircleAlert className='h-5 w-5 text-status-error' />}
          label='Errored'
          value={errored}
          title='Crashed, restart policy gave up, or launch failed.'
        />
        <StatCard
          icon={<Activity className='h-5 w-5 text-primary' />}
          label='Total projects'
          value={projects.length}
        />
      </div>

      <div className='grid grid-cols-1 gap-6 lg:grid-cols-[3fr_2fr]'>
        {/* Recent activity -- collapsed shows 10; expanded shows up to 50.
            The DaemonProvider's ring buffer caps the source list, so even
            "expanded" stays bounded. */}
        <Card className='flex flex-col gap-3 p-6'>
          <div className='flex items-baseline justify-between gap-2'>
            <h2 className='text-lg font-semibold'>Recent activity</h2>
            {uniqueEvents.length > 10 && (
              <button
                type='button'
                onClick={() => setActivityExpanded((v) => !v)}
                className='text-xs text-muted-foreground hover:text-foreground'
              >
                {activityExpanded
                  ? 'Show 10'
                  : `Show all (${Math.min(uniqueEvents.length, 50)})`}
              </button>
            )}
          </div>
          {uniqueEvents.length === 0 ? (
            <p className='text-sm text-muted-foreground'>
              No events yet. Daemon and project events will stream here live.
            </p>
          ) : (
            <ul className='flex flex-col gap-1.5'>
              {uniqueEvents
                .slice(0, activityExpanded ? 50 : 10)
                .map((evt) => (
                  <li key={evt.id} className='flex items-baseline gap-2 font-mono text-xs'>
                    <span className='text-primary'>#{evt.id}</span>
                    <span className='flex-1 truncate text-foreground'>{evt.name}</span>
                    <span className='text-muted-foreground'>{formatLocal(evt.timestamp_utc, 'time')}</span>
                  </li>
                ))}
            </ul>
          )}
        </Card>

        {/* Quick jump */}
        <Card className='flex flex-col gap-3 p-6'>
          <h2 className='text-lg font-semibold'>Jump in</h2>
          <p className='text-sm text-muted-foreground'>
            Launch + manage your projects, watch what's running, or wire up a tool.
          </p>
          <div className='mt-1 flex flex-col gap-2'>
            <Button
              variant='secondary'
              className='justify-start'
              onClick={() => onNavigate({ page: 'apps', section: 'projects' })}
            >
              Open Apps
            </Button>
            <Button
              variant='secondary'
              className='justify-start'
              onClick={() => onNavigate({ page: 'ai-coding', section: 'sessions' })}
            >
              Sessions (Claude / Codex / shells)
            </Button>
            <Button
              variant='secondary'
              className='justify-start'
              onClick={() => onNavigate({ page: 'apps', section: 'running' })}
            >
              Running Now
            </Button>
            <Button
              variant='secondary'
              className='justify-start'
              onClick={() => onNavigate({ page: 'tools', section: 'tools', toolsTab: 'installed' })}
            >
              My Tools
            </Button>
            <Button
              variant='secondary'
              className='justify-start'
              onClick={() => onNavigate({ page: 'whatsnew' })}
            >
              What&apos;s New &amp; Roadmap
            </Button>
          </div>
        </Card>
      </div>

      {/* "Built for AI agents too" -- this is the explicit ADR-0002 stance.
          Goes on Home so a fresh human sees it, and any Claude session that
          opens / from the workbench has a trivial pointer to GET /ai/context. */}
      <Card className='flex flex-col gap-3 border-dashed p-6'>
        <h2 className='text-lg font-semibold'>Built for AI agents too</h2>
        <p className='max-w-3xl text-sm text-muted-foreground'>
          The dashboard works in two directions. A human navigates by clicking;
          a Claude or Codex session running in a <b>Sessions</b> tab navigates
          by REST. Every project, tool, marketplace entry, audit row and live
          PTY session is exposed as JSON — and there's a compact orientation
          digest at <code className='font-mono'>GET /api/v1/ai/context</code>{' '}
          so a coder session can introspect what's running and where files
          live without sifting through individual endpoints.
        </p>
        <div className='flex flex-wrap gap-2'>
          <Button
            variant='secondary'
            size='sm'
            onClick={() => onNavigate({ page: 'ai-coding', section: 'sessions' })}
          >
            Open a coder session
          </Button>
        </div>
      </Card>
    </div>
  );
}

function StatCard({
  icon,
  label,
  value,
  title,
}: {
  icon: React.ReactNode;
  label: string;
  value: number;
  title?: string;
}): JSX.Element {
  return (
    <Card className='flex items-center gap-4 p-5' title={title}>
      <div className='flex h-11 w-11 items-center justify-center rounded-md bg-secondary'>{icon}</div>
      <div>
        <div className='text-2xl font-semibold leading-none'>{value}</div>
        <div className='mt-1 text-xs text-muted-foreground'>{label}</div>
      </div>
    </Card>
  );
}
