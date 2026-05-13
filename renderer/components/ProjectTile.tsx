// One project tile (Milestone D).
//
// Shows name + path + live status badge + a Launch/Stop button + an Edit
// affordance. Status comes from props so the parent page can update it
// instantly from WS events without the tile fetching.

import { useState } from 'react';

import { launchProject, stopProject } from '../lib/projects-client';
import type { Project } from '../lib/generated-types';
import { formatLocal, formatUptime } from '../lib/format-time';
import { StatusBadge } from './StatusBadge';

export interface ProjectTileProps {
  project: Project;
  onEdit: (project: Project) => void;
  onDelete: (project: Project) => void;
  onActionError?: (project: Project, error: Error) => void;
}

export function ProjectTile({ project, onEdit, onDelete, onActionError }: ProjectTileProps): JSX.Element {
  const [busy, setBusy] = useState(false);

  const isRunning = project.status === 'launched' || project.status === 'stopping';
  const isTransitioning = project.status === 'launching' || project.status === 'stopping';

  async function handleLaunch(): Promise<void> {
    setBusy(true);
    try {
      await launchProject(project.id, 'desktop');
    } catch (err) {
      onActionError?.(project, err as Error);
    } finally {
      setBusy(false);
    }
  }

  async function handleStop(): Promise<void> {
    setBusy(true);
    try {
      await stopProject(project.id, 'desktop');
    } catch (err) {
      onActionError?.(project, err as Error);
    } finally {
      setBusy(false);
    }
  }

  return (
    <article
      style={{
        backgroundColor: 'var(--synapse-bg-surface)',
        border: '1px solid var(--synapse-border-subtle)',
        borderRadius: 'var(--synapse-radius-lg)',
        padding: 'var(--synapse-space-6)',
        display: 'flex',
        flexDirection: 'column',
        gap: 'var(--synapse-space-4)',
        minHeight: '180px',
      }}
    >
      <header style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 'var(--synapse-space-3)' }}>
        <div>
          <h3 style={{ margin: 0, fontSize: 'var(--synapse-text-lg)', letterSpacing: '-0.01em' }}>
            {project.name}
          </h3>
          <p
            style={{
              margin: 'var(--synapse-space-1) 0 0',
              color: 'var(--synapse-text-secondary)',
              fontSize: 'var(--synapse-text-xs)',
              fontFamily: 'var(--synapse-font-mono)',
              wordBreak: 'break-all',
            }}
          >
            {project.path}
          </p>
        </div>
        <StatusBadge status={project.status} />
      </header>

      {project.description && (
        <p style={{ margin: 0, color: 'var(--synapse-text-secondary)', fontSize: 'var(--synapse-text-sm)' }}>
          {project.description}
        </p>
      )}

      <dl
        style={{
          display: 'grid',
          gridTemplateColumns: 'auto 1fr',
          gap: 'var(--synapse-space-1) var(--synapse-space-3)',
          margin: 0,
          fontSize: 'var(--synapse-text-xs)',
        }}
      >
        <dt style={dtStyle}>cmd</dt>
        <dd style={ddStyle}>{project.launch_cmd}</dd>
        {project.expected_port !== null && (
          <>
            <dt style={dtStyle}>port</dt>
            <dd style={ddStyle}>{project.expected_port}</dd>
          </>
        )}
        <dt style={dtStyle}>updated</dt>
        <dd style={ddStyle}>
          {project.status === 'launched'
            ? `running ${formatUptime(project.last_transition_at)}`
            : formatLocal(project.last_transition_at, 'short')}
        </dd>
      </dl>

      {project.last_error && (
        <p
          role='alert'
          style={{
            margin: 0,
            padding: 'var(--synapse-space-2) var(--synapse-space-3)',
            borderRadius: 'var(--synapse-radius-sm)',
            backgroundColor: 'rgba(248, 113, 113, 0.08)',
            border: '1px solid var(--synapse-status-error)',
            color: 'var(--synapse-status-error)',
            fontSize: 'var(--synapse-text-xs)',
            fontFamily: 'var(--synapse-font-mono)',
          }}
        >
          [{project.last_error.code}] {project.last_error.message}
        </p>
      )}

      <footer style={{ display: 'flex', gap: 'var(--synapse-space-2)', marginTop: 'auto', flexWrap: 'wrap' }}>
        {isRunning ? (
          <button
            type='button'
            disabled={busy || isTransitioning}
            onClick={handleStop}
            style={buttonStyle('danger')}
          >
            {project.status === 'stopping' ? 'stopping…' : 'Stop'}
          </button>
        ) : (
          <button
            type='button'
            disabled={busy || isTransitioning}
            onClick={handleLaunch}
            style={buttonStyle('primary')}
          >
            {project.status === 'launching' ? 'launching…' : 'Launch'}
          </button>
        )}
        <button type='button' onClick={() => onEdit(project)} style={buttonStyle('ghost')}>
          Edit
        </button>
        <button
          type='button'
          onClick={() => onDelete(project)}
          disabled={isRunning || isTransitioning}
          style={buttonStyle('ghost')}
          title={isRunning ? 'Stop the project before deleting.' : 'Delete'}
        >
          Delete
        </button>
      </footer>
    </article>
  );
}

const dtStyle: React.CSSProperties = {
  color: 'var(--synapse-text-muted)',
  fontFamily: 'var(--synapse-font-mono)',
};
const ddStyle: React.CSSProperties = {
  margin: 0,
  color: 'var(--synapse-text-secondary)',
  fontFamily: 'var(--synapse-font-mono)',
  wordBreak: 'break-all',
};

type ButtonVariant = 'primary' | 'danger' | 'ghost';

function buttonStyle(variant: ButtonVariant): React.CSSProperties {
  const base: React.CSSProperties = {
    minHeight: '36px',
    padding: '0 var(--synapse-space-4)',
    borderRadius: 'var(--synapse-radius-md)',
    fontSize: 'var(--synapse-text-sm)',
    fontFamily: 'var(--synapse-font-sans)',
    cursor: 'pointer',
    border: '1px solid transparent',
    transition: 'background-color var(--synapse-duration-fast) var(--synapse-ease-smooth)',
  };
  if (variant === 'primary') {
    return {
      ...base,
      backgroundColor: 'var(--synapse-accent)',
      color: 'var(--synapse-text-primary)',
    };
  }
  if (variant === 'danger') {
    return {
      ...base,
      backgroundColor: 'transparent',
      borderColor: 'var(--synapse-status-error)',
      color: 'var(--synapse-status-error)',
    };
  }
  return {
    ...base,
    backgroundColor: 'transparent',
    borderColor: 'var(--synapse-border-strong)',
    color: 'var(--synapse-text-primary)',
  };
}
