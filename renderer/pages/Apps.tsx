// Apps page (Milestone D) — lists managed projects as tiles.
//
// Subscribes to v1.project.* WS events so tile state stays current without
// polling. Empty state (Contract #13) renders a friendly CTA if no projects
// have been registered yet. Delete is a confirm-before-destructive
// interaction (Contract #12).

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { deleteProject, listProjects } from '../lib/projects-client';
import type { Project } from '../lib/generated-types';
import { SynapseWsClient } from '../lib/ws-client';
import { ProjectEditDialog } from '../components/ProjectEditDialog';
import { ProjectTile } from '../components/ProjectTile';

export function AppsPage(): JSX.Element {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<Project | null>(null);
  const [deleting, setDeleting] = useState<Project | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const wsRef = useRef<SynapseWsClient | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const next = await listProjects();
      setProjects(next);
      setLoadError(null);
    } catch (err) {
      setLoadError((err as Error).message || 'Failed to fetch projects');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();

    const ws = new SynapseWsClient();
    wsRef.current = ws;
    const unsub = ws.onEvent((event) => {
      if (!event.name.startsWith('v1.project.')) return;
      // Optimistic update for the affected project. Fall back to a refresh
      // for safety — the daemon's state is authoritative.
      const id = (event.payload as { id?: string }).id;
      if (!id) return;
      void refresh();
    });
    ws.start();

    return () => {
      unsub();
      ws.stop();
    };
  }, [refresh]);

  const sorted = useMemo(() => {
    return [...projects].sort((a, b) => a.name.localeCompare(b.name));
  }, [projects]);

  async function handleConfirmDelete(target: Project): Promise<void> {
    try {
      await deleteProject(target.id);
      setDeleting(null);
      setDeleteError(null);
      await refresh();
    } catch (err) {
      setDeleteError((err as Error).message || 'Delete failed');
    }
  }

  return (
    <section style={{ display: 'flex', flexDirection: 'column', gap: 'var(--synapse-space-6)' }}>
      <header style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between' }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 'var(--synapse-text-xl)', letterSpacing: '-0.01em' }}>
            Apps
          </h2>
          <p style={{ margin: 'var(--synapse-space-1) 0 0', color: 'var(--synapse-text-secondary)', fontSize: 'var(--synapse-text-sm)' }}>
            Launchable projects under Synapse's management. Click a tile to start it.
          </p>
        </div>
      </header>

      {loadError && (
        <p role='alert' style={{ color: 'var(--synapse-status-error)' }}>
          Could not load projects: {loadError}
        </p>
      )}

      {loading && projects.length === 0 ? (
        <p style={{ color: 'var(--synapse-text-secondary)' }}>Loading projects…</p>
      ) : projects.length === 0 ? (
        <EmptyState onRetry={() => void refresh()} />
      ) : (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))',
            gap: 'var(--synapse-space-6)',
          }}
        >
          {sorted.map((p) => (
            <ProjectTile
              key={p.id}
              project={p}
              onEdit={(project) => setEditing(project)}
              onDelete={(project) => {
                setDeleteError(null);
                setDeleting(project);
              }}
              onActionError={(_proj, err) => setLoadError(err.message)}
            />
          ))}
        </div>
      )}

      {editing && (
        <ProjectEditDialog
          project={editing}
          onSaved={(updated) => {
            setProjects((prev) => prev.map((p) => (p.id === updated.id ? updated : p)));
            setEditing(null);
          }}
          onClose={() => setEditing(null)}
        />
      )}

      {deleting && (
        <ConfirmDialog
          title={`Delete "${deleting.name}"?`}
          body={
            <>
              <p>
                Synapse will soft-delete this project's registry row. The on-disk app at{' '}
                <code>{deleting.path}</code> stays untouched.
              </p>
              <p style={{ color: 'var(--synapse-text-muted)', fontSize: 'var(--synapse-text-xs)' }}>
                You can recreate the entry later via "+ Add" (coming in Milestone F).
              </p>
            </>
          }
          confirmLabel='Delete project'
          danger
          error={deleteError}
          onConfirm={() => handleConfirmDelete(deleting)}
          onCancel={() => {
            setDeleting(null);
            setDeleteError(null);
          }}
        />
      )}
    </section>
  );
}

