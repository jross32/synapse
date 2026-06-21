// One project tile (Milestones D/E/F) -- shadcn Card surface.
//
// Shows name + path + live status, the cmd/port/uptime metadata, a live
// cpu/ram line while running, and the Launch/Stop + Edit/Delete actions.
// A "more actions" row exposes quick OS actions (open folder / browser).

import { useEffect, useState } from 'react';
import { Code2, FolderOpen, Globe, Paperclip, Pin, Sparkles, TerminalSquare } from 'lucide-react';

import { projectBrowserUrl } from '@shared/browser-runtime';
import { getProjectDiskUsage, launchProject, patchProject, stopProject } from '@shared/projects-client';
import type { Project, ResourceSnapshot } from '@shared/generated-types';
import { formatLocal, formatUptime } from '@shared/format-time';
import {
  canOpenInTerminal,
  canOpenInVscode,
  hasElectronBridge,
  openExternal,
  openInTerminal,
  openInVscode,
} from '@shared/electron-bridge';
import { openProjectWorkbench } from '@shared/workbench-client';
import { kindMeta } from '@shared/project-kinds';
import { cn } from '@shared/utils';
import { Badge } from './ui/badge';
import { Button } from './ui/button';
import { Card } from './ui/card';
import { Modal } from './ui/modal';
import { FilesPanel } from './FilesPanel';
import { ProjectDetailModal } from './ProjectDetailModal';
import { StatusBadge } from './StatusBadge';

/** Tile-sized byte formatter. 1 KB / 12 MB / 1.4 GB. */
function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(0)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
}

export interface ProjectTileProps {
  project: Project;
  resources?: ResourceSnapshot;
  onEdit: (project: Project) => void;
  onDelete: (project: Project) => void;
  onViewLogs: (project: Project) => void;
  onChanged?: (project: Project) => void;
  onActionError?: (project: Project, error: Error) => void;
}

