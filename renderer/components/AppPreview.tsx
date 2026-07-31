// App preview pane (ADR-0028 Phase 5) — watch the app an AI is building, live.
//
// Synapse launches real projects on real ports, so the preview iframes the *live
// running app* rather than a sandboxed snapshot: full framework, real backend, real
// data — and it updates as the AI edits (the project's own dev server does the
// reloading). Device widths let you check mobile/tablet without leaving the page.
//
// One-window: this is an openable/closable pane inside Live View, not a new page.
// It owns its own scroll; the page never scrolls.

import { useMemo, useRef, useState } from 'react';
import { ExternalLink, Monitor, RefreshCw, ScrollText, Smartphone, Tablet, X } from 'lucide-react';

import { openExternal } from '@shared/electron-bridge';
import type { Project } from '@shared/generated-types';
import { cn } from '@shared/utils';
import { LogViewer } from './LogViewer';

type DeviceWidth = 'mobile' | 'tablet' | 'desktop';

const DEVICE: Record<DeviceWidth, { label: string; width: number | null; icon: typeof Monitor }> = {
  mobile: { label: 'Mobile (375)', width: 375, icon: Smartphone },
  tablet: { label: 'Tablet (768)', width: 768, icon: Tablet },
  desktop: { label: 'Desktop', width: null, icon: Monitor },
};

/** The live URL for a running project, or null when it isn't previewable. */
export function previewUrl(project: Project | null | undefined): string | null {
  if (!project || project.status !== 'launched' || !project.expected_port) return null;
  return `http://localhost:${project.expected_port}`;
}

export function AppPreview({
  project,
  onClose,
}: {
  project: Project;
  onClose: () => void;
}): JSX.Element {
  const [device, setDevice] = useState<DeviceWidth>('desktop');
  const [nonce, setNonce] = useState(0);
  const [logsOpen, setLogsOpen] = useState(false);
  const frameRef = useRef<HTMLIFrameElement | null>(null);
  const url = useMemo(() => previewUrl(project), [project]);

  return (
    <div className='flex min-h-0 flex-1 flex-col'>
      <div className='flex shrink-0 flex-wrap items-center justify-between gap-2 border-b border-border px-3 py-2'>
        <div className='min-w-0'>
          <p className='truncate text-sm font-semibold'>Preview · {project.name}</p>
          <p className='truncate font-mono text-[11px] text-muted-foreground'>{url}</p>
        </div>
        <div className='flex items-center gap-1'>
          {(Object.keys(DEVICE) as DeviceWidth[]).map((key) => {
            const Icon = DEVICE[key].icon;
            return (
              <button
                key={key}
                type='button'
                onClick={() => setDevice(key)}
                aria-label={DEVICE[key].label}
                title={DEVICE[key].label}
                aria-pressed={device === key}
                className={cn(
                  'rounded p-1.5 text-muted-foreground transition hover:text-foreground',
                  device === key && 'bg-accent text-foreground'
                )}
              >
                <Icon className='h-4 w-4' aria-hidden='true' />
              </button>
            );
          })}
          <span className='mx-1 h-4 w-px bg-border' aria-hidden='true' />
          <button
            type='button'
            onClick={() => setNonce((n) => n + 1)}
            aria-label='Reload preview'
            title='Reload preview'
            className='rounded p-1.5 text-muted-foreground transition hover:text-foreground'
          >
            <RefreshCw className='h-4 w-4' aria-hidden='true' />
          </button>
          <button
            type='button'
            onClick={() => setLogsOpen(true)}
            aria-label='Open logs'
            title='Logs'
            className='rounded p-1.5 text-muted-foreground transition hover:text-foreground'
          >
            <ScrollText className='h-4 w-4' aria-hidden='true' />
          </button>
          {url && (
            <button
              type='button'
              onClick={() => void openExternal(url)}
              aria-label='Open in browser'
              title='Open in browser'
              className='rounded p-1.5 text-muted-foreground transition hover:text-foreground'
            >
              <ExternalLink className='h-4 w-4' aria-hidden='true' />
            </button>
          )}
          <button
            type='button'
            onClick={onClose}
            aria-label='Close preview'
            title='Close preview'
            className='rounded p-1.5 text-muted-foreground transition hover:text-foreground'
          >
            <X className='h-4 w-4' aria-hidden='true' />
          </button>
        </div>
      </div>

      <div className='scrollbar-thin min-h-0 flex-1 overflow-auto bg-secondary/20 p-3'>
        {url ? (
          <div
            className='mx-auto h-full overflow-hidden rounded-lg border border-border bg-background shadow-sm'
            style={DEVICE[device].width ? { width: DEVICE[device].width, maxWidth: '100%' } : undefined}
          >
            <iframe
              ref={frameRef}
              key={`${url}#${nonce}`}
              src={url}
              title={`Live preview of ${project.name}`}
              className='h-full w-full border-0'
            />
          </div>
        ) : (
          <div className='flex h-full items-center justify-center px-4 text-center'>
            <div>
              <p className='text-sm font-medium'>Not running</p>
              <p className='mt-1 text-xs text-muted-foreground'>
                Launch {project.name} (and give it an expected port) to watch it live here.
              </p>
            </div>
          </div>
        )}
      </div>

      <LogViewer open={logsOpen} project={project} onClose={() => setLogsOpen(false)} />
    </div>
  );
}
