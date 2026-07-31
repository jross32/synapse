// Global Notification Center (ADR-0028). A persistent bell — reachable on every
// screen, desktop + mobile — that shows what the AIs driving Synapse are doing:
// a session connected (#001, green/yellow/red), a squad was created, work was
// handed off, an idea was filed to the review inbox.
//
// Built to the one-window standard: the panel is a fixed-height shell whose list
// and detail panes scroll independently (.scrollbar-thin) — the page never scrolls.

import { useEffect, useRef, useState } from 'react';
import { Bell, CheckCheck, ChevronLeft, ExternalLink, X } from 'lucide-react';

import { isMobileRoute } from '@shared/browser-runtime';
import { formatLocal } from '@shared/format-time';
import { useActivity } from '@shared/use-activity';
import type { ActivityLevel, ActivityNotification } from '@shared/activity-client';
import { cn } from '@shared/utils';

// Level -> the app's semantic status tokens (never raw palette colours).
const LEVEL_DOT: Record<ActivityLevel, string> = {
  green: 'bg-status-launched',
  yellow: 'bg-status-launching',
  red: 'bg-status-error',
  info: 'bg-primary',
};

const LEVEL_LABEL: Record<ActivityLevel, string> = {
  green: 'Connected — all good',
  yellow: 'Degraded',
  red: 'Failed',
  info: 'Activity',
};

// Notification bodies are markdown-ish (`**Status:** yellow`). There's no markdown
// renderer in the app, and raw `**` markers read as noise -- so honour just the one
// construct the projector emits (inline bold) and leave everything else verbatim.
function renderInlineBold(text: string): React.ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
    part.startsWith('**') && part.endsWith('**') && part.length > 4 ? (
      <strong key={i} className='font-semibold text-foreground'>
        {part.slice(2, -2)}
      </strong>
    ) : (
      part
    )
  );
}

function relativeTime(iso: string): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return '';
  const secs = Math.max(0, Math.round((Date.now() - then) / 1000));
  if (secs < 60) return 'just now';
  if (secs < 3600) return `${Math.floor(secs / 60)}m ago`;
  if (secs < 86400) return `${Math.floor(secs / 3600)}h ago`;
  return formatLocal(iso, 'short');
}

