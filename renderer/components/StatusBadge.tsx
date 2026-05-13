// Live status pill — Contract #2.
//
// One badge component handles every entity's status. Colour comes from the
// theme tokens defined in theme-tokens.css; subcomponents elsewhere import
// this rather than rolling their own.

import type { CSSProperties } from 'react';

import type { EntityStatus } from '../lib/generated-types';

const LABEL: Record<EntityStatus, string> = {
  idle: 'idle',
  launching: 'launching…',
  launched: 'running',
  stopping: 'stopping…',
  stopped: 'stopped',
  error: 'error',
};

const COLOR: Record<EntityStatus, string> = {
  idle: 'var(--synapse-status-idle)',
  launching: 'var(--synapse-status-launching)',
  launched: 'var(--synapse-status-launched)',
  stopping: 'var(--synapse-status-stopping)',
  stopped: 'var(--synapse-status-stopped)',
  error: 'var(--synapse-status-error)',
};

const SPINNING: Record<EntityStatus, boolean> = {
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
  style?: CSSProperties;
}

export function StatusBadge({ status, label, style }: StatusBadgeProps): JSX.Element {
  const color = COLOR[status];
  return (
    <span
      aria-live='polite'
      aria-label={label ?? `Status: ${LABEL[status]}`}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 'var(--synapse-space-2)',
        padding: 'var(--synapse-space-1) var(--synapse-space-3)',
        borderRadius: 'var(--synapse-radius-pill)',
        backgroundColor: 'var(--synapse-bg-elevated)',
        border: '1px solid var(--synapse-border-subtle)',
        fontSize: 'var(--synapse-text-xs)',
        fontFamily: 'var(--synapse-font-mono)',
        color: 'var(--synapse-text-primary)',
        ...style,
      }}
    >
      <span
        style={{
          width: '8px',
          height: '8px',
          borderRadius: 'var(--synapse-radius-pill)',
          backgroundColor: color,
          boxShadow: SPINNING[status] ? `0 0 6px ${color}` : undefined,
          animation: SPINNING[status]
            ? 'synapse-pulse 1.2s ease-in-out infinite'
            : undefined,
        }}
      />
      {label ?? LABEL[status]}
    </span>
  );
}
