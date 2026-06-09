// Generic, manifest-driven tool card (Milestone F · v0.1.9, multi-instance v0.1.9.5).
//
// One component renders every tool: it reads the manifest's fields + actions
// and the live ToolState. `tool`-scoped actions are the card's own buttons;
// `item`-scoped actions render once per live instance (e.g. one Cloudtap
// tunnel) with that instance's id. No tool-specific UI code -- a new tool is
// a folder + a manifest, never a renderer change.

import { useState } from 'react';
import {
  Check,
  Cloud,
  Copy,
  ExternalLink,
  Loader2,
  TerminalSquare,
  Wrench,
} from 'lucide-react';

import type {
  ToolAction,
  ToolEntry,
  ToolField,
  ToolItem,
} from '@shared/generated-types';
import { runToolAction } from '@shared/tools-client';
import { openExternal } from '@shared/electron-bridge';
import { Badge } from './ui/badge';
import { Button } from './ui/button';
import { Card } from './ui/card';
import { Input } from './ui/input';
import { StatusBadge } from './StatusBadge';

const ICONS: Record<string, typeof Wrench> = {
  cloud: Cloud,
  wrench: Wrench,
  terminal: TerminalSquare,
};

function initialFields(entry: ToolEntry): Record<string, string> {
  const values: Record<string, string> = {};
  for (const f of entry.manifest.fields) {
    const seed = f.default;
    values[f.key] = seed === undefined || seed === null ? '' : String(seed);
  }
  return values;
}

/** Renders a `public_url` result value as an openable + copyable link. */
function PublicUrl({ url }: { url: string }): JSX.Element {
  const [copied, setCopied] = useState(false);
  async function copy(): Promise<void> {
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard blocked -- ignore */
    }
  }
  return (
    <div className='flex items-center gap-2'>
      <button
        type='button'
        onClick={() => void openExternal(url)}
        className='flex min-w-0 items-center gap-1.5 font-mono text-sm text-primary hover:underline'
      >
        <ExternalLink className='h-3.5 w-3.5 shrink-0' />
        <span className='truncate'>{url}</span>
      </button>
      <Button variant='ghost' size='sm' className='h-7 shrink-0 px-2' onClick={copy}>
        {copied ? <Check className='h-3.5 w-3.5' /> : <Copy className='h-3.5 w-3.5' />}
      </Button>
    </div>
  );
}

export interface ToolCardProps {
  entry: ToolEntry;
  onChanged?: (entry: ToolEntry) => void;
}