export function NotificationCenter(): JSX.Element {
  const mobile = isMobileRoute();
  const { notifications, unreadCount, loaded, error, markRead, markAllRead } = useActivity();
  const [open, setOpen] = useState(false);
  const [detail, setDetail] = useState<ActivityNotification | null>(null);
  const panelRef = useRef<HTMLDivElement | null>(null);
  const buttonRef = useRef<HTMLButtonElement | null>(null);

  // Close on Escape + outside click (a dropdown, not a modal — it shouldn't trap).
  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent): void {
      if (e.key === 'Escape') {
        if (detail) setDetail(null);
        else setOpen(false);
      }
    }
    function onClick(e: MouseEvent): void {
      const target = e.target as Node;
      if (panelRef.current?.contains(target) || buttonRef.current?.contains(target)) return;
      setOpen(false);
      setDetail(null);
    }
    document.addEventListener('keydown', onKey);
    document.addEventListener('mousedown', onClick);
    return () => {
      document.removeEventListener('keydown', onKey);
      document.removeEventListener('mousedown', onClick);
    };
  }, [open, detail]);

  function jumpTo(intent: Record<string, unknown>): void {
    // The app shell listens for this and routes via its own navigate() flow.
    window.dispatchEvent(new CustomEvent('synapse:navigate', { detail: intent }));
    setOpen(false);
    setDetail(null);
  }

  function openDetail(n: ActivityNotification): void {
    setDetail(n);
    if (!n.read_at) void markRead(n.id);
  }

  return (
    <>
      <button
        ref={buttonRef}
        type='button'
        onClick={() => {
          setOpen((v) => !v);
          setDetail(null);
        }}
        aria-label={
          unreadCount > 0 ? `AI activity — ${unreadCount} unread` : 'AI activity'
        }
        aria-expanded={open}
        title='AI activity'
        className={cn(
          'fixed right-4 z-40 flex h-12 w-12 items-center justify-center rounded-full border border-border bg-card text-foreground shadow-lg transition hover:border-primary md:right-6',
          // Sits above the Capture FAB, which owns the bottom slot.
          mobile ? 'bottom-[calc(11.5rem+env(safe-area-inset-bottom))]' : 'bottom-24'
        )}
      >
        <Bell className='h-5 w-5' aria-hidden='true' />
        {unreadCount > 0 && (
          <span
            className='absolute -right-1 -top-1 min-w-5 rounded-full bg-primary px-1 text-center text-[11px] font-semibold leading-5 text-primary-foreground'
            aria-hidden='true'
          >
            {unreadCount > 99 ? '99+' : unreadCount}
          </span>
        )}
      </button>

      {open && (
        <div
          ref={panelRef}
          role='dialog'
          aria-label='AI activity'
          className={cn(
            // One-window: a fixed-height shell; only the inner pane scrolls.
            'fixed right-4 z-50 flex max-h-[min(32rem,70vh)] w-[min(24rem,calc(100vw-2rem))] flex-col overflow-hidden rounded-xl border border-border bg-card shadow-2xl md:right-6',
            mobile ? 'bottom-[calc(17rem+env(safe-area-inset-bottom))]' : 'bottom-40'
          )}
        >
          <header className='flex shrink-0 items-center justify-between gap-2 border-b border-border px-4 py-3'>
            {detail ? (
              <button
                type='button'
                onClick={() => setDetail(null)}
                className='flex items-center gap-1 text-sm text-muted-foreground transition hover:text-foreground'
              >
                <ChevronLeft className='h-4 w-4' aria-hidden='true' /> Back
              </button>
            ) : (
              <h2 className='text-sm font-semibold'>AI activity</h2>
            )}
            <div className='flex items-center gap-2'>
              {!detail && unreadCount > 0 && (
                <button
                  type='button'
                  onClick={() => void markAllRead()}
                  className='flex items-center gap-1 text-xs text-muted-foreground transition hover:text-foreground'
                  title='Mark all read'
                >
                  <CheckCheck className='h-3.5 w-3.5' aria-hidden='true' /> Mark all read
                </button>
              )}
              <button
                type='button'
                onClick={() => {
                  setOpen(false);
                  setDetail(null);
                }}
                aria-label='Close activity panel'
                className='text-muted-foreground transition hover:text-foreground'
              >
                <X className='h-4 w-4' aria-hidden='true' />
              </button>
            </div>
          </header>

          {/* The only scrolling region — the panel itself never grows the page. */}
          <div className='scrollbar-thin min-h-0 flex-1 overflow-y-auto'>
            {detail ? (
              <DetailView notification={detail} onJump={jumpTo} />
            ) : (
              <ListView
                notifications={notifications}
                loaded={loaded}
                error={error}
                onOpen={openDetail}
                onDismiss={(id) => void markRead(id)}
              />
            )}
          </div>
        </div>
      )}
    </>
  );
}

function ListView({
  notifications,
  loaded,
  error,
  onOpen,
  onDismiss,
}: {
  notifications: ActivityNotification[];
  loaded: boolean;
  error: string | null;
  onOpen: (n: ActivityNotification) => void;
  onDismiss: (id: string) => void;
}): JSX.Element {
  if (!loaded) {
    return <p className='px-4 py-6 text-center text-sm text-muted-foreground'>Loading activity…</p>;
  }
  if (error && notifications.length === 0) {
    return (
      <p role='alert' className='px-4 py-6 text-center text-sm text-destructive'>
        {error}
      </p>
    );
  }
  if (notifications.length === 0) {
    return (
      <div className='px-4 py-8 text-center'>
        <p className='text-sm font-medium'>Nothing yet</p>
        <p className='mt-1 text-xs text-muted-foreground'>
          When an AI connects to Synapse or does something notable, it shows up here.
        </p>
      </div>
    );
  }
  return (
    <ul className='divide-y divide-border'>
      {notifications.map((n) => (
        <li key={n.id} className={cn('group flex items-start gap-2 px-3 py-2.5', !n.read_at && 'bg-accent/30')}>
          <span
            className={cn('mt-1.5 h-2 w-2 shrink-0 rounded-full', LEVEL_DOT[n.level] ?? LEVEL_DOT.info)}
            title={LEVEL_LABEL[n.level] ?? LEVEL_LABEL.info}
            aria-hidden='true'
          />
          <button
            type='button'
            onClick={() => onOpen(n)}
            className='min-w-0 flex-1 text-left'
            title='See details'
          >
            <p className={cn('truncate text-sm', !n.read_at && 'font-medium')}>{n.title}</p>
            <p className='mt-0.5 text-[11px] text-muted-foreground'>{relativeTime(n.created_at)}</p>
          </button>
          <button
            type='button'
            onClick={() => onDismiss(n.id)}
            aria-label={`Dismiss: ${n.title}`}
            title='Dismiss'
            className='shrink-0 rounded p-1 text-muted-foreground opacity-0 transition hover:bg-accent hover:text-foreground focus:opacity-100 group-hover:opacity-100'
          >
            <X className='h-3.5 w-3.5' aria-hidden='true' />
          </button>
        </li>
      ))}
    </ul>
  );
}