export function ProjectTile({
  project,
  resources,
  onEdit,
  onDelete,
  onViewLogs,
  onChanged,
  onActionError,
}: ProjectTileProps): JSX.Element {
  const [busy, setBusy] = useState(false);
  const [filesOpen, setFilesOpen] = useState(false);
  const [detailOpen, setDetailOpen] = useState(false);
  // Disk-usage badge (v0.1.36 A5). Lazy-fetched once per mount;
  // route-side cache keeps re-renders cheap. Empty string = haven't
  // received yet; null = call failed (older daemon or skipped).
  const [diskUsageLabel, setDiskUsageLabel] = useState<string | null>('');

  useEffect(() => {
    let cancelled = false;
    void getProjectDiskUsage(project.id)
      .then((usage) => {
        if (cancelled) return;
        setDiskUsageLabel(formatBytes(usage.bytes) + (usage.truncated ? '+' : ''));
      })
      .catch(() => {
        if (cancelled) return;
        // Pre-v0.1.36 daemon won't have the route. Hide the row silently.
        setDiskUsageLabel(null);
      });
    return () => {
      cancelled = true;
    };
  }, [project.id]);

  const isRunning = project.status === 'launched' || project.status === 'stopping';
  const isTransitioning = project.status === 'launching' || project.status === 'stopping';
  const browserUrl = projectBrowserUrl(project.expected_port);
  const desktopBridge = hasElectronBridge();

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

  async function togglePinned(): Promise<void> {
    try {
      const updated = await patchProject(project.id, { pinned: !project.pinned });
      onChanged?.(updated);
    } catch (err) {
      onActionError?.(project, err as Error);
    }
  }

  async function handleOpenInVscode(): Promise<void> {
    const result = await openInVscode(project.path);
    if (!result.ok && result.error) {
      onActionError?.(project, new Error(result.error));
    }
  }

  async function handleOpenInTerminal(): Promise<void> {
    const result = await openInTerminal(project.path);
    if (!result.ok && result.error) {
      onActionError?.(project, new Error(result.error));
    }
  }

  async function handleOpenInWorkbench(): Promise<void> {
    try {
      const session = await openProjectWorkbench(project.id);
      // Hand off to the Sessions page via the same global event the
      // marketplace deep-link uses (v0.1.27).
      window.dispatchEvent(
        new CustomEvent('synapse:open-session', {
          detail: { sessionId: session.session_id },
        })
      );
    } catch (err) {
      onActionError?.(project, err as Error);
    }
  }

  return (
    <Card
      className='group flex min-h-[200px] cursor-pointer flex-col gap-4 p-6 transition-colors hover:border-primary'
      role='button'
      tabIndex={0}
      onClick={() => setDetailOpen(true)}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          setDetailOpen(true);
        }
      }}
      aria-label={`Open ${project.name} details`}
    >
      <header className='flex items-start justify-between gap-3'>
        <div className='min-w-0'>
          <h3 className='truncate text-lg font-semibold tracking-tight'>{project.name}</h3>
          <p className='mt-1 break-words font-mono text-xs text-muted-foreground'>{project.path}</p>
        </div>
        <div className='flex items-center gap-1.5'>
          <button
            type='button'
            onClick={(e) => {
              e.stopPropagation();
              void togglePinned();
            }}
            title={project.pinned ? 'Unpin' : 'Pin to top'}
            aria-label={project.pinned ? `Unpin ${project.name}` : `Pin ${project.name} to top`}
            aria-pressed={project.pinned}
            className={cn(
              'rounded-md p-1 transition-colors hover:bg-accent',
              project.pinned ? 'text-primary' : 'text-muted-foreground'
            )}
          >
            <Pin className={cn('h-4 w-4', project.pinned && 'fill-current')} aria-hidden='true' />
          </button>
          <StatusBadge status={project.status} />
        </div>
      </header>

      {(() => {
        const km = kindMeta(project.kind);
        const KIcon = km.icon;
        const showRow =
          project.kind !== 'app' || project.group || project.tags.length > 0;
        if (!showRow) return null;
        return (
          <div className='flex flex-wrap items-center gap-1.5'>
            {project.kind !== 'app' && (
              <span
                title={`Kind: ${km.label}`}
                className={cn(
                  'inline-flex items-center gap-1 rounded-full border-transparent px-2 py-0.5 text-[11px] font-medium',
                  km.badgeClass
                )}
              >
                <KIcon className='h-3 w-3' />
                {km.label}
              </span>
            )}
            {project.group && <Badge variant='secondary'>{project.group}</Badge>}
            {project.tags.map((t) => (
              <Badge key={t} variant='outline'>
                {t}
              </Badge>
            ))}
          </div>
        );
      })()}

      {project.description && (
        <p className='text-sm text-muted-foreground'>{project.description}</p>
      )}

      <dl className='grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs'>
        <dt className='font-mono text-muted-foreground'>cmd</dt>
        <dd className='break-words font-mono text-secondary-foreground'>{project.launch_cmd}</dd>
        {project.expected_port !== null && (
          <>
            <dt className='font-mono text-muted-foreground'>port</dt>
            <dd className='font-mono text-secondary-foreground'>{project.expected_port}</dd>
          </>
        )}
        {diskUsageLabel && (
          <>
            <dt className='font-mono text-muted-foreground'>size</dt>
            <dd className='font-mono text-secondary-foreground'>{diskUsageLabel}</dd>
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

      <div
        className='mt-auto flex flex-col gap-2'
        onClick={(e) => e.stopPropagation()}
        onKeyDown={(e) => e.stopPropagation()}
      >
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
          {desktopBridge && (
            <Button
              variant='ghost'
              size='sm'
              className='h-7 px-2 text-xs text-muted-foreground'
              onClick={() => void openExternal(project.path)}
            >
              <FolderOpen className='h-3.5 w-3.5' /> Open folder
            </Button>
          )}
          {canOpenInVscode() && (
            <Button
              variant='ghost'
              size='sm'
              className='h-7 px-2 text-xs text-muted-foreground'
              title='Open this project in VS Code'
              onClick={() => void handleOpenInVscode()}
            >
              <Code2 className='h-3.5 w-3.5' /> Open in VS Code
            </Button>
          )}
          {canOpenInTerminal() && (
            <Button
              variant='ghost'
              size='sm'
              className='h-7 px-2 text-xs text-muted-foreground'
              title='Open a terminal in this project'
              onClick={() => void handleOpenInTerminal()}
            >
              <TerminalSquare className='h-3.5 w-3.5' /> Terminal
            </Button>
          )}
          <Button
            variant='ghost'
            size='sm'
            className='h-7 px-2 text-xs text-muted-foreground'
            title='Open a coder session (claude / codex / shell) pre-cd into this project'
            onClick={() => void handleOpenInWorkbench()}
          >
            <Sparkles className='h-3.5 w-3.5' /> Open in workbench
          </Button>
          <Button
            variant='ghost'
            size='sm'
            className='h-7 px-2 text-xs text-muted-foreground'
            title='Files attached to this project (uploads + session transcripts)'
            onClick={() => setFilesOpen(true)}
          >
            <Paperclip className='h-3.5 w-3.5' /> Files
          </Button>
          {project.expected_port !== null && (
            <Button
              variant='ghost'
              size='sm'
              className='h-7 px-2 text-xs text-muted-foreground'
              disabled={project.status !== 'launched' || browserUrl === null}
              title={
                project.status !== 'launched'
                  ? `Launch ${project.name} first to open it in your browser`
                  : browserUrl
                    ? `Open ${browserUrl}`
                    : 'Open a Cloudtap tunnel for this app port before using it over WAN.'
              }
              aria-label={`Open ${project.name} in browser`}
              onClick={() => browserUrl && void openExternal(browserUrl)}
            >
              <Globe className='h-3.5 w-3.5' aria-hidden='true' /> Open in browser
            </Button>
          )}
        </div>
      </div>

      {filesOpen && (
        <Modal
          open
          onClose={() => setFilesOpen(false)}
          labelledBy={`files-modal-${project.id}`}
          className='!max-w-3xl'
        >
          <h2 id={`files-modal-${project.id}`} className='text-lg font-semibold'>
            Files — {project.name}
          </h2>
          <p className='text-sm text-muted-foreground'>
            Uploads + workbench transcripts. AI sessions launched in a
            workbench see these under{' '}
            <code className='font-mono text-xs'>$SYNAPSE_FILES</code>.
          </p>
          <FilesPanel projectId={project.id} />
        </Modal>
      )}

      <ProjectDetailModal
        open={detailOpen}
        project={detailOpen ? project : null}
        resources={resources}
        onClose={() => setDetailOpen(false)}
      />
    </Card>
  );
}
