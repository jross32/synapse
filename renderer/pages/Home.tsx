// Home page (Milestone F) -- at-a-glance command-center overview.
// The featured slideshow + recents carousel get fleshed out in v0.1.10;
// v0.1.8 ships the heartbeat HUD + recent activity feed.

import { Activity, Boxes, CircleAlert, CirclePlay } from 'lucide-react';

import { useDaemon } from '@shared/daemon-context';
import { formatLocal } from '@shared/format-time';
import type { PageId } from '@shared/nav';
import { Card } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { PageHeader } from '../components/PageHeader';

export interface HomePageProps {
  onNavigate: (page: PageId) => void;
}

export function HomePage({ onNavigate }: HomePageProps): JSX.Element {
  const { projects, recentEvents, health } = useDaemon();

  const running = projects.filter((p) => p.status === 'launched').length;
  const errored = projects.filter((p) => p.status === 'error').length;
  const idle = projects.length - running - errored;

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

      {/* Heartbeat HUD */}
      <div className='grid grid-cols-[repeat(auto-fit,minmax(180px,1fr))] gap-4'>
        <StatCard icon={<CirclePlay className='h-5 w-5 text-status-launched' />} label='Running' value={running} />
        <StatCard icon={<Boxes className='h-5 w-5 text-status-idle' />} label='Idle / stopped' value={idle} />
        <StatCard icon={<CircleAlert className='h-5 w-5 text-status-error' />} label='Errored' value={errored} />
        <StatCard icon={<Activity className='h-5 w-5 text-primary' />} label='Total projects' value={projects.length} />
      </div>

      <div className='grid grid-cols-1 gap-6 lg:grid-cols-2'>
        {/* Quick jump */}
        <Card className='flex flex-col gap-3 p-6'>
          <h2 className='text-lg font-semibold'>Jump in</h2>
          <p className='text-sm text-muted-foreground'>
            Launch + manage your projects, watch what's running, or wire up a tool.
          </p>
          <div className='mt-1 flex flex-wrap gap-2'>
            <Button variant='secondary' onClick={() => onNavigate('apps')}>
              Open Apps
            </Button>
            <Button variant='secondary' onClick={() => onNavigate('processes')}>
              Live Processes
            </Button>
            <Button variant='secondary' onClick={() => onNavigate('tools')}>
              Tools
            </Button>
          </div>
        </Card>

        {/* Recent activity */}
        <Card className='flex flex-col gap-3 p-6'>
          <h2 className='text-lg font-semibold'>Recent activity</h2>
          {recentEvents.length === 0 ? (
            <p className='text-sm text-muted-foreground'>
              No events yet. Daemon and project events will stream here live.
            </p>
          ) : (
            <ul className='flex flex-col gap-1.5'>
              {recentEvents.slice(0, 8).map((evt) => (
                <li key={evt.id} className='flex items-baseline gap-2 font-mono text-xs'>
                  <span className='text-primary'>#{evt.id}</span>
                  <span className='flex-1 truncate text-foreground'>{evt.name}</span>
                  <span className='text-muted-foreground'>{formatLocal(evt.timestamp_utc, 'time')}</span>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
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
