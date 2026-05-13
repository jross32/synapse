// Modal edit dialog for a Project (Contract #1 — editable from UI).
//
// Renders a focused-trapped overlay with the editable fields. Saves via
// PATCH /api/v1/projects/{id}. Full env-var editor + secrets storage UI
// lands in Milestone F; this dialog covers the name / path / launch_cmd /
// description / expected_port set that gets us through Milestone D.

import { useEffect, useRef, useState } from 'react';

import { patchProject } from '../lib/projects-client';
import type { Project, ProjectUpdate } from '../lib/generated-types';

export interface ProjectEditDialogProps {
  project: Project;
  onSaved: (updated: Project) => void;
  onClose: () => void;
}

export function ProjectEditDialog({ project, onSaved, onClose }: ProjectEditDialogProps): JSX.Element {
  const [name, setName] = useState(project.name);
  const [path, setPath] = useState(project.path);
  const [launchCmd, setLaunchCmd] = useState(project.launch_cmd);
  const [description, setDescription] = useState(project.description ?? '');
  const [expectedPort, setExpectedPort] = useState<string>(
    project.expected_port === null ? '' : String(project.expected_port)
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const firstFieldRef = useRef<HTMLInputElement | null>(null);

  // Focus the first field on mount + Esc to close.
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
    setBusy(true);
    setError(null);
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
      aria-labelledby='edit-dialog-title'
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
        if (e.target === e.currentTarget && !busy) onClose();
      }}
    >
      <form
        onSubmit={handleSubmit}
        style={{
          width: 'min(640px, 100%)',
          maxHeight: '90vh',
          overflowY: 'auto',
          backgroundColor: 'var(--synapse-bg-surface)',
          border: '1px solid var(--synapse-border-subtle)',
          borderRadius: 'var(--synapse-radius-lg)',
          padding: 'var(--synapse-space-8)',
          display: 'flex',
          flexDirection: 'column',
          gap: 'var(--synapse-space-4)',
        }}
      >
        <h2 id='edit-dialog-title' style={{ margin: 0, fontSize: 'var(--synapse-text-xl)' }}>
          Edit project — <code>{project.id}</code>
        </h2>

        <Field label='Name'>
          <input ref={firstFieldRef} value={name} onChange={(e) => setName(e.target.value)} style={inputStyle} />
        </Field>
        <Field label='Working directory'>
          <input value={path} onChange={(e) => setPath(e.target.value)} style={inputStyle} />
        </Field>
        <Field label='Launch command'>
          <input value={launchCmd} onChange={(e) => setLaunchCmd(e.target.value)} style={inputStyle} />
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
            {busy ? 'Saving…' : 'Save'}
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

const inputStyle: React.CSSProperties = {
  padding: 'var(--synapse-space-2) var(--synapse-space-3)',
  borderRadius: 'var(--synapse-radius-sm)',
  border: '1px solid var(--synapse-border-strong)',
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
    border: '1px solid transparent',
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
