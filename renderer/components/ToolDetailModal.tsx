// Tool detail modal (v0.1.36).
//
// Click the (i) icon on a ToolCard header to open. Surfaces the
// manifest in a more discoverable way: what the tool does, when to
// use it, who ships it, what actions it exposes (and what each
// action's primitive is so the AI knows whether it'll spawn a
// process, open a URL, etc.).

import {
  Boxes,
  Hash,
  Info,
  Package,
  Sparkles,
  Wrench,
} from 'lucide-react';

import type { ToolEntry } from '@shared/generated-types';
import { Badge } from './ui/badge';
import { Button } from './ui/button';
import { Modal } from './ui/modal';
import { StatusBadge } from './StatusBadge';

export interface ToolDetailModalProps {
  open: boolean;
  entry: ToolEntry | null;
  onClose: () => void;
}

const PRIMITIVE_HINT: Record<string, { label: string; meaning: string }> = {
  'url.open': {
    label: 'Opens a URL',
    meaning: 'Opens the result in your default browser. Safe.',
  },
  'process.spawn': {
    label: 'Runs a one-shot command',
    meaning:
      'Spawns a subprocess with the configured argv, captures its output, and returns it. No shell. Timeout caps at 30 s.',
  },
  'pty.spawn': {
    label: 'Opens a terminal session',
    meaning:
      'Spawns the configured argv inside a real PTY and hands you a Sessions tab. Use this for interactive coders / shells.',
  },
};

export function ToolDetailModal({
  open,
  entry,
  onClose,
}: ToolDetailModalProps): JSX.Element | null {
  if (!open || !entry) return null;
  const { manifest, state } = entry;
  const toolActions = manifest.actions.filter((a) => a.scope === 'tool');
  const itemActions = manifest.actions.filter((a) => a.scope === 'item');

  return (
    <Modal
      open
      onClose={onClose}
      labelledBy='tool-detail-title'
      className='max-w-3xl'
    >
      {/* Hero */}
      <div className='flex flex-col gap-2'>
        <div className='flex flex-wrap items-start justify-between gap-3'>
          <div className='flex items-center gap-3'>
            <div className='flex h-12 w-12 items-center justify-center rounded-lg bg-secondary'>
              <Wrench className='h-6 w-6 text-primary' aria-hidden='true' />
            </div>
            <div>
              <h2
                id='tool-detail-title'
                className='text-2xl font-semibold tracking-tight'
              >
                {manifest.name}
              </h2>
              <p className='font-mono text-xs text-muted-foreground'>
                {manifest.id} · v{manifest.version}
              </p>
            </div>
          </div>
          <StatusBadge status={state.status} />
        </div>
        <p className='text-sm text-muted-foreground'>{manifest.description}</p>
      </div>

      {/* What it does */}
      <div className='grid grid-cols-1 gap-3 sm:grid-cols-2'>
        <DetailCard
          icon={<Info className='h-3.5 w-3.5' aria-hidden='true' />}
          title='When to use'
        >
          <p className='text-xs text-muted-foreground'>
            {manifest.runnable
              ? toolActions.length > 0
                ? `Click "${toolActions[0].label}" to run.`
                : 'Reactive tool — runs in response to events.'
              : 'No handler in this build; this manifest is read-only here.'}
          </p>
        </DetailCard>

        <DetailCard
          icon={<Package className='h-3.5 w-3.5' aria-hidden='true' />}
          title='Manifest'
        >
          <ul className='space-y-1 text-xs text-muted-foreground'>
            <li>
              Icon: <span className='font-mono'>{manifest.icon}</span>
            </li>
            <li>
              Actions: <span className='font-mono'>{manifest.actions.length}</span>
            </li>
            <li>
              Fields: <span className='font-mono'>{manifest.fields.length}</span>
            </li>
          </ul>
        </DetailCard>
      </div>

      {/* Actions surface */}
      {(toolActions.length > 0 || itemActions.length > 0) && (
        <div>
          <h3 className='mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground'>
            Actions
          </h3>
          <ul className='flex flex-col gap-2'>
            {[...toolActions, ...itemActions].map((a) => {
              const prim = a.primitive
                ? PRIMITIVE_HINT[a.primitive]
                : undefined;
              return (
                <li
                  key={a.id}
                  className='rounded-md border border-border bg-secondary/30 p-3 text-xs'
                >
                  <div className='flex items-center justify-between gap-2'>
                    <span className='font-medium text-foreground'>
                      {a.label}
                    </span>
                    <div className='flex items-center gap-1'>
                      {a.danger && (
                        <Badge variant='destructive' className='text-[10px]'>
                          destructive
                        </Badge>
                      )}
                      {a.scope === 'item' && (
                        <Badge variant='secondary' className='text-[10px]'>
                          per-item
                        </Badge>
                      )}
                      {a.primitive && (
                        <Badge variant='secondary' className='font-mono text-[10px]'>
                          {a.primitive}
                        </Badge>
                      )}
                    </div>
                  </div>
                  {prim && (
                    <p className='mt-1 text-muted-foreground'>
                      <strong className='text-foreground'>{prim.label}.</strong>{' '}
                      {prim.meaning}
                    </p>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {/* AI lens */}
      <div className='rounded-md border border-dashed border-border bg-secondary/30 p-3 text-xs text-muted-foreground'>
        <p className='mb-1 flex items-center gap-1.5 font-semibold text-foreground'>
          <Sparkles className='h-3.5 w-3.5 text-primary' aria-hidden='true' />
          What a Claude / Codex session sees
        </p>
        <p>
          This tool is at <code className='font-mono'>/api/v1/tools/{manifest.id}</code>.
          Run an action with{' '}
          <code className='font-mono'>POST /api/v1/tools/{manifest.id}/run/&lt;action_id&gt;</code>{' '}
          and a JSON body of field values. The AI's compact
          orientation digest at <code className='font-mono'>/api/v1/ai/context</code>{' '}
          lists this tool alongside the others.
        </p>
      </div>

      {/* Power-user JSON dump */}
      <details className='rounded-md border border-border bg-secondary/30 p-2 text-xs'>
        <summary className='cursor-pointer text-muted-foreground'>
          <Hash className='mr-1 inline h-3 w-3' aria-hidden='true' />
          Raw manifest JSON
        </summary>
        <pre className='mt-2 max-h-48 overflow-auto rounded bg-card p-2 font-mono text-[11px]'>
          {JSON.stringify(manifest, null, 2)}
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

function DetailCard({
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
