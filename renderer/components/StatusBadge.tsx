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
