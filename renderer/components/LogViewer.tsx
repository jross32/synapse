// Log viewer (Contract #3) -- shows the tail of a project's most recent log
// file. Polls GET /api/v1/projects/{id}/logs while open so output stays fresh.

import { useCallback, useEffect, useRef, useState } from 'react';
import { Bot, Loader2, RefreshCw } from 'lucide-react';

import { getProjectLogs, type ProjectLogs } from '@shared/projects-client';
import { askAssistant, getAssistantStatus } from '@shared/assistant-client';
import type { Project } from '@shared/generated-types';
import { Button } from './ui/button';
import { Modal } from './ui/modal';

const ERROR_RE = /error|warn|exception|traceback|fail|fatal|panic/i;

/** Pick the most relevant log lines to hand the assistant: error/warn lines if
 *  any, otherwise the tail. Capped so the prompt stays small. */
function errorSnippet(lines: string[], cap = 40): string {
  const flagged = lines.filter((l) => ERROR_RE.test(l));
  const chosen = (flagged.length > 0 ? flagged : lines).slice(-cap);
  return chosen.join('\n');
}

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
  // "Explain with AI" -- only offered when the local assistant is on + ready.
  const [aiReady, setAiReady] = useState(false);
  const [explaining, setExplaining] = useState(false);
  const [explanation, setExplanation] = useState<string | null>(null);
  const [aiError, setAiError] = useState<string | null>(null);

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

  // Decide whether to offer the AI explainer (assistant on + a model installed).
  useEffect(() => {
    if (!open) return;
    setExplanation(null);
    setAiError(null);
    getAssistantStatus()
      .then((s) => setAiReady(s.installed && s.enabled && s.server_up && s.models.length > 0))
      .catch(() => setAiReady(false));
  }, [open, project]);

  const explain = useCallback(async () => {
    if (!project || !logs || logs.lines.length === 0) return;
    setExplaining(true);
    setAiError(null);
    setExplanation(null);
    try {
      const snippet = errorSnippet(logs.lines);
      const res = await askAssistant({
        content:
          `This is the recent log tail from my project "${project.name}". ` +
          `Explain in plain language what is going wrong (if anything) and suggest a concrete next step. ` +
          `Be brief.\n\n\`\`\`\n${snippet}\n\`\`\``,
        include_context: true,
      });
      setExplanation(res.answer);
    } catch (e) {
      setAiError((e as Error).message || 'The assistant could not answer.');
    } finally {
      setExplaining(false);
    }
  }, [project, logs]);

  if (!project) return null;

  return (
    <Modal open={open} onClose={onClose} labelledBy='log-viewer-title' className='max-w-3xl'>
      <div className='flex items-center justify-between'>
        <h2 id='log-viewer-title' className='text-lg font-semibold'>
          Logs — <span className='font-mono text-base'>{project.name}</span>
        </h2>
        <div className='flex gap-2'>
          {aiReady && (
            <Button
              size='sm'
              onClick={() => void explain()}
              disabled={explaining || !logs || logs.lines.length === 0}
              title='Ask the local assistant to explain these logs'
            >
              {explaining ? <Loader2 className='h-3.5 w-3.5 animate-spin' /> : <Bot className='h-3.5 w-3.5' />}
              Explain with AI
            </Button>
          )}
          <Button variant='outline' size='sm' onClick={() => void fetchLogs()} disabled={loading}>
            <RefreshCw className='h-3.5 w-3.5' /> Refresh
          </Button>
        </div>
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

      {aiError && <p role='alert' className='text-xs text-destructive'>{aiError}</p>}
      {explanation && (
        <div className='flex flex-col gap-1 rounded-md border border-primary/30 bg-primary/5 p-3'>
          <div className='flex items-center gap-1.5 text-xs font-medium text-primary'>
            <Bot className='h-3.5 w-3.5' /> Assistant
          </div>
          <p className='whitespace-pre-wrap text-sm text-foreground'>{explanation}</p>
        </div>
      )}

      <div className='flex justify-end'>
        <Button variant='outline' onClick={onClose}>
          Close
        </Button>
      </div>
    </Modal>
  );
}
