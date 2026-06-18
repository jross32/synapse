// Status legend popover (v0.1.35) -- spells out what each EntityStatus
// actually means. Contract #2 defines six values but the difference
// between idle and stopped (especially) isn't obvious from the label.
//
// Source of truth for the per-status meaning is STATUS_MEANING in
// StatusBadge.tsx so the badge tooltip and this popover never drift.

import { useEffect, useRef, useState } from 'react';
import { HelpCircle } from 'lucide-react';

import type { EntityStatus } from '@shared/generated-types';
import { cn } from '@shared/utils';

// v0.1.36 A3: idle + stopped are presented to the user as a single
// "not running" row. The daemon still emits both internally; only the
// legend collapses them.
type LegendRow = {
  key: string;
  dot: string;
  label: string;
  meaning: string;
};

const ROWS: LegendRow[] = [
  {
    key: 'not-running',
    dot: 'bg-status-stopped',
    label: 'not running',
    meaning:
      "Synapse isn't managing this project right now. Either it's never started this install, or it was running and has since exited.",
  },
  {
    key: 'launching',
    dot: 'bg-status-launching',
    label: 'launching',
    meaning: 'Spawn in flight -- waiting for the process to come up.',
  },
  {
    key: 'launched',
    dot: 'bg-status-launched',
    label: 'running',
    meaning: 'Running -- heartbeat OK and ports answering.',
  },
  {
    key: 'stopping',
    dot: 'bg-status-stopping',
    label: 'stopping',
    meaning: 'Stop signal sent -- waiting for the process to exit.',
  },
  {
    key: 'error',
    dot: 'bg-status-error',
    label: 'error',
    meaning: 'Crashed, restart policy gave up, or launch failed. See last_error.',
  },
];

export function StatusLegend(): JSX.Element {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement | null>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const dialogRef = useRef<HTMLDivElement | null>(null);

  // Close on click-outside and on Escape so it behaves like a real popover.
  // Also restore focus to the trigger when the popover dismisses, so a
  // keyboard user lands back where they started.
  useEffect(() => {
    if (!open) return;
    function onDown(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') setOpen(false);
    }
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    // Focus the dialog body on open so screen readers + keyboard land
    // inside the popover rather than staying on the toggle.
    const focusTimer = window.setTimeout(() => dialogRef.current?.focus(), 0);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
      window.clearTimeout(focusTimer);
      // Return focus to the trigger so Tab continues from the right
      // place. Only when focus is still inside the popover -- otherwise
      // the user has clicked away and we should respect that.
      if (
        document.activeElement &&
        ref.current?.contains(document.activeElement) &&
        triggerRef.current
      ) {
        triggerRef.current.focus();
      }
    };
  }, [open]);

  return (
    <div ref={ref} className='relative inline-flex'>
      <button
        ref={triggerRef}
        type='button'
        aria-expanded={open}
        aria-haspopup='dialog'
        onClick={() => setOpen((o) => !o)}
        title='What do the status labels mean?'
        className={cn(
          'inline-flex items-center gap-1 rounded-full border border-border px-2 py-1 text-xs',
          'text-muted-foreground transition-colors hover:border-primary hover:text-foreground'
        )}
      >
        <HelpCircle className='h-3.5 w-3.5' aria-hidden='true' />
        <span>What do these statuses mean?</span>
      </button>
      {open && (
        <div
          ref={dialogRef}
          role='dialog'
          aria-label='Status legend'
          tabIndex={-1}
          className={cn(
            'absolute right-0 top-full z-30 mt-2 w-80 rounded-md border border-border bg-card p-3 shadow-lg outline-none',
            'text-xs'
          )}
        >
          <p className='mb-2 font-semibold text-foreground'>What the status pills mean</p>
          <ul className='space-y-2'>
            {ROWS.map((row) => (
              <li key={row.key} className='flex items-start gap-2'>
                <span
                  className={cn(
                    'mt-1 h-2 w-2 shrink-0 rounded-full',
                    row.dot
                  )}
                  aria-hidden='true'
                />
                <div>
                  <span className='font-mono text-foreground'>{row.label}</span>
                  <p className='text-muted-foreground'>{row.meaning}</p>
                </div>
              </li>
            ))}
          </ul>
          <p className='mt-3 border-t border-border pt-2 text-muted-foreground'>
            <strong className='text-foreground'>Tip:</strong> hover any tile's
            pill for the same meaning inline.
          </p>
        </div>
      )}
    </div>
  );
}
