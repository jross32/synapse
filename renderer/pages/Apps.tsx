// Apps page (Milestones D + E) -- project tiles + live process monitor.
//
// Owns a single WS subscription for the whole page: v1.project.* events
// trigger a refresh, v1.process.heartbeat feeds the live CPU/RAM map shared
// by the tiles and the ProcessMonitor table.
//
// Empty state (#13), confirm-before-destructive delete (#12), and the
// "+ Add Project" create flow (#1 -- everything editable from the UI) all
// live here.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { deleteProject, listProjects } from '../lib/projects-client';
import type { Project, ResourceSnapshot } from '../lib/generated-types';
import { SynapseWsClient } from '../lib/ws-client';
import { ProcessMonitor } from '../components/ProcessMonitor';
import { ProjectFormDialog, type ProjectFormMode } from '../components/ProjectFormDialog';
import { ProjectTile } from '../components/ProjectTile';

interface FormState {
  mode: ProjectFormMode;
  project?: Project;
}

export function AppsPage(): JSX.Element {
  const [projects, setProjects] = useState<Project[]>([]);
  const [resourcesById, setResourcesById] = useState<Record<string, ResourceSnapshot>>({});
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState<FormState | null>(null);
  const [deleting, setDeleting] = useState<Project | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const wsRef = useRef<SynapseWsClient | null>(null);

  const refresh = useCallback(async () => {
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
      if (event.name === 'v1.process.heartbeat') {
        // Heartbeat payload carries a snapshot per running process.
        const procs = (event.payload as { processes?: ResourceSnapshot[] }).processes ?? [];
        setResourcesById((prev) => {
          const next = { ...prev };
          for (const snap of procs) next[snap.entity_id] = snap;
          return next;
        });
        return;
      }
      if (event.name.startsWith('v1.project.')) {
        // Daemon state is authoritative -- refetch on any project event.
        void refresh();
      }
    });
    ws.start();

    return () => {
      unsub();
      ws.stop();
    };
  }, [refresh]);

  const sorted = useMemo(
    () => [...projects].sort((a, b) => a.name.localeCompare(b.name)),
    [projects]
  );

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
    <section style={{ display: 'flex', flexDirection: 'column', gap: 'var(--synapse-space-8)' }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--synapse-space-6)' }}>
        <header style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 'var(--synapse-space-4)' }}>
          <div>
            <h2 style={{ margin: 0, fontSize: 'var(--synapse-text-xl)', letterSpacing: '-0.01em' }}>
              Apps
            </h2>
            <p style={{ margin: 'var(--synapse-space-1) 0 0', color: 'var(--synapse-text-secondary)', fontSize: 'var(--synapse-text-sm)' }}>
              Launchable projects under Synapse's management. Click a tile to start it.
            </p>
          </div>
          <button
            type='button'
            onClick={() => setForm({ mode: 'create' })}
            style={{
              minHeight: '40px',
              padding: '0 var(--synapse-space-5)',
              borderRadius: 'var(--synapse-radius-md)',
              backgroundColor: 'var(--synapse-accent)',
              color: 'var(--synapse-text-primary)',
              borderWidth: '1px',
              borderStyle: 'solid',
              borderColor: 'transparent',
              fontSize: 'var(--synapse-text-sm)',
              fontWeight: 600,
              cursor: 'pointer',
              whiteSpace: 'nowrap',
            }}
          >
            + Add Project
          </button>
        </header>

        {loadError && (
          <p role='alert' style={{ color: 'var(--synapse-status-error)' }}>
            Could not load projects: {loadError}
          </p>
        )}

        {loading && projects.length === 0 ? (
          <p style={{ color: 'var(--synapse-text-secondary)' }}>Loading projects…</p>
        ) : projects.length === 0 ? (
          <EmptyState onAdd={() => setForm({ mode: 'create' })} />
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
                resources={resourcesById[p.id]}
                onEdit={(project) => setForm({ mode: 'edit', project })}
                onDelete={(project) => {
                  setDeleteError(null);
                  setDeleting(project);
                }}
                onActionError={(_proj, err) => setLoadError(err.message)}
              />
            ))}
          </div>
        )}
      </div>

      <ProcessMonitor
        projects={projects}
        resourcesById={resourcesById}
        onActionError={(_p, err) => setLoadError(err.message)}
      />

      {form && (
        <ProjectFormDialog
          mode={form.mode}
          project={form.project}
          onSaved={(saved) => {
            setProjects((prev) => {
              const exists = prev.some((p) => p.id === saved.id);
              return exists ? prev.map((p) => (p.id === saved.id ? saved : p)) : [...prev, saved];
            });
            setForm(null);
          }}
          onClose={() => setForm(null)}
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
                You can re-add it any time with "+ Add Project".
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

function EmptyState({ onAdd }: { onAdd: () => void }): JSX.Element {
  // Contract #13 -- no blank pages.
  return (
    <div
      style={{
        backgroundColor: 'var(--synapse-bg-surface)',
        borderWidth: '1px',
        borderStyle: 'dashed',
        borderColor: 'var(--synapse-border-strong)',
        borderRadius: 'var(--synapse-radius-lg)',
        padding: 'var(--synapse-space-12)',
        textAlign: 'center',
      }}
    >
      <h3 style={{ margin: 0, fontSize: 'var(--synapse-text-lg)' }}>No projects yet</h3>
      <p style={{ margin: 'var(--synapse-space-2) 0 var(--synapse-space-4)', color: 'var(--synapse-text-secondary)' }}>
        Add any app on your machine — Synapse will launch it, monitor it, and keep its logs.
      </p>
      <button
        type='button'
        onClick={onAdd}
        style={{
          minHeight: '40px',
          padding: '0 var(--synapse-space-5)',
          borderRadius: 'var(--synapse-radius-md)',
          backgroundColor: 'var(--synapse-accent)',
          color: 'var(--synapse-text-primary)',
          borderWidth: '1px',
          borderStyle: 'solid',
          borderColor: 'transparent',
          fontSize: 'var(--synapse-text-sm)',
          fontWeight: 600,
          cursor: 'pointer',
        }}
      >
        + Add your first project
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
  // Contract #12 -- confirm before destructive, with structured detail.
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
          borderWidth: '1px',
          borderStyle: 'solid',
          borderColor: 'var(--synapse-border-subtle)',
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
              borderWidth: '1px',
              borderStyle: 'solid',
              borderColor: 'var(--synapse-border-strong)',
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
              borderWidth: '1px',
              borderStyle: 'solid',
              borderColor: 'transparent',
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
