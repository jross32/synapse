// Apps page (Milestone F) -- project tiles + create/edit/delete/logs.
//
// Reads everything from the shared DaemonProvider context: projects, live
// resource snapshots, refresh. No own WebSocket.

import { useMemo, useState } from 'react';
import { FolderSearch, Plus, Search, X } from 'lucide-react';

import { deleteProject } from '@shared/projects-client';
import type { Project } from '@shared/generated-types';
import { useDaemon } from '@shared/daemon-context';
import { Button } from '../components/ui/button';
import { Card } from '../components/ui/card';
import { Input } from '../components/ui/input';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { DiscoveryDialog } from '../components/DiscoveryDialog';
import { LogViewer } from '../components/LogViewer';
import { ProjectFormDialog, type ProjectFormMode } from '../components/ProjectFormDialog';
import { ProjectTile } from '../components/ProjectTile';
import { PageHeader } from '../components/PageHeader';

function matchesQuery(p: Project, q: string): boolean {
  if (!q) return true;
  const haystack = [
    p.name,
    p.id,
    p.path,
    p.description ?? '',
    p.group ?? '',
    (p.tags ?? []).join(' '),
    p.launch_cmd,
  ]
    .join(' ')
    .toLowerCase();
  return q
    .toLowerCase()
    .split(/\s+/)
    .filter(Boolean)
    .every((word) => haystack.includes(word));
}

interface FormState {
  mode: ProjectFormMode;
  project?: Project;
}

export function AppsPage(): JSX.Element {
  const { projects, resourcesById, refreshProjects, upsertProjectLocal, removeProjectLocal } =
    useDaemon();

  const [form, setForm] = useState<FormState | null>(null);
  const [deleting, setDeleting] = useState<Project | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [logsFor, setLogsFor] = useState<Project | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [discoveryOpen, setDiscoveryOpen] = useState(false);
  const [query, setQuery] = useState('');

  // Pinned projects float to the top, then alphabetical.
  const sorted = useMemo(
    () =>
      [...projects].sort((a, b) => {
        if (a.pinned !== b.pinned) return a.pinned ? -1 : 1;
        return a.name.localeCompare(b.name);
      }),
    [projects]
  );

  // Filter on every keystroke -- matches name, id, path, description, group,
  // tags, and launch command. Empty query => everything.
  const visible = useMemo(
    () => sorted.filter((p) => matchesQuery(p, query)),
    [sorted, query]
  );

  async function handleConfirmDelete(target: Project): Promise<void> {
    try {
      await deleteProject(target.id);
      removeProjectLocal(target.id);
      setDeleting(null);
      setDeleteError(null);
    } catch (err) {
      setDeleteError((err as Error).message || 'Delete failed');
    }
  }

  return (
    <div className='flex flex-col gap-6'>
      <PageHeader
        title='Apps'
        subtitle="Launchable projects under Synapse's management. Click a tile to start it."
        action={
          <div className='flex gap-2'>
            <Button variant='outline' onClick={() => setDiscoveryOpen(true)}>
              <FolderSearch className='h-4 w-4' /> Scan for projects
            </Button>
            <Button onClick={() => setForm({ mode: 'create' })}>
              <Plus className='h-4 w-4' /> Add Project
            </Button>
          </div>
        }
      />

      {actionError && (
        <p role='alert' className='text-sm text-destructive'>
          {actionError}
        </p>
      )}

      {projects.length === 0 ? (
        <Card className='border-dashed p-12 text-center'>
          <h3 className='text-lg font-semibold'>No projects yet</h3>
          <p className='mx-auto mt-2 max-w-md text-sm text-muted-foreground'>
            Add any app on your machine — Synapse will launch it, monitor it, and keep its
            logs. Or scan a folder and let auto-discovery find them all.
          </p>
          <div className='mt-4 flex justify-center gap-2'>
            <Button variant='outline' onClick={() => setDiscoveryOpen(true)}>
              <FolderSearch className='h-4 w-4' /> Scan a folder
            </Button>
            <Button onClick={() => setForm({ mode: 'create' })}>
              <Plus className='h-4 w-4' /> Add your first project
            </Button>
          </div>
        </Card>
      ) : (
        <>
          <div className='flex flex-wrap items-center gap-3'>
            <div className='relative grow sm:max-w-md'>
              <Search className='pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground' />
              <Input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder='Filter by name, path, tag, group…'
                className='pl-9 pr-9'
                aria-label='Filter projects'
              />
              {query && (
                <button
                  type='button'
                  aria-label='Clear filter'
                  onClick={() => setQuery('')}
                  className='absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-muted-foreground hover:bg-accent hover:text-foreground'
                >
                  <X className='h-3.5 w-3.5' />
                </button>
              )}
            </div>
            <span className='text-xs text-muted-foreground'>
              {query
                ? `${visible.length} of ${sorted.length} project${sorted.length === 1 ? '' : 's'}`
                : `${sorted.length} project${sorted.length === 1 ? '' : 's'}`}
            </span>
          </div>

          {visible.length === 0 ? (
            <Card className='border-dashed p-10 text-center text-sm text-muted-foreground'>
              Nothing matches "{query}". Try a different word, or clear the filter.
            </Card>
          ) : (
            <div className='grid grid-cols-[repeat(auto-fill,minmax(min(100%,320px),1fr))] gap-6'>
              {visible.map((p) => (
                <ProjectTile
                  key={p.id}
                  project={p}
                  resources={resourcesById[p.id]}
                  onEdit={(project) => setForm({ mode: 'edit', project })}
                  onDelete={(project) => {
                    setDeleteError(null);
                    setDeleting(project);
                  }}
                  onViewLogs={(project) => setLogsFor(project)}
                  onChanged={(updated) => upsertProjectLocal(updated)}
                  onActionError={(_p, err) => setActionError(err.message)}
                />
              ))}
            </div>
          )}
        </>
      )}

      {form && (
        <ProjectFormDialog
          open
          mode={form.mode}
          project={form.project}
          onSaved={(saved) => {
            upsertProjectLocal(saved);
            void refreshProjects();
            setForm(null);
          }}
          onClose={() => setForm(null)}
        />
      )}

      <ConfirmDialog
        open={deleting !== null}
        title={deleting ? `Delete "${deleting.name}"?` : ''}
        body={
          deleting && (
            <>
              <p>
                Synapse will soft-delete this project's registry row. The on-disk app at{' '}
                <code className='font-mono'>{deleting.path}</code> stays untouched.
              </p>
              <p className='text-xs text-muted-foreground'>
                You can re-add it any time with "+ Add Project".
              </p>
            </>
          )
        }
        confirmLabel='Delete project'
        danger
        error={deleteError}
        onConfirm={() => deleting && handleConfirmDelete(deleting)}
        onCancel={() => {
          setDeleting(null);
          setDeleteError(null);
        }}
      />

      <LogViewer open={logsFor !== null} project={logsFor} onClose={() => setLogsFor(null)} />

      <DiscoveryDialog
        open={discoveryOpen}
        onClose={() => setDiscoveryOpen(false)}
        onImported={() => {
          setDiscoveryOpen(false);
          void refreshProjects();
        }}
      />
    </div>
  );
}
