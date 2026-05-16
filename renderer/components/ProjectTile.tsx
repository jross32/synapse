// One project tile (Milestones D/E/F) -- shadcn Card surface.
//
// Shows name + path + live status, the cmd/port/uptime metadata, a live
// cpu/ram line while running, and the Launch/Stop + Edit/Delete actions.
// A "more actions" row exposes quick OS actions (open folder / browser).

import { useState } from 'react';
import { FolderOpen, Globe } from 'lucide-react';

import { launchProject, stopProject } from '@shared/projects-client';
import type { Project, ResourceSnapshot } from '@shared/generated-types';
import { formatLocal, formatUptime } from '@shared/format-time';
import { openExternal } from '@shared/electron-bridge';
import { Button } from './ui/button';
import { Card } from './ui/card';
import { StatusBadge } from './StatusBadge';

export interface ProjectTileProps {
  project: Project;
  resources?: ResourceSnapshot;
  onEdit: (project: Project) => void;
  onDelete: (project: Project) => void;
  onViewLogs: (project: Project) => void;
  onActionError?: (project: Project, error: Error) => void;
}

export function ProjectTile({
  project,
  resources,
  onEdit,
  onDelete,
  onViewLogs,
  onActionError,
}: ProjectTileProps): JSX.Element {
  const [busy, setBusy] = useState(false);

  const isRunning = project.status === 'launched' || project.status === 'stopping';
  const isTransitioning = project.status === 'launching' || project.status === 'stopping';

  async function run(action: () => Promise<unknown>): Promise<void> {
    setBusy(true);
    try {
      await action();
    } catch (err) {
      onActionError?.(project, err as Error);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className='flex min-h-[200px] flex-col gap-4 p-6'>
      <header className='flex items-start justify-between gap-3'>
        <div className='min-w-0'>
          <h3 className='truncate text-lg font-semibold tracking-tight'>{project.name}</h3>
          <p className='mt-1 break-all font-mono text-xs text-muted-foreground'>{project.path}</p>
        </div>
        <StatusBadge status={project.status} />
      </header>

      {project.description && (
        <p className='text-sm text-muted-foreground'>{project.description}</p>
      )}

      <dl className='grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs'>
        <dt className='font-mono text-muted-foreground'>cmd</dt>
        <dd className='break-all font-mono text-secondary-foreground'>{project.launch_cmd}</dd>
        {project.expected_port !== null && (
          <>
            <dt className='font-mono text-muted-foreground'>port</dt>
            <dd className='font-mono text-secondary-foreground'>{project.expected_port}</dd>
          </>
        )}
        <dt className='font-mono text-muted-foreground'>updated</dt>
        <dd className='font-mono text-secondary-foreground'>
          {project.status === 'launched'
            ? `running ${formatUptime(project.last_transition_at)}`
            : formatLocal(project.last_transition_at, 'short')}
        </dd>
        {project.status === 'launched' && resources && (
          <>
            <dt className='font-mono text-muted-foreground'>cpu / ram</dt>
            <dd className='font-mono text-secondary-foreground'>
              {resources.cpu_percent.toFixed(1)}% &middot; {resources.rss_mb.toFixed(0)} MB
            </dd>
          </>
        )}
      </dl>

      {project.last_error && (
        <p
          role='alert'
          className='rounded-sm border border-destructive bg-destructive/10 px-3 py-2 font-mono text-xs text-destructive'
        >
          [{project.last_error.code}] {project.last_error.message}
        </p>
      )}

      <div className='mt-auto flex flex-col gap-2'>
        <div className='flex flex-wrap gap-2'>
          {isRunning ? (
            <Button variant='destructive' size='sm' disabled={busy || isTransitioning} onClick={() => run(() => stopProject(project.id))}>
              {project.status === 'stopping' ? 'Stopping…' : 'Stop'}
            </Button>
          ) : (
            <Button size='sm' disabled={busy || isTransitioning} onClick={() => run(() => launchProject(project.id))}>
              {project.status === 'launching' ? 'Launching…' : 'Launch'}
            </Button>
          )}
          <Button variant='outline' size='sm' onClick={() => onEdit(project)}>
            Edit
          </Button>
          <Button variant='outline' size='sm' onClick={() => onViewLogs(project)}>
            Logs
          </Button>
          <Button
            variant='ghost'
            size='sm'
            disabled={isRunning || isTransitioning}
            title={isRunning ? 'Stop the project before deleting.' : 'Delete'}
            onClick={() => onDelete(project)}
          >
            Delete
          </Button>
        </div>
        <div className='flex flex-wrap gap-1'>
          <Button
            variant='ghost'
            size='sm'
            className='h-7 px-2 text-xs text-muted-foreground'
            onClick={() => void openExternal(project.path)}
          >
            <FolderOpen className='h-3.5 w-3.5' /> Open folder
          </Button>
          {project.expected_port !== null && (
            <Button
              variant='ghost'
              size='sm'
              className='h-7 px-2 text-xs text-muted-foreground'
              onClick={() => void openExternal(`http://localhost:${project.expected_port}`)}
            >
              <Globe className='h-3.5 w-3.5' /> Open in browser
            </Button>
          )}
        </div>
      </div>
    </Card>
  );
}
