// Log viewer (Contract #3) -- shows the tail of a project's most recent log
// file. Polls GET /api/v1/projects/{id}/logs while open so output stays fresh.

import { useCallback, useEffect, useRef, useState } from 'react';
import { RefreshCw } from 'lucide-react';

import { getProjectLogs, type ProjectLogs } from '@shared/projects-client';
import type { Project } from '@shared/generated-types';
import { Button } from './ui/button';
import { Modal } from './ui/modal';

export interface LogViewerProps {
  open: boolean;
  project: Project | null;
  onClose: () => void;
}

const POLL_MS = 2500;

export function LogViewer({ open, project, onClose }: LogViewerProps): JSX.Element | null {
  const [logs, setLogs] = useState<ProjectLogs | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const preRef = useRef<HTMLPreElement | null>(null);

  const fetchLogs = useCallback(async () => {
    if (!project) return;
    setLoading(true);
    try {
      setLogs(await getProjectLogs(project.id, 500));
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, [project]);

  useEffect(() => {
    if (!open || !project) return;
    void fetchLogs();
    const timer = setInterval(() => void fetchLogs(), POLL_MS);
    return () => clearInterval(timer);
  }, [open, project, fetchLogs]);

  // Keep the view pinned to the newest line.
  useEffect(() => {
    if (preRef.current) preRef.current.scrollTop = preRef.current.scrollHeight;
  }, [logs]);

  if (!project) return null;

  return (
    <Modal open={open} onClose={onClose} labelledBy='log-viewer-title' className='max-w-3xl'>
      <div className='flex items-center justify-between'>
        <h2 id='log-viewer-title' className='text-lg font-semibold'>
          Logs — <span className='font-mono text-base'>{project.name}</span>
        </h2>
        <Button variant='outline' size='sm' onClick={() => void fetchLogs()} disabled={loading}>
          <RefreshCw className='h-3.5 w-3.5' /> Refresh
        </Button>
      </div>

      {logs?.log_path && (
        <p className='break-words font-mono text-xs text-muted-foreground'>{logs.log_path}</p>
      )}
      {error && (
        <p role='alert' className='text-sm text-destructive'>
          {error}
        </p>
      )}

      <pre
        ref={preRef}
        className='h-[55vh] overflow-auto rounded-md border border-border bg-background p-4 font-mono text-xs leading-relaxed text-foreground'
      >
        {logs === null
          ? 'Loading…'
          : logs.lines.length === 0
          ? 'No log output yet. Launch the project to generate logs.'
          : logs.lines.join('\n')}
      </pre>

      {logs && logs.total_lines > logs.lines.length && (
        <p className='text-xs text-muted-foreground'>
          Showing the last {logs.lines.length} of {logs.total_lines} lines.
        </p>
      )}

      <div className='flex justify-end'>
        <Button variant='outline' onClick={onClose}>
          Close
        </Button>
      </div>
    </Modal>
  );
}
