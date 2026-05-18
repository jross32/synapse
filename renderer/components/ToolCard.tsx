// Generic, manifest-driven tool card (Milestone F · v0.1.9).
//
// One component renders every tool: it reads the manifest's fields + actions
// and the live ToolState. No tool-specific UI code -- a new tool is a folder
// + a manifest, never a renderer change. `public_url` in a tool's result is
// the one value rendered specially (as an openable link).

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

import type { ToolAction, ToolEntry, ToolField } from '@shared/generated-types';
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
    const prior = entry.state.fields?.[f.key];
    const fallback = f.default;
    const seed = prior ?? fallback;
    values[f.key] = seed === undefined || seed === null ? '' : String(seed);
  }
  return values;
}

export interface ToolCardProps {
  entry: ToolEntry;
  onChanged?: (entry: ToolEntry) => void;
}

export function ToolCard({ entry: initial, onChanged }: ToolCardProps): JSX.Element {
  const [entry, setEntry] = useState<ToolEntry>(initial);
  const [fields, setFields] = useState<Record<string, string>>(() => initialFields(initial));
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const { manifest, state } = entry;
  const Icon = ICONS[manifest.icon] ?? Wrench;
  const publicUrl = typeof state.result.public_url === 'string' ? state.result.public_url : null;

  function coerce(field: ToolField, raw: string): unknown {
    if (field.type === 'number') return raw === '' ? null : Number(raw);
    if (field.type === 'boolean') return raw === 'true';
    return raw;
  }

  async function handleAction(action: ToolAction): Promise<void> {
    setBusyAction(action.id);
    setActionError(null);
    const payload: Record<string, unknown> = {};
    for (const f of manifest.fields) payload[f.key] = coerce(f, fields[f.key] ?? '');
    try {
      const next = await runToolAction(manifest.id, action.id, payload);
      setEntry(next);
      onChanged?.(next);
    } catch (err) {
      setActionError((err as Error).message || 'Action failed');
    } finally {
      setBusyAction(null);
    }
  }

  async function copyUrl(): Promise<void> {
    if (!publicUrl) return;
    try {
      await navigator.clipboard.writeText(publicUrl);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard blocked -- ignore */
    }
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
                disabled={!manifest.runnable || busyAction !== null}
                onChange={(e) =>
                  setFields((prev) => ({ ...prev, [f.key]: e.target.value }))
                }
              />
              {f.help && <span className='text-xs text-muted-foreground'>{f.help}</span>}
            </label>
          ))}
        </div>
      )}

      {publicUrl && (
        <div className='flex flex-col gap-1 rounded-md border border-border bg-secondary/50 p-3'>
          <span className='text-xs font-medium text-muted-foreground'>Public URL</span>
          <div className='flex items-center gap-2'>
            <button
              type='button'
              onClick={() => void openExternal(publicUrl)}
              className='flex min-w-0 items-center gap-1.5 font-mono text-sm text-primary hover:underline'
            >
              <ExternalLink className='h-3.5 w-3.5 shrink-0' />
              <span className='truncate'>{publicUrl}</span>
            </button>
            <Button variant='ghost' size='sm' className='h-7 shrink-0 px-2' onClick={copyUrl}>
              {copied ? <Check className='h-3.5 w-3.5' /> : <Copy className='h-3.5 w-3.5' />}
            </Button>
          </div>
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
        {manifest.actions.map((a) => {
          // available_in empty = always enabled; otherwise the action is only
          // live in the listed statuses (e.g. can't "Open tunnel" when one is
          // already open).
          const wrongState =
            a.available_in.length > 0 && !a.available_in.includes(state.status);
          return (
            <Button
              key={a.id}
              size='sm'
              variant={a.danger ? 'destructive' : a.primary ? 'default' : 'outline'}
              disabled={!manifest.runnable || busyAction !== null || wrongState}
              onClick={() => void handleAction(a)}
            >
              {busyAction === a.id && <Loader2 className='h-4 w-4 animate-spin' />}
              {a.label}
            </Button>
          );
        })}
      </div>
    </Card>
  );
}