export function ToolCard({ entry: initial, onChanged }: ToolCardProps): JSX.Element {
  const [entry, setEntry] = useState<ToolEntry>(initial);
  const [fields, setFields] = useState<Record<string, string>>(() => initialFields(initial));
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const { manifest, state } = entry;
  const Icon = ICONS[manifest.icon] ?? Wrench;
  const toolActions = manifest.actions.filter((a) => a.scope === 'tool');
  const itemActions = manifest.actions.filter((a) => a.scope === 'item');
  const toolUrl = typeof state.result.public_url === 'string' ? state.result.public_url : null;
  // pty.spawn primitive (v0.1.27) stamps a session_id on the tool state when
  // the action launches a terminal session. We surface it as "Open in
  // Sessions" so the user lands on the live xterm tab in one click.
  const sessionId =
    typeof state.result.session_id === 'string' ? state.result.session_id : null;

  function coerce(field: ToolField, raw: string): unknown {
    if (field.type === 'number') return raw === '' ? null : Number(raw);
    if (field.type === 'boolean') return raw === 'true';
    return raw;
  }

  async function handleAction(action: ToolAction, itemId?: string): Promise<void> {
    const key = itemId ? `${action.id}:${itemId}` : action.id;
    setBusyKey(key);
    setActionError(null);
    const payload: Record<string, unknown> = {};
    for (const f of manifest.fields) payload[f.key] = coerce(f, fields[f.key] ?? '');
    try {
      const next = await runToolAction(manifest.id, action.id, payload, itemId);
      setEntry(next);
      onChanged?.(next);
    } catch (err) {
      setActionError((err as Error).message || 'Action failed');
    } finally {
      setBusyKey(null);
    }
  }

  function actionButton(
    action: ToolAction,
    enabled: boolean,
    itemId?: string
  ): JSX.Element {
    const key = itemId ? `${action.id}:${itemId}` : action.id;
    return (
      <Button
        key={key}
        size='sm'
        variant={action.danger ? 'destructive' : action.primary ? 'default' : 'outline'}
        disabled={!manifest.runnable || busyKey !== null || !enabled}
        onClick={() => void handleAction(action, itemId)}
      >
        {busyKey === key && <Loader2 className='h-4 w-4 animate-spin' />}
        {action.label}
      </Button>
    );
  }

  function renderItem(item: ToolItem): JSX.Element {
    const url = typeof item.result.public_url === 'string' ? item.result.public_url : null;
    const port = item.result.local_port;
    return (
      <div
        key={item.id}
        className='flex flex-col gap-2 rounded-md border border-border bg-secondary/40 p-3'
      >
        <div className='flex items-center justify-between gap-2'>
          <div className='flex min-w-0 items-center gap-2'>
            <span className='truncate font-medium'>{item.label}</span>
            {port !== undefined && port !== null && (
              <Badge variant='outline' className='font-mono text-[10px]'>
                :{String(port)}
              </Badge>
            )}
          </div>
          <StatusBadge status={item.status} />
        </div>
        {url && <PublicUrl url={url} />}
        {item.message && !item.last_error && (
          <p className='text-xs text-muted-foreground'>{item.message}</p>
        )}
        {item.last_error && (
          <p
            role='alert'
            className='rounded-sm border border-destructive bg-destructive/10 px-2 py-1 font-mono text-xs text-destructive'
          >
            [{item.last_error.code}] {item.last_error.message}
          </p>
        )}
        {itemActions.length > 0 && (
          <div className='flex flex-wrap gap-2'>
            {itemActions.map((a) =>
              actionButton(
                a,
                a.available_in.length === 0 || a.available_in.includes(item.status),
                item.id
              )
            )}
          </div>
        )}
      </div>
    );
  }

  return (
    <Card className='flex min-h-[200px] flex-col gap-4 p-6'>
      <header className='flex items-start justify-between gap-3'>
        <div className='flex items-center gap-3'>
          <div className='flex h-10 w-10 items-center justify-center rounded-lg bg-secondary'>
            <Icon className='h-5 w-5 text-primary' />
          </div>
          <div className='min-w-0'>
            <h3 className='truncate text-lg font-semibold tracking-tight'>{manifest.name}</h3>
            <p className='font-mono text-xs text-muted-foreground'>v{manifest.version}</p>
          </div>
        </div>
        <StatusBadge status={state.status} />
      </header>

      <p className='text-sm text-muted-foreground'>{manifest.description}</p>

      {!manifest.runnable && (
        <Badge variant='secondary' className='w-fit'>
          No handler in this build — read-only
        </Badge>
      )}

      {manifest.fields.length > 0 && (
        <div className='flex flex-col gap-3'>
          {manifest.fields.map((f) => (
            <label key={f.key} className='flex flex-col gap-1 text-sm'>
              <span className='font-medium'>
                {f.label}
                {f.required && <span className='ml-1 text-destructive'>*</span>}
              </span>
              <Input
                type={f.type === 'number' ? 'number' : 'text'}
                value={fields[f.key] ?? ''}
                min={f.min ?? undefined}
                max={f.max ?? undefined}
                placeholder={f.placeholder ?? undefined}
                disabled={!manifest.runnable || busyKey !== null}
                onChange={(e) =>
                  setFields((prev) => ({ ...prev, [f.key]: e.target.value }))
                }
              />
              {f.help && <span className='text-xs text-muted-foreground'>{f.help}</span>}
            </label>
          ))}
        </div>
      )}

      {/* Tool-level result link (single-shot tools). Multi-instance tools use items. */}
      {toolUrl && (
        <div className='flex flex-col gap-1 rounded-md border border-border bg-secondary/50 p-3'>
          <span className='text-xs font-medium text-muted-foreground'>Public URL</span>
          <PublicUrl url={toolUrl} />
        </div>
      )}

      {/* PTY session deep link (v0.1.27). Fires a global event the App shell
          listens for so we can switch pages without coupling ToolCard to the
          nav model. */}
      {sessionId && (
        <div className='flex flex-col gap-2 rounded-md border border-border bg-secondary/50 p-3'>
          <span className='text-xs font-medium text-muted-foreground'>
            Session opened
          </span>
          <div className='flex items-center justify-between gap-2'>
            <span className='truncate font-mono text-xs'>{sessionId}</span>
            <Button
              size='sm'
              onClick={() =>
                window.dispatchEvent(
                  new CustomEvent('synapse:open-session', { detail: { sessionId } })
                )
              }
            >
              Open in Sessions
            </Button>
          </div>
        </div>
      )}

      {/* Live instances (e.g. Cloudtap tunnels). */}
      {state.items.length > 0 && (
        <div className='flex flex-col gap-2'>
          <span className='text-xs font-medium text-muted-foreground'>
            Active ({state.items.length})
          </span>
          {state.items.map(renderItem)}
        </div>
      )}

      {state.message && !state.last_error && (
        <p className='text-xs text-muted-foreground'>{state.message}</p>
      )}

      {state.last_error && (
        <p
          role='alert'
          className='rounded-sm border border-destructive bg-destructive/10 px-3 py-2 font-mono text-xs text-destructive'
        >
          [{state.last_error.code}] {state.last_error.message}
        </p>
      )}

      {actionError && (
        <p role='alert' className='text-sm text-destructive'>
          {actionError}
        </p>
      )}

      <div className='mt-auto flex flex-wrap gap-2'>
        {toolActions.map((a) =>
          actionButton(
            a,
            a.available_in.length === 0 || a.available_in.includes(state.status)
          )
        )}
      </div>
    </Card>
  );
}
