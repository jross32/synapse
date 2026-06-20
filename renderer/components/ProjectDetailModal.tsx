// Project detail modal (v0.1.36) — opens when the user clicks
// anywhere on a ProjectTile body (not on the action buttons). Bigger
// canvas to surface everything we know about the project, useful for
// both the human user and a Claude / Codex session reading the page.
//
// Layout: hero strip with name + status + kind chip, then three
// columns: meta (cmd / port / size / uptime), live resources (CPU /
// RAM if running), and tags + group. Below the columns: description,
// followed by a "What the AI sees" section that reproduces what
// /api/v1/ai/context exposes for this project — gives the user a
// concrete sense of how the AI uses the data.

import { useEffect, useState } from 'react';
import {
  Activity,
  Boxes,
  Code2,
  Cpu,
  ExternalLink,
  FolderOpen,
  HardDrive,
  Hash,
  Pin,
  Tag,
} from 'lucide-react';

import {
  type ProjectDiskUsage,
  getProjectDiskUsage,
} from '@shared/projects-client';
import { projectBrowserUrl } from '@shared/browser-runtime';
import type { Project, ResourceSnapshot } from '@shared/generated-types';
import { formatLocal, formatUptime } from '@shared/format-time';
import { openExternal } from '@shared/electron-bridge';
import { kindMeta } from '@shared/project-kinds';
import { cn } from '@shared/utils';
import { Badge } from './ui/badge';
import { Button } from './ui/button';
import { Modal } from './ui/modal';
import { StatusBadge } from './StatusBadge';