function EmptyState({ onRetry }: { onRetry: () => void }): JSX.Element {
  // Contract #13 — no blank pages.
  return (
    <div
      style={{
        backgroundColor: 'var(--synapse-bg-surface)',
        border: '1px dashed var(--synapse-border-strong)',
        borderRadius: 'var(--synapse-radius-lg)',
        padding: 'var(--synapse-space-12)',
        textAlign: 'center',
      }}
    >
      <h3 style={{ margin: 0, fontSize: 'var(--synapse-text-lg)' }}>No projects yet</h3>
      <p style={{ margin: 'var(--synapse-space-2) 0 var(--synapse-space-4)', color: 'var(--synapse-text-secondary)' }}>
        Synapse seeds <code>wbscrper</code> on first run. If you don't see it, the daemon may not have started
        yet — try the daemon health link in the tray menu.
      </p>
      <button
        type='button'
        onClick={onRetry}
        style={{
          minHeight: '36px',
          padding: '0 var(--synapse-space-4)',
          borderRadius: 'var(--synapse-radius-md)',
          fontSize: 'var(--synapse-text-sm)',
          backgroundColor: 'transparent',
          border: '1px solid var(--synapse-border-strong)',
          color: 'var(--synapse-text-primary)',
          cursor: 'pointer',
        }}
      >
        Refresh
      </button>
    </div>
  );
}

interface ConfirmDialogProps {
  title: string;
  body: React.ReactNode;
  confirmLabel: string;
  danger?: boolean;
  error?: string | null;
  onConfirm: () => void;
  onCancel: () => void;
}

function ConfirmDialog({ title, body, confirmLabel, danger, error, onConfirm, onCancel }: ConfirmDialogProps): JSX.Element {
  // Contract #12 — confirm before destructive (with structured detail of
  // what will happen, not a generic "are you sure?").
  return (
    <div
      role='dialog'
      aria-modal='true'
      aria-labelledby='confirm-title'
      style={{
        position: 'fixed',
        inset: 0,
        backgroundColor: 'var(--synapse-bg-overlay)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 'var(--synapse-space-6)',
        zIndex: 100,
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onCancel();
      }}
    >
      <div
        style={{
          width: 'min(480px, 100%)',
          backgroundColor: 'var(--synapse-bg-surface)',
          border: '1px solid var(--synapse-border-subtle)',
          borderRadius: 'var(--synapse-radius-lg)',
          padding: 'var(--synapse-space-8)',
          display: 'flex',
          flexDirection: 'column',
          gap: 'var(--synapse-space-4)',
        }}
      >
        <h2 id='confirm-title' style={{ margin: 0, fontSize: 'var(--synapse-text-lg)' }}>
          {title}
        </h2>
        <div style={{ color: 'var(--synapse-text-secondary)', fontSize: 'var(--synapse-text-sm)' }}>{body}</div>
        {error && (
          <p role='alert' style={{ margin: 0, color: 'var(--synapse-status-error)', fontSize: 'var(--synapse-text-sm)' }}>
            {error}
          </p>
        )}
        <footer style={{ display: 'flex', gap: 'var(--synapse-space-2)', justifyContent: 'flex-end' }}>
          <button
            type='button'
            onClick={onCancel}
            style={{
              minHeight: '36px',
              padding: '0 var(--synapse-space-4)',
              borderRadius: 'var(--synapse-radius-md)',
              backgroundColor: 'transparent',
              border: '1px solid var(--synapse-border-strong)',
              color: 'var(--synapse-text-primary)',
              fontSize: 'var(--synapse-text-sm)',
              cursor: 'pointer',
            }}
          >
            Cancel
          </button>
          <button
            type='button'
            onClick={onConfirm}
            style={{
              minHeight: '36px',
              padding: '0 var(--synapse-space-4)',
              borderRadius: 'var(--synapse-radius-md)',
              backgroundColor: danger ? 'var(--synapse-status-error)' : 'var(--synapse-accent)',
              color: 'var(--synapse-text-primary)',
              border: '1px solid transparent',
              fontSize: 'var(--synapse-text-sm)',
              cursor: 'pointer',
            }}
          >
            {confirmLabel}
          </button>
        </footer>
      </div>
    </div>
  );
}