function DetailView({
  notification,
  onJump,
}: {
  notification: ActivityNotification;
  onJump: (intent: Record<string, unknown>) => void;
}): JSX.Element {
  const tokens = notification.token_usage as
    | { total_tokens?: number; input_tokens?: number; output_tokens?: number; by_role?: Record<string, number> }
    | null;
  return (
    <div className='flex flex-col gap-3 px-4 py-3'>
      <div>
        <div className='flex items-center gap-2'>
          <span
            className={cn('h-2 w-2 shrink-0 rounded-full', LEVEL_DOT[notification.level] ?? LEVEL_DOT.info)}
            aria-hidden='true'
          />
          <span className='text-[11px] uppercase tracking-wide text-muted-foreground'>
            {LEVEL_LABEL[notification.level] ?? LEVEL_LABEL.info}
          </span>
        </div>
        <h3 className='mt-1 text-sm font-semibold'>{notification.title}</h3>
        <p className='mt-0.5 text-[11px] text-muted-foreground'>
          {formatLocal(notification.created_at, 'long')}
          {notification.seq !== null && ` · session #${String(notification.seq).padStart(3, '0')}`}
        </p>
      </div>

      {notification.body_md && (
        <p className='whitespace-pre-wrap text-sm text-muted-foreground'>
          {renderInlineBold(notification.body_md)}
        </p>
      )}

      {tokens && typeof tokens.total_tokens === 'number' && (
        <div className='rounded-lg border border-border bg-secondary/30 p-3'>
          <p className='text-[11px] font-semibold uppercase tracking-wide text-muted-foreground'>
            Token usage
          </p>
          <dl className='mt-2 grid grid-cols-3 gap-2 text-center'>
            <div>
              <dt className='text-[10px] text-muted-foreground'>In</dt>
              <dd className='font-mono text-xs'>{(tokens.input_tokens ?? 0).toLocaleString()}</dd>
            </div>
            <div>
              <dt className='text-[10px] text-muted-foreground'>Out</dt>
              <dd className='font-mono text-xs'>{(tokens.output_tokens ?? 0).toLocaleString()}</dd>
            </div>
            <div>
              <dt className='text-[10px] text-muted-foreground'>Total</dt>
              <dd className='font-mono text-xs font-semibold'>{tokens.total_tokens.toLocaleString()}</dd>
            </div>
          </dl>
          {tokens.by_role && Object.keys(tokens.by_role).length > 0 && (
            <ul className='mt-2 space-y-1 border-t border-border pt-2'>
              {Object.entries(tokens.by_role).map(([role, count]) => (
                <li key={role} className='flex items-center justify-between text-[11px]'>
                  <span className='truncate text-muted-foreground'>{role}</span>
                  <span className='font-mono'>{count.toLocaleString()}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {notification.links.length > 0 && (
        <div className='flex flex-wrap gap-2'>
          {notification.links.map((link) => (
            <button
              key={link.label}
              type='button'
              onClick={() => onJump(link.intent)}
              className='inline-flex items-center gap-1.5 rounded-md border border-border px-2.5 py-1.5 text-xs transition hover:border-primary hover:text-foreground'
            >
              <ExternalLink className='h-3.5 w-3.5' aria-hidden='true' />
              {link.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
