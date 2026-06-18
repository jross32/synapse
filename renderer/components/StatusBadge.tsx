// Live status pill -- Contract #2. One badge handles every entity's status;
// colour comes from the Tailwind `status-*` palette (theme-tokens / styles.css).

import { cn } from '@shared/utils';
import type { EntityStatus } from '@shared/generated-types';

// v0.1.36 A3: idle + stopped collapse into one user-facing label.
// Contract #2's six-status enum is preserved on the daemon side; the
// audit log + last_transition_at still distinguish them. The user
// just sees "not running" for both because the distinction wasn't
// load-bearing in the UI.
const LABEL: Record<EntityStatus, string> = {
  idle: 'not running',
  launching: 'launching',
  launched: 'running',
  stopping: 'stopping',
  stopped: 'not running',
  error: 'error',
};

/**
 * One-line explanation of each status, shown as the badge's native
 * tooltip so the user can hover any project tile to learn what the
 * pill actually means. Same source of truth as the StatusLegend
 * popover.
 */
export const STATUS_MEANING: Record<EntityStatus, string> = {
  idle: 'Not running. Synapse has never started this project this install.',
  launching: 'Spawn in flight -- waiting for the process to come up.',
  launched: 'Running -- heartbeat OK and ports answering.',
  stopping: 'Stop signal sent -- waiting for the process to exit.',
  stopped: 'Not running. Was running earlier; exited cleanly or via Stop.',
  error: 'Crashed, restart policy gave up, or launch failed. See last_error.',
};

const DOT: Record<EntityStatus, string> = {
  idle: 'bg-status-idle',
  launching: 'bg-status-launching',
  launched: 'bg-status-launched',
  stopping: 'bg-status-stopping',
  stopped: 'bg-status-stopped',
  error: 'bg-status-error',
};

const TRANSITIONING: Record<EntityStatus, boolean> = {
  idle: false,
  launching: true,
  launched: false,
  stopping: true,
  stopped: false,
  error: false,
};

export interface StatusBadgeProps {
  status: EntityStatus;
  label?: string;
  className?: string;
}

export function StatusBadge({ status, label, className }: StatusBadgeProps): JSX.Element {
  return (
    <span
      aria-live='polite'
      aria-label={`Status: ${LABEL[status]}`}
      title={`${LABEL[status]} — ${STATUS_MEANING[status]}`}
      className={cn(
        'inline-flex items-center gap-2 rounded-full border border-border bg-secondary px-2.5 py-0.5',
        'font-mono text-xs text-foreground',
        className
      )}
    >
      <span
        className={cn(
          'h-2 w-2 rounded-full',
          DOT[status],
          TRANSITIONING[status] && 'animate-synapse-pulse'
        )}
      />
      {label ?? LABEL[status]}
    </span>
  );
}
