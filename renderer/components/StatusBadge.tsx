// Live status pill -- Contract #2. One badge handles every entity's status;
// colour comes from the Tailwind `status-*` palette (theme-tokens / styles.css).

import { cn } from '@shared/utils';
import type { EntityStatus } from '@shared/generated-types';

const LABEL: Record<EntityStatus, string> = {
  idle: 'idle',
  launching: 'launching',
  launched: 'running',
  stopping: 'stopping',
  stopped: 'stopped',
  error: 'error',
};

/**
 * One-line explanation of each status, shown as the badge's native
 * tooltip so the user can hover any project tile to learn what the
 * pill actually means. Same source of truth as the StatusLegend
 * popover.
 */
export const STATUS_MEANING: Record<EntityStatus, string> = {
  idle: 'Never started this session -- nothing has been attempted yet.',
  launching: 'Spawn in flight -- waiting for the process to come up.',
  launched: 'Running -- heartbeat OK and ports answering.',
  stopping: 'Stop signal sent -- waiting for the process to exit.',
  stopped: 'Was running; has now exited (clean shutdown or via Stop).',
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
