// Live process monitor (Contract #19) -- a table of everything Synapse is
// running, CPU% + RAM streaming from v1.process.heartbeat.

import { stopProject } from '@shared/projects-client';
import type { Project, ResourceSnapshot } from '@shared/generated-types';
import { formatUptime } from '@shared/format-time';
import { cn } from '@shared/utils';
import { Button } from './ui/button';
import { Card } from './ui/card';
import { StatusBadge } from './StatusBadge';

export interface ProcessMonitorProps {
  projects: Project[];
  resourcesById: Record<string, ResourceSnapshot>;
  onActionError?: (project: Project, error: Error) => void;
}

const RUNNING_STATES = new Set(['launching', 'launched', 'stopping']);

export function ProcessMonitor({ projects, resourcesById, onActionError }: ProcessMonitorProps): JSX.Element {
  const running = projects.filter((p) => RUNNING_STATES.has(p.status));

  if (running.length === 0) {
    return (
      <Card className='border-dashed p-8 text-center text-sm text-muted-foreground'>
        Nothing running. Launch a project from the Apps tab and it will appear here
        with live CPU + memory.
      </Card>
    );
  }

  return (
    <Card className='overflow-hidden'>
      <div className='overflow-x-auto'>
        <table className='min-w-[760px] w-full border-collapse text-sm'>
          <thead>
            <tr className='border-b border-border'>
              {['Project', 'Status', 'PID', 'Uptime', 'CPU', 'Memory', ''].map((h) => (
                <th
                  key={h}
                  className='px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground'
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {running.map((p) => {
              const res = resourcesById[p.id];
              return (
                <tr key={p.id} className='border-b border-border last:border-0'>
                  <td className='px-4 py-3 font-medium'>{p.name}</td>
                  <td className='px-4 py-3'>
                    <StatusBadge status={p.status} />
                  </td>
                  <td className='px-4 py-3 font-mono text-muted-foreground'>{res ? res.pid : '—'}</td>
                  <td className='px-4 py-3 font-mono text-muted-foreground'>
                    {p.status === 'launched' ? formatUptime(p.last_transition_at) : '—'}
                  </td>
                  <td className='px-4 py-3'>
                    <CpuGauge value={res?.cpu_percent ?? 0} />
                  </td>
                  <td className='px-4 py-3 font-mono'>{res ? `${res.rss_mb.toFixed(0)} MB` : '—'}</td>
                  <td className='px-4 py-3 text-right'>
                    <Button
                      variant='outline'
                      size='sm'
                      disabled={p.status !== 'launched'}
                      onClick={() => {
                        stopProject(p.id).catch((err) => onActionError?.(p, err as Error));
                      }}
                    >
                      Stop
                    </Button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function CpuGauge({ value }: { value: number }): JSX.Element {
  const pct = Math.min(100, value);
  const tone =
    pct > 85 ? 'bg-status-error' : pct > 60 ? 'bg-status-launching' : 'bg-status-launched';
  return (
    <div className='flex items-center gap-2'>
      <div className='h-1.5 w-16 overflow-hidden rounded-full bg-secondary'>
        <div className={cn('h-full', tone)} style={{ width: `${pct}%` }} />
      </div>
      <span className='min-w-[44px] font-mono text-xs'>{value.toFixed(1)}%</span>
    </div>
  );
}
