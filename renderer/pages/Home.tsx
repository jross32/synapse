// Home page (Milestone F · v0.1.10) -- the Synapse command-center overview.
//
// A featured slideshow over the user's apps sits up top, then the heartbeat
// HUD, then live activity + quick jumps. The slideshow can launch a project
// straight from the hero.

import { useMemo, useState } from 'react';
import { Activity, Boxes, CircleAlert, CirclePlay } from 'lucide-react';

import { useDaemon } from '@shared/daemon-context';
import { launchProject } from '@shared/projects-client';
import { formatLocal } from '@shared/format-time';
import type { Project } from '@shared/generated-types';
import type { PageId } from '@shared/nav';
import { Card } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { PageHeader } from '../components/PageHeader';
import { FeaturedSlideshow } from '../components/FeaturedSlideshow';

const FEATURED_CAP = 5;

export interface HomePageProps {
  onNavigate: (page: PageId) => void;
}

export function HomePage({ onNavigate }: HomePageProps): JSX.Element {
  const { projects, recentEvents, health, upsertProjectLocal } = useDaemon();

  const [launchBusyId, setLaunchBusyId] = useState<string | null>(null);
  const [launchError, setLaunchError] = useState<string | null>(null);

  const running = projects.filter((p) => p.status === 'launched').length;
  const errored = projects.filter((p) => p.status === 'error').length;
  const idle = projects.length - running - errored;

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
          onView={() => onNavigate('apps')}
        />
      ) : (
        <Card className='flex flex-col items-center gap-3 border-dashed p-10 text-center'>
          <h2 className='text-lg font-semibold'>Welcome to Synapse</h2>
          <p className='max-w-md text-sm text-muted-foreground'>
            Add your first project — or scan a folder and let auto-discovery find them all —
            and it'll headline here.
          </p>
          <Button onClick={() => onNavigate('apps')}>Go to Apps</Button>
        </Card>
      )}

      {launchError && (
        <p role='alert' className='text-sm text-destructive'>
          {launchError}
        </p>
      )}

      {/* Heartbeat HUD */}
      <div className='grid grid-cols-[repeat(auto-fit,minmax(180px,1fr))] gap-4'>
        <StatCard icon={<CirclePlay className='h-5 w-5 text-status-launched' />} label='Running' value={running} />
        <StatCard icon={<Boxes className='h-5 w-5 text-status-idle' />} label='Idle / stopped' value={idle} />
        <StatCard icon={<CircleAlert className='h-5 w-5 text-status-error' />} label='Errored' value={errored} />
        <StatCard icon={<Activity className='h-5 w-5 text-primary' />} label='Total projects' value={projects.length} />
      </div>

      <div className='grid grid-cols-1 gap-6 lg:grid-cols-[3fr_2fr]'>
        {/* Recent activity */}
        <Card className='flex flex-col gap-3 p-6'>
          <h2 className='text-lg font-semibold'>Recent activity</h2>
          {recentEvents.length === 0 ? (
            <p className='text-sm text-muted-foreground'>
              No events yet. Daemon and project events will stream here live.
            </p>
          ) : (
            <ul className='flex flex-col gap-1.5'>
              {recentEvents.slice(0, 10).map((evt) => (
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
            <Button variant='secondary' className='justify-start' onClick={() => onNavigate('apps')}>
              Open Apps
            </Button>
            <Button variant='secondary' className='justify-start' onClick={() => onNavigate('sessions')}>
              Sessions (Claude / Codex / shells)
            </Button>
            <Button variant='secondary' className='justify-start' onClick={() => onNavigate('processes')}>
              Live Processes
            </Button>
            <Button variant='secondary' className='justify-start' onClick={() => onNavigate('tools')}>
              Tools
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
          <Button variant='secondary' size='sm' onClick={() => onNavigate('sessions')}>
            Open a coder session
          </Button>
        </div>
      </Card>
    </div>
  );
}

function StatCard({ icon, label, value }: { icon: React.ReactNode; label: string; value: number }): JSX.Element {
  return (
    <Card className='flex items-center gap-4 p-5'>
      <div className='flex h-11 w-11 items-center justify-center rounded-md bg-secondary'>{icon}</div>
      <div>
        <div className='text-2xl font-semibold leading-none'>{value}</div>
        <div className='mt-1 text-xs text-muted-foreground'>{label}</div>
      </div>
    </Card>
  );
}
