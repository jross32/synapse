// Live process monitor (Contract #19) -- a compact table of everything
// Synapse currently has running, with CPU% + RAM updating from the daemon's
// v1.process.heartbeat broadcast (~2s cadence).
//
// Data comes in as props from the page that owns the WS subscription, so
// this component stays a pure render of {projects} x {resource snapshots}.

import { stopProject } from '../lib/projects-client';
import type { Project, ResourceSnapshot } from '../lib/generated-types';
import { formatUptime } from '../lib/format-time';
import { StatusBadge } from './StatusBadge';

export interface ProcessMonitorProps {
  projects: Project[];
  resourcesById: Record<string, ResourceSnapshot>;
  onActionError?: (project: Project, error: Error) => void;
}

const RUNNING_STATES = new Set(['launching', 'launched', 'stopping']);

export function ProcessMonitor({ projects, resourcesById, onActionError }: ProcessMonitorProps): JSX.Element {
  const running = projects.filter((p) => RUNNING_STATES.has(p.status));

  return (
    <section style={{ display: 'flex', flexDirection: 'column', gap: 'var(--synapse-space-4)' }}>
      <div>
        <h2 style={{ margin: 0, fontSize: 'var(--synapse-text-xl)', letterSpacing: '-0.01em' }}>
          Live Processes
        </h2>
        <p style={{ margin: 'var(--synapse-space-1) 0 0', color: 'var(--synapse-text-secondary)', fontSize: 'var(--synapse-text-sm)' }}>
          Everything Synapse is running right now. CPU + memory update live (~2s).
        </p>
      </div>

      {running.length === 0 ? (
        <div
          style={{
            backgroundColor: 'var(--synapse-bg-surface)',
            borderWidth: '1px',
            borderStyle: 'dashed',
            borderColor: 'var(--synapse-border-strong)',
            borderRadius: 'var(--synapse-radius-lg)',
            padding: 'var(--synapse-space-8)',
            textAlign: 'center',
            color: 'var(--synapse-text-secondary)',
            fontSize: 'var(--synapse-text-sm)',
          }}
        >
          Nothing running. Launch a project from the Apps section above and it
          will appear here with live CPU + memory.
        </div>
      ) : (
        <div
          style={{
            backgroundColor: 'var(--synapse-bg-surface)',
            borderWidth: '1px',
            borderStyle: 'solid',
            borderColor: 'var(--synapse-border-subtle)',
            borderRadius: 'var(--synapse-radius-lg)',
            overflow: 'hidden',
          }}
        >
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 'var(--synapse-text-sm)' }}>
            <thead>
              <tr>
                {['Project', 'Status', 'PID', 'Uptime', 'CPU', 'Memory', ''].map((h) => (
                  <th key={h} style={thStyle}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {running.map((p) => {
                const res = resourcesById[p.id];
                return (
                  <tr key={p.id} style={{ borderTop: '1px solid var(--synapse-border-subtle)' }}>
                    <td style={tdStyle}>
                      <span style={{ fontWeight: 600 }}>{p.name}</span>
                    </td>
                    <td style={tdStyle}>
                      <StatusBadge status={p.status} />
                    </td>
                    <td style={{ ...tdStyle, fontFamily: 'var(--synapse-font-mono)' }}>
                      {res ? res.pid : '—'}
                    </td>
                    <td style={{ ...tdStyle, fontFamily: 'var(--synapse-font-mono)' }}>
                      {p.status === 'launched' ? formatUptime(p.last_transition_at) : '—'}
                    </td>
                    <td style={tdStyle}>
                      <Gauge value={res?.cpu_percent ?? 0} max={100} suffix='%' />
                    </td>
                    <td style={tdStyle}>
                      <span style={{ fontFamily: 'var(--synapse-font-mono)' }}>
                        {res ? `${res.rss_mb.toFixed(0)} MB` : '—'}
                      </span>
                    </td>
                    <td style={{ ...tdStyle, textAlign: 'right' }}>
                      <button
                        type='button'
                        onClick={() => {
                          stopProject(p.id, 'desktop').catch((err) =>
                            onActionError?.(p, err as Error)
                          );
                        }}
                        disabled={p.status !== 'launched'}
                        style={{
                          minHeight: '32px',
                          padding: '0 var(--synapse-space-3)',
                          borderRadius: 'var(--synapse-radius-md)',
                          backgroundColor: 'transparent',
                          borderWidth: '1px',
                          borderStyle: 'solid',
                          borderColor: 'var(--synapse-status-error)',
                          color: 'var(--synapse-status-error)',
                          fontSize: 'var(--synapse-text-xs)',
                          cursor: 'pointer',
                        }}
                      >
                        Stop
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

/** Tiny inline bar gauge for CPU%. */
function Gauge({ value, max, suffix }: { value: number; max: number; suffix: string }): JSX.Element {
  const pct = Math.min(100, (value / max) * 100);
  const color =
    pct > 85
      ? 'var(--synapse-status-error)'
      : pct > 60
      ? 'var(--synapse-status-launching)'
      : 'var(--synapse-status-launched)';
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--synapse-space-2)' }}>
      <div
        style={{
          width: '64px',
          height: '6px',
          borderRadius: 'var(--synapse-radius-pill)',
          backgroundColor: 'var(--synapse-bg-elevated)',
          overflow: 'hidden',
        }}
      >
        <div style={{ width: `${pct}%`, height: '100%', backgroundColor: color }} />
      </div>
      <span style={{ fontFamily: 'var(--synapse-font-mono)', minWidth: '44px' }}>
        {value.toFixed(1)}{suffix}
      </span>
    </div>
  );
}

const thStyle: React.CSSProperties = {
  textAlign: 'left',
  padding: 'var(--synapse-space-3) var(--synapse-space-4)',
  color: 'var(--synapse-text-muted)',
  fontSize: 'var(--synapse-text-xs)',
  fontWeight: 600,
  textTransform: 'uppercase',
  letterSpacing: '0.04em',
};

const tdStyle: React.CSSProperties = {
  padding: 'var(--synapse-space-3) var(--synapse-space-4)',
  color: 'var(--synapse-text-primary)',
};