export interface ProjectDetailModalProps {
  open: boolean;
  project: Project | null;
  resources?: ResourceSnapshot;
  onClose: () => void;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

export function ProjectDetailModal({
  open,
  project,
  resources,
  onClose,
}: ProjectDetailModalProps): JSX.Element | null {
  const [disk, setDisk] = useState<ProjectDiskUsage | null>(null);

  useEffect(() => {
    if (!open || !project) {
      setDisk(null);
      return;
    }
    let cancelled = false;
    void getProjectDiskUsage(project.id)
      .then((u) => !cancelled && setDisk(u))
      .catch(() => !cancelled && setDisk(null));
    return () => {
      cancelled = true;
    };
  }, [open, project]);

  if (!open || !project) return null;

  const km = kindMeta(project.kind);
  const KindIcon = km.icon;
  const browserUrl = projectBrowserUrl(project.expected_port);

  return (
    <Modal
      open
      onClose={onClose}
      labelledBy='project-detail-title'
      className='max-w-3xl'
    >
      {/* Hero strip */}
      <div className='flex flex-col gap-2'>
        <div className='flex items-center gap-2 text-xs text-muted-foreground'>
          <KindIcon className='h-3.5 w-3.5' aria-hidden='true' />
          <span>{km.label}</span>
          {project.pinned && (
            <>
              <span>·</span>
              <span className='inline-flex items-center gap-1 text-primary'>
                <Pin className='h-3 w-3 fill-current' aria-hidden='true' /> Pinned
              </span>
            </>
          )}
        </div>
        <div className='flex flex-wrap items-center justify-between gap-2'>
          <h2
            id='project-detail-title'
            className='text-2xl font-semibold tracking-tight'
          >
            {project.name}
          </h2>
          <StatusBadge status={project.status} />
        </div>
        <p className='break-all font-mono text-xs text-muted-foreground'>
          {project.id}
          <span className='mx-1.5'>·</span>
          {project.path}
        </p>
      </div>

      {/* Three column meta */}
      <div className='grid grid-cols-1 gap-3 sm:grid-cols-3'>
        <DetailColumn
          icon={<Code2 className='h-3.5 w-3.5' aria-hidden='true' />}
          title='Launch'
        >
          <div className='font-mono text-xs'>{project.launch_cmd}</div>
          {project.expected_port !== null && (
            <div className='mt-1'>
              {browserUrl ? (
                <button
                  type='button'
                  onClick={() => project.status === 'launched' && void openExternal(browserUrl)}
                  disabled={project.status !== 'launched'}
                  className={cn(
                    'flex items-center gap-1 font-mono text-xs',
                    project.status === 'launched'
                      ? 'text-primary hover:underline'
                      : 'text-muted-foreground'
                  )}
                >
                  <ExternalLink className='h-3 w-3' aria-hidden='true' />
                  {browserUrl.replace(/^https?:\/\//, '')}
                </button>
              ) : (
                <div className='font-mono text-xs text-muted-foreground'>
                  WAN needs tunnel for port {project.expected_port}
                </div>
              )}
            </div>
          )}
        </DetailColumn>

        <DetailColumn
          icon={<HardDrive className='h-3.5 w-3.5' aria-hidden='true' />}
          title='On disk'
        >
          {disk ? (
            <>
              <div className='font-mono text-sm text-foreground'>
                {formatBytes(disk.bytes)}
                {disk.truncated ? '+' : ''}
              </div>
              <div className='font-mono text-[11px] text-muted-foreground'>
                {disk.file_count.toLocaleString()} files
                {disk.truncated && ' (walk truncated)'}
              </div>
            </>
          ) : (
            <span className='text-xs text-muted-foreground'>—</span>
          )}
        </DetailColumn>

        <DetailColumn
          icon={<Activity className='h-3.5 w-3.5' aria-hidden='true' />}
          title='Activity'
        >
          <div className='font-mono text-xs'>
            {project.status === 'launched'
              ? `up ${formatUptime(project.last_transition_at)}`
              : `idle since ${formatLocal(project.last_transition_at, 'short')}`}
          </div>
          {project.status === 'launched' && resources && (
            <div className='mt-1 flex items-center gap-1 font-mono text-[11px] text-muted-foreground'>
              <Cpu className='h-3 w-3' aria-hidden='true' />
              {resources.cpu_percent.toFixed(1)}% · {resources.rss_mb.toFixed(0)} MB
            </div>
          )}
        </DetailColumn>
      </div>

      {/* Group + tags */}
      {(project.group || (project.tags && project.tags.length > 0)) && (
        <div className='flex flex-wrap items-center gap-2'>
          {project.group && (
            <Badge variant='secondary' className='gap-1'>
              <FolderOpen className='h-3 w-3' aria-hidden='true' />
              {project.group}
            </Badge>
          )}
          {project.tags?.map((tag) => (
            <Badge key={tag} variant='secondary' className='gap-1'>
              <Tag className='h-3 w-3' aria-hidden='true' />
              {tag}
            </Badge>
          ))}
        </div>
      )}

      {/* Description */}
      {project.description && (
        <div>
          <h3 className='mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground'>
            Description
          </h3>
          <p className='text-sm'>{project.description}</p>
        </div>
      )}

      {/* AI lens */}
      <div className='rounded-md border border-dashed border-border bg-secondary/30 p-3 text-xs text-muted-foreground'>
        <p className='mb-1 flex items-center gap-1.5 font-semibold text-foreground'>
          <Boxes className='h-3.5 w-3.5 text-primary' aria-hidden='true' />
          What a Claude / Codex session sees
        </p>
        <p>
          The daemon exposes this project at{' '}
          <code className='font-mono'>/api/v1/projects/{project.id}</code>.
          Live resources stream over WS as{' '}
          <code className='font-mono'>v1.process.heartbeat</code>. Any
          session opened in workbench mode inherits{' '}
          <code className='font-mono'>$SYNAPSE_PROJECT_ID</code> and{' '}
          <code className='font-mono'>$SYNAPSE_FILES</code> so the AI
          can {project.expected_port !== null ? `curl localhost:${project.expected_port} ` : 'curl the daemon '}
          + read uploaded files directly.
        </p>
      </div>

      {/* Footer: schema dump for power users + AI */}
      <details className='rounded-md border border-border bg-secondary/30 p-2 text-xs'>
        <summary className='cursor-pointer text-muted-foreground'>
          <Hash className='mr-1 inline h-3 w-3' aria-hidden='true' />
          Raw project JSON
        </summary>
        <pre className='mt-2 max-h-48 overflow-auto rounded bg-card p-2 font-mono text-[11px]'>
          {JSON.stringify(project, null, 2)}
        </pre>
      </details>

      <div className='flex justify-end'>
        <Button variant='outline' onClick={onClose} aria-label='Close'>
          Close
        </Button>
      </div>
    </Modal>
  );
}

function DetailColumn({
  icon,
  title,
  children,
}: {
  icon: React.ReactNode;
  title: string;
  children: React.ReactNode;
}): JSX.Element {
  return (
    <div className='rounded-md border border-border bg-secondary/30 p-3'>
      <div className='mb-1 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground'>
        {icon}
        {title}
      </div>
      {children}
    </div>
  );
}
