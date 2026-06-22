// Create / edit dialog for a Project (Contract #1 -- editable from the UI).
//
//   mode="create" -- the "+ Add Project" flow: id + name + path + launch cmd.
//   mode="edit"   -- pre-filled from an existing project; PATCHes the diff.

import { useState } from 'react';

import { createProject, patchProject } from '@shared/projects-client';
import type { Project, ProjectKind, ProjectUpdate } from '@shared/generated-types';
import { KIND_META, KIND_ORDER } from '@shared/project-kinds';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Modal } from './ui/modal';

export type ProjectFormMode = 'create' | 'edit';

export interface ProjectFormDialogProps {
  open: boolean;
  mode: ProjectFormMode;
  project?: Project;
  onSaved: (project: Project) => void;
  onClose: () => void;
}

const ID_RE = /^[a-z][a-z0-9-]*[a-z0-9]$|^[a-z]$/;

function slugifyProjectId(value: string): string {
  const base = value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
  if (!base) return '';
  if (/^[a-z]/.test(base)) return base;
  return `project-${base}`;
}

export function ProjectFormDialog({
  open,
  mode,
  project,
  onSaved,
  onClose,
}: ProjectFormDialogProps): JSX.Element | null {
  const isEdit = mode === 'edit';

  const [id, setId] = useState(project?.id ?? '');
  const [name, setName] = useState(project?.name ?? '');
  const [path, setPath] = useState(project?.path ?? '');
  const [launchCmd, setLaunchCmd] = useState(project?.launch_cmd ?? '');
  const [description, setDescription] = useState(project?.description ?? '');
  const [group, setGroup] = useState(project?.group ?? '');
  const [expectedPort, setExpectedPort] = useState<string>(
    project?.expected_port == null ? '' : String(project.expected_port)
  );
  const [kind, setKind] = useState<ProjectKind>(project?.kind ?? 'app');
  const [createPath, setCreatePath] = useState(true);
  const [idTouched, setIdTouched] = useState(Boolean(project?.id));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent): Promise<void> {
    e.preventDefault();
    setError(null);
    await (isEdit ? submitEdit() : submitCreate());
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
      onSaved(
        await createProject({
          id: id.trim(),
          name: name.trim(),
          path: path.trim(),
          launch_cmd: launchCmd.trim(),
          create_path: createPath,
          description: description.trim() || null,
          expected_port: expectedPort === '' ? null : Number(expectedPort),
          group: group.trim() || null,
          kind,
        })
      );
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
    if (group !== (project.group ?? '')) patch.group = group.trim() || null;
    const parsedPort = expectedPort === '' ? undefined : Number(expectedPort);
    if (parsedPort !== project.expected_port && (parsedPort === undefined || !Number.isNaN(parsedPort))) {
      patch.expected_port = parsedPort;
    }
    if (kind !== project.kind) patch.kind = kind;
    if (Object.keys(patch).length === 0) {
      onClose();
      return;
    }
    setBusy(true);
    try {
      onSaved(await patchProject(project.id, patch));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal open={open} onClose={onClose} labelledBy='project-form-title' dismissable={!busy}>
      <form onSubmit={handleSubmit} className='flex flex-col gap-4'>
        <h2 id='project-form-title' className='text-xl font-semibold'>
          {isEdit ? (
            <>
              Edit project — <code className='font-mono text-base'>{project?.id}</code>
            </>
          ) : (
            'Add a project'
          )}
        </h2>
        {!isEdit && (
          <p className='text-sm text-muted-foreground'>
            Register any app on your machine. It stays local — projects live in Synapse's
            database, never in the repo or on GitHub.
          </p>
        )}

        {!isEdit && (
          <Field label='ID (kebab-case, permanent)'>
            <Input
              value={id}
              onChange={(e) => {
                setIdTouched(true);
                setId(e.target.value.toLowerCase());
              }}
              placeholder='my-app'
            />
          </Field>
        )}
        <Field label='Name'>
          <Input
            value={name}
            onChange={(e) => {
              const next = e.target.value;
              setName(next);
              if (!isEdit && !idTouched) {
                setId(slugifyProjectId(next));
              }
            }}
            placeholder='My App'
          />
        </Field>
        <Field label='Working directory'>
          <Input value={path} onChange={(e) => setPath(e.target.value)} placeholder='C:\Users\you\my-app' />
        </Field>
        {!isEdit && (
          <label className='flex items-start gap-3 rounded-xl border border-border/70 bg-secondary/20 px-3 py-3 text-sm'>
            <input
              type='checkbox'
              className='mt-0.5 h-4 w-4 rounded border-border'
              checked={createPath}
              onChange={(e) => setCreatePath(e.target.checked)}
            />
            <span className='min-w-0'>
              <span className='font-medium text-foreground'>Create the folder if it does not exist yet</span>
              <span className='mt-1 block text-xs text-muted-foreground'>
                Handy from mobile or hosted browser sessions where the AI cannot open a native
                file picker or make a folder through your local OS shell first.
              </span>
            </span>
          </label>
        )}
        <Field label='Launch command'>
          <Input value={launchCmd} onChange={(e) => setLaunchCmd(e.target.value)} placeholder='npm start' />
        </Field>
        <Field label='Description (optional)'>
          <Input value={description} onChange={(e) => setDescription(e.target.value)} />
        </Field>
        <Field label='Group (optional)'>
          <Input value={group} onChange={(e) => setGroup(e.target.value)} placeholder='e.g. AI, Scraping, Games' />
        </Field>
        <Field label='Expected port (optional)'>
          <Input
            value={expectedPort}
            onChange={(e) => setExpectedPort(e.target.value.replace(/[^0-9]/g, ''))}
            inputMode='numeric'
            placeholder='3000'
          />
        </Field>
        <Field label='Kind'>
          <select
            value={kind}
            onChange={(e) => setKind(e.target.value as ProjectKind)}
            // colorScheme: 'dark' tells Windows + macOS to render the
            // native dropdown panel in its dark variant (light otherwise).
            // The <option> elements are OS-painted; CSS classes don't
            // reach them.
            style={{ colorScheme: 'dark' }}
            className='h-9 rounded-md border border-input bg-card px-3 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring'
          >
            {KIND_ORDER.map((k) => (
              <option key={k} value={k} className='bg-card text-foreground'>
                {KIND_META[k].label}
              </option>
            ))}
          </select>
        </Field>

        {error && (
          <p role='alert' className='text-sm text-destructive'>
            {error}
          </p>
        )}

        <div className='flex justify-end gap-2'>
          <Button type='button' variant='outline' disabled={busy} onClick={onClose}>
            Cancel
          </Button>
          <Button type='submit' disabled={busy}>
            {busy ? 'Saving…' : isEdit ? 'Save' : 'Add project'}
          </Button>
        </div>
      </form>
    </Modal>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }): JSX.Element {
  return (
    <label className='flex flex-col gap-1.5'>
      <span className='text-sm text-muted-foreground'>{label}</span>
      {children}
    </label>
  );
}
