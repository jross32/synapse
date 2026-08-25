// One project tile (Milestones D/E/F, compacted v0.1.188) -- shadcn Card surface.
//
// Deliberately SHORT: name + path + status + the two actions people reach for
// constantly (Launch/Stop, Open in browser). Everything else this used to show
// inline -- cmd, port, disk size, cpu/ram, description, kind/group/tags, the
// full OS-integration button row (Edit/Logs/Delete/Open folder/VS Code/
// Terminal/AI OS/Workbench/Files) -- moved into ProjectDetailModal, which
// already opens on a click anywhere on the card body. A grid of a dozen tall
// cards used to force endless scrolling to see all your apps at a glance;
// this trades that for "quick actions visible, everything else one click
// away", the same shape as ProjectDetailModal already used for the "what the
// AI sees" / raw-JSON detail nobody needs visible by default.

import { useState } from 'react';
import { ChevronRight, Globe, Pin } from 'lucide-react';

import { projectBrowserUrl } from '@shared/browser-runtime';
import { openProjectInAiOs } from '@shared/ai-cases-client';
import { launchProject, patchProject, stopProject } from '@shared/projects-client';
import type { Project, ResourceSnapshot } from '@shared/generated-types';
import {
  canOpenInTerminal,
  canOpenInVscode,
  hasElectronBridge,
  openExternal,
  openInTerminal,
  openInVscode,
} from '@shared/electron-bridge';
import { openProjectWorkbench } from '@shared/workbench-client';
import { cn } from '@shared/utils';
import { Button } from './ui/button';
import { Card } from './ui/card';
import { Modal } from './ui/modal';
import { FilesPanel } from './FilesPanel';
import { ProjectDetailModal } from './ProjectDetailModal';
import { StatusBadge } from './StatusBadge';

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
  const [detailOpen, setDetailOpen] = useState(false);
  const [filesOpen, setFilesOpen] = useState(false);

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

  async function handleOpenInAiOs(): Promise<void> {
    try {
      const launch = await openProjectInAiOs(project.id);
      await openExternal(launch.url);
    } catch (err) {
      onActionError?.(project, err as Error);
    }
  }

  return (
    <Card
      className='group flex cursor-pointer flex-col gap-3 p-4 transition-colors hover:border-primary'
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
      <div className='flex items-start justify-between gap-3'>
        <div className='min-w-0'>
          <div className='flex items-center gap-2'>
            <h3 className='truncate text-base font-semibold tracking-tight'>{project.name}</h3>
            <StatusBadge status={project.status} />
          </div>
          <p className='mt-0.5 truncate font-mono text-xs text-muted-foreground'>{project.path}</p>
        </div>
        <div className='flex shrink-0 items-center gap-1'>
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
          <ChevronRight
            className='h-4 w-4 text-muted-foreground transition-transform group-hover:translate-x-0.5'
            aria-hidden='true'
          />
        </div>
      </div>

      {project.last_error && (
        <p
          role='alert'
          className='truncate rounded-sm border border-destructive bg-destructive/10 px-2 py-1 font-mono text-[11px] text-destructive'
          title={`[${project.last_error.code}] ${project.last_error.message}`}
        >
          [{project.last_error.code}] {project.last_error.message}
        </p>
      )}

      <div
        className='flex flex-wrap gap-2'
        onClick={(e) => e.stopPropagation()}
        onKeyDown={(e) => e.stopPropagation()}
      >
        {isRunning ? (
          <Button variant='destructive' size='sm' disabled={busy || isTransitioning} onClick={() => run(() => stopProject(project.id))}>
            {project.status === 'stopping' ? 'Stopping…' : 'Stop'}
          </Button>
        ) : (
          <Button size='sm' disabled={busy || isTransitioning} onClick={() => run(() => launchProject(project.id))}>
            {project.status === 'launching' ? 'Launching…' : 'Launch'}
          </Button>
        )}
        <Button
          variant='outline'
          size='sm'
          disabled={project.expected_port === null || project.status !== 'launched' || browserUrl === null}
          title={
            project.expected_port === null
              ? 'No expected port set for this project -- open its details and Edit to set one, then this button will work.'
              : project.status !== 'launched'
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
      </div>

      <ProjectDetailModal
        open={detailOpen}
        project={detailOpen ? project : null}
        resources={resources}
        onClose={() => setDetailOpen(false)}
        onEdit={() => {
          setDetailOpen(false);
          onEdit(project);
        }}
        onDelete={() => {
          setDetailOpen(false);
          onDelete(project);
        }}
        onViewLogs={() => {
          setDetailOpen(false);
          onViewLogs(project);
        }}
        onOpenFolder={desktopBridge ? () => void openExternal(project.path) : undefined}
        onOpenInVscode={canOpenInVscode() ? handleOpenInVscode : undefined}
        onOpenInTerminal={canOpenInTerminal() ? handleOpenInTerminal : undefined}
        onOpenInAiOs={handleOpenInAiOs}
        onOpenInWorkbench={handleOpenInWorkbench}
        onOpenFiles={() => setFilesOpen(true)}
        isRunning={isRunning}
        isTransitioning={isTransitioning}
      />

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
    </Card>
  );
}
