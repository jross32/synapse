// Modal create / edit dialog for a Project (Contract #1 -- editable from UI).
//
// One component, two modes:
//   mode="create" -- collects id + name + path + launch_cmd (+ optionals),
//                    POSTs a new project. The daemon fills every other field
//                    with its model defaults.
//   mode="edit"   -- pre-fills from an existing project, PATCHes the diff.
//                    The id is immutable, so the id field is hidden.
//
// Esc closes, click-outside dismisses (when not busy), focus traps the first
// field. Full env-var + secrets editor lands in Milestone F.

import { useEffect, useRef, useState } from 'react';

import { createProject, patchProject } from '../lib/projects-client';
import type { Project, ProjectUpdate } from '../lib/generated-types';

export type ProjectFormMode = 'create' | 'edit';

export interface ProjectFormDialogProps {
  mode: ProjectFormMode;
  /** Required for mode="edit"; ignored for mode="create". */
  project?: Project;
  onSaved: (project: Project) => void;
  onClose: () => void;
}

const ID_RE = /^[a-z][a-z0-9-]*[a-z0-9]$|^[a-z]$/;

export function ProjectFormDialog({ mode, project, onSaved, onClose }: ProjectFormDialogProps): JSX.Element {
  const isEdit = mode === 'edit';

  const [id, setId] = useState(project?.id ?? '');
  const [name, setName] = useState(project?.name ?? '');
  const [path, setPath] = useState(project?.path ?? '');
  const [launchCmd, setLaunchCmd] = useState(project?.launch_cmd ?? '');
  const [description, setDescription] = useState(project?.description ?? '');
  const [expectedPort, setExpectedPort] = useState<string>(
    project?.expected_port == null ? '' : String(project.expected_port)
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const firstFieldRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    firstFieldRef.current?.focus();
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape' && !busy) onClose();
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [busy, onClose]);

  async function handleSubmit(e: React.FormEvent): Promise<void> {
    e.preventDefault();
    setError(null);

    if (isEdit) {
      await submitEdit();
    } else {
      await submitCreate();
    }
  }

  async function submitCreate(): Promise<void> {
    if (!ID_RE.test(id)) {
      setError('ID must be kebab-case: lower-case letters, digits and single hyphens.');
      return;
    }
    if (!name.trim() || !path.trim() || !launchCmd.trim()) {
      setError('Name, working directory and launch command are all required.');
      return;
    }
    setBusy(true);
    try {
      const created = await createProject({
        id: id.trim(),
        name: name.trim(),
        path: path.trim(),
        launch_cmd: launchCmd.trim(),
        description: description.trim() || null,
        expected_port: expectedPort === '' ? null : Number(expectedPort),
      });
      onSaved(created);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function submitEdit(): Promise<void> {
    if (!project) return;
    const patch: ProjectUpdate = {};
    if (name.trim() && name !== project.name) patch.name = name.trim();
    if (path.trim() && path !== project.path) patch.path = path.trim();
    if (launchCmd.trim() && launchCmd !== project.launch_cmd) patch.launch_cmd = launchCmd.trim();
    if (description !== (project.description ?? '')) patch.description = description.trim() || undefined;
    const parsedPort = expectedPort === '' ? undefined : Number(expectedPort);
    if (parsedPort !== project.expected_port && (parsedPort === undefined || !Number.isNaN(parsedPort))) {
      patch.expected_port = parsedPort;
    }
    if (Object.keys(patch).length === 0) {
      onClose();
      return;
    }
    setBusy(true);
    try {
      const updated = await patchProject(project.id, patch);
      onSaved(updated);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      role='dialog'
      aria-modal='true'
      aria-labelledby='project-form-title'
      style={overlayStyle}
      onClick={(e) => {
        if (e.target === e.currentTarget && !busy) onClose();
      }}
    >
      <form onSubmit={handleSubmit} style={panelStyle}>
        <h2 id='project-form-title' style={{ margin: 0, fontSize: 'var(--synapse-text-xl)' }}>
          {isEdit ? (
            <>Edit project — <code>{project?.id}</code></>
          ) : (
            'Add a project'
          )}
        </h2>
        {!isEdit && (
          <p style={{ margin: 0, color: 'var(--synapse-text-secondary)', fontSize: 'var(--synapse-text-sm)' }}>
            Register any app on your machine. It stays local — projects live in
            Synapse's database, never in the repo or on GitHub.
          </p>
        )}

        {!isEdit && (
          <Field label='ID (kebab-case, permanent)'>
            <input
              ref={firstFieldRef}
              value={id}
              onChange={(e) => setId(e.target.value.toLowerCase())}
              placeholder='my-app'
              style={inputStyle}
            />
          </Field>
        )}
        <Field label='Name'>
          <input
            ref={isEdit ? firstFieldRef : undefined}
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder='My App'
            style={inputStyle}
          />
        </Field>
        <Field label='Working directory'>
          <input
            value={path}
            onChange={(e) => setPath(e.target.value)}
            placeholder='C:\\Users\\you\\my-app'
            style={inputStyle}
          />
        </Field>
        <Field label='Launch command'>
          <input
            value={launchCmd}
            onChange={(e) => setLaunchCmd(e.target.value)}
            placeholder='npm start'
            style={inputStyle}
          />
        </Field>
        <Field label='Description (optional)'>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={2}
            style={{ ...inputStyle, fontFamily: 'var(--synapse-font-sans)', resize: 'vertical' }}
          />
        </Field>
        <Field label='Expected port (optional)'>
          <input
            value={expectedPort}
            onChange={(e) => setExpectedPort(e.target.value.replace(/[^0-9]/g, ''))}
            inputMode='numeric'
            placeholder='3000'
            style={inputStyle}
          />
        </Field>

        {error && (
          <p role='alert' style={{ margin: 0, color: 'var(--synapse-status-error)', fontSize: 'var(--synapse-text-sm)' }}>
            {error}
          </p>
        )}

        <footer style={{ display: 'flex', gap: 'var(--synapse-space-2)', justifyContent: 'flex-end' }}>
          <button type='button' onClick={onClose} disabled={busy} style={btn('ghost')}>
            Cancel
          </button>
          <button type='submit' disabled={busy} style={btn('primary')}>
            {busy ? 'Saving…' : isEdit ? 'Save' : 'Add project'}
          </button>
        </footer>
      </form>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }): JSX.Element {
  return (
    <label style={{ display: 'flex', flexDirection: 'column', gap: 'var(--synapse-space-2)' }}>
      <span style={{ fontSize: 'var(--synapse-text-sm)', color: 'var(--synapse-text-secondary)' }}>{label}</span>
      {children}
    </label>
  );
}

const overlayStyle: React.CSSProperties = {
  position: 'fixed',
  inset: 0,
  backgroundColor: 'var(--synapse-bg-overlay)',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  padding: 'var(--synapse-space-6)',
  zIndex: 100,
};

const panelStyle: React.CSSProperties = {
  width: 'min(640px, 100%)',
  maxHeight: '90vh',
  overflowY: 'auto',
  backgroundColor: 'var(--synapse-bg-surface)',
  borderWidth: '1px',
  borderStyle: 'solid',
  borderColor: 'var(--synapse-border-subtle)',
  borderRadius: 'var(--synapse-radius-lg)',
  padding: 'var(--synapse-space-8)',
  display: 'flex',
  flexDirection: 'column',
  gap: 'var(--synapse-space-4)',
};

const inputStyle: React.CSSProperties = {
  padding: 'var(--synapse-space-2) var(--synapse-space-3)',
  borderRadius: 'var(--synapse-radius-sm)',
  borderWidth: '1px',
  borderStyle: 'solid',
  borderColor: 'var(--synapse-border-strong)',
  backgroundColor: 'var(--synapse-bg-elevated)',
  color: 'var(--synapse-text-primary)',
  fontFamily: 'var(--synapse-font-mono)',
  fontSize: 'var(--synapse-text-sm)',
};

function btn(variant: 'primary' | 'ghost'): React.CSSProperties {
  const base: React.CSSProperties = {
    minHeight: '36px',
    padding: '0 var(--synapse-space-4)',
    borderRadius: 'var(--synapse-radius-md)',
    fontSize: 'var(--synapse-text-sm)',
    fontFamily: 'var(--synapse-font-sans)',
    cursor: 'pointer',
    borderWidth: '1px',
    borderStyle: 'solid',
    borderColor: 'transparent',
  };
  if (variant === 'primary') {
    return { ...base, backgroundColor: 'var(--synapse-accent)', color: 'var(--synapse-text-primary)' };
  }
  return {
    ...base,
    backgroundColor: 'transparent',
    borderColor: 'var(--synapse-border-strong)',
    color: 'var(--synapse-text-primary)',
  };
}
