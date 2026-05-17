// Apps page (Milestone F) -- project tiles + create/edit/delete/logs.
//
// Reads everything from the shared DaemonProvider context: projects, live
// resource snapshots, refresh. No own WebSocket.

import { useMemo, useState } from 'react';
import { FolderSearch, Plus } from 'lucide-react';

import { deleteProject } from '@shared/projects-client';
import type { Project } from '@shared/generated-types';
import { useDaemon } from '@shared/daemon-context';
import { Button } from '../components/ui/button';
import { Card } from '../components/ui/card';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { DiscoveryDialog } from '../components/DiscoveryDialog';
import { LogViewer } from '../components/LogViewer';
import { ProjectFormDialog, type ProjectFormMode } from '../components/ProjectFormDialog';
import { ProjectTile } from '../components/ProjectTile';
import { PageHeader } from '../components/PageHeader';

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

  // Pinned projects float to the top, then alphabetical.
  const sorted = useMemo(
    () =>
      [...projects].sort((a, b) => {
        if (a.pinned !== b.pinned) return a.pinned ? -1 : 1;
        return a.name.localeCompare(b.name);
      }),
    [projects]
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
        <div className='grid grid-cols-[repeat(auto-fill,minmax(320px,1fr))] gap-6'>
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
              onViewLogs={(project) => setLogsFor(project)}
              onChanged={(updated) => upsertProjectLocal(updated)}
              onActionError={(_p, err) => setActionError(err.message)}
            />
          ))}
        </div>
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
