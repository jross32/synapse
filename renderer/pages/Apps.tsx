// Apps page (Milestone F) -- project tiles + create/edit/delete/logs.
//
// Reads everything from the shared DaemonProvider context: projects, live
// resource snapshots, refresh. No own WebSocket.

import { useEffect, useMemo, useRef, useState } from 'react';
import { Activity, BookOpen, Download, FolderSearch, HelpCircle, Loader2, Plus, Search, X } from 'lucide-react';

import { deleteProject } from '@shared/projects-client';
import type { Project, ProjectKind } from '@shared/generated-types';
import { useDaemon } from '@shared/daemon-context';
import { handleTablistKeydown } from '@shared/tablist';
import { KIND_META, KIND_ORDER, kindMeta } from '@shared/project-kinds';
import { cn } from '@shared/utils';
import {
  importChatgpt,
  type ChatgptImportResponse,
} from '../lib/imports-client';
import { SynapseApiError } from '../lib/api-client';
import { Button } from '../components/ui/button';
import { Card } from '../components/ui/card';
import { Input } from '../components/ui/input';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { ChatgptImportHelp } from '../components/ChatgptImportHelp';
import { DiscoveryDialog } from '../components/DiscoveryDialog';
import { LogViewer } from '../components/LogViewer';
import { ProjectFormDialog, type ProjectFormMode } from '../components/ProjectFormDialog';
import { ProjectRecordsSection } from '../components/ProjectRecordsSection';
import { ProjectTile } from '../components/ProjectTile';
import { PageHeader } from '../components/PageHeader';
import { StatusLegend } from '../components/StatusLegend';
import { ProcessesPage } from './Processes';

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

type AppsSection = 'projects' | 'running' | 'memory';

interface FormState {
  mode: ProjectFormMode;
  project?: Project;
}

export interface AppsPageProps {
  initialSection?: AppsSection;
}

export function AppsPage({ initialSection = 'projects' }: AppsPageProps): JSX.Element {
  const {
    projects,
    projectsLoaded,
    projectsError,
    resourcesById,
    refreshProjects,
    upsertProjectLocal,
    removeProjectLocal,
  } = useDaemon();
  const [section, setSection] = useState<AppsSection>(initialSection);
  const [memoryProjectId, setMemoryProjectId] = useState<string>('');

  const [form, setForm] = useState<FormState | null>(null);
  const [deleting, setDeleting] = useState<Project | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [logsFor, setLogsFor] = useState<Project | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [discoveryOpen, setDiscoveryOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [kindFilter, setKindFilter] = useState<ProjectKind | 'all'>('all');
  const [importing, setImporting] = useState(false);
  const [importHelpOpen, setImportHelpOpen] = useState(false);
  const [importResult, setImportResult] = useState<ChatgptImportResponse | null>(null);
  const [importError, setImportError] = useState<string | null>(null);
  const importInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    setSection(initialSection);
  }, [initialSection]);

  async function handleImportFile(file: File): Promise<void> {
    setImporting(true);
    setImportError(null);
    setImportResult(null);
    try {
      const result = await importChatgpt(file);
      setImportResult(result);
      await refreshProjects();
    } catch (err) {
      const msg =
        err instanceof SynapseApiError
          ? err.envelope.message
          : (err as Error).message || 'Import failed';
      setImportError(msg);
    } finally {
      setImporting(false);
    }
  }

  // Pinned projects float to the top, then alphabetical.
  const sorted = useMemo(
    () =>
      [...projects].sort((a, b) => {
        if (a.pinned !== b.pinned) return a.pinned ? -1 : 1;
        return a.name.localeCompare(b.name);
      }),
    [projects]
  );

  // Count by kind so the chips can show "MCP (3)" etc. Empty kinds are
  // hidden -- a fresh registry shouldn't show seven empty chips.
  const kindCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const p of sorted) counts[p.kind] = (counts[p.kind] ?? 0) + 1;
    return counts;
  }, [sorted]);

  // Filter on every keystroke -- matches name, id, path, description, group,
  // tags, and launch command. Empty query => everything. The kind filter
  // intersects with the text filter.
  const visible = useMemo(
    () =>
      sorted.filter(
        (p) =>
          (kindFilter === 'all' || p.kind === kindFilter) && matchesQuery(p, query)
      ),
    [sorted, query, kindFilter]
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
        subtitle={
          section === 'projects'
            ? 'Your registered projects. Each tile is a folder Synapse manages. Installable plugins live in My Tools.'
            : section === 'memory'
            ? 'Project Memory — ADRs, backlog, and version history for a project. Synapse stores these so any AI session can read and add to them.'
            : 'Everything Synapse is running right now, with live CPU and memory telemetry.'
        }
        action={
          section === 'projects' &&
          <div className='flex flex-wrap justify-end gap-2'>
            <div className='flex items-stretch gap-1'>
              <Button
                variant='outline'
                onClick={() => importInputRef.current?.click()}
                disabled={importing}
                title='Upload a ChatGPT Settings → Data Controls → Export Data zip'
              >
                <Download className='h-4 w-4' />
                {importing ? 'Importing…' : 'Import ChatGPT export'}
              </Button>
              <button
                type='button'
                onClick={() => setImportHelpOpen(true)}
                aria-label='How does ChatGPT export import work?'
                title='How does this work?'
                className='inline-flex items-center justify-center rounded-md border border-input px-2 text-muted-foreground transition-colors hover:border-primary hover:text-foreground'
              >
                <HelpCircle className='h-4 w-4' aria-hidden='true' />
              </button>
            </div>
            <Button variant='outline' onClick={() => setDiscoveryOpen(true)}>
              <FolderSearch className='h-4 w-4' /> Scan for projects
            </Button>
            <Button onClick={() => setForm({ mode: 'create' })}>
              <Plus className='h-4 w-4' /> Add Project
            </Button>
            <input
              ref={importInputRef}
              type='file'
              accept='.zip,application/zip'
              className='hidden'
              onChange={(e) => {
                const file = e.target.files?.[0];
                e.target.value = '';
                if (file) void handleImportFile(file);
              }}
            />
          </div>
        }
      />

      <div
        role='tablist'
        aria-label='Apps sections'
        onKeyDown={handleTablistKeydown}
        className='flex flex-wrap gap-1 rounded-lg border border-border bg-secondary/30 p-1'
      >
        <TopTab
          active={section === 'projects'}
          onClick={() => setSection('projects')}
          label='Projects'
          icon={FolderSearch}
        />
        <TopTab
          active={section === 'running'}
          onClick={() => setSection('running')}
          label='Running Now'
          icon={Activity}
        />
        <TopTab
          active={section === 'memory'}
          onClick={() => {
            setMemoryProjectId((prev) => prev || sorted[0]?.id || '');
            setSection('memory');
          }}
          label='Memory'
          icon={BookOpen}
        />
      </div>

      {section === 'running' ? (
        <ProcessesPage headerless />
      ) : section === 'memory' ? (
        <div className='flex flex-col gap-4'>
          {sorted.length === 0 ? (
            <Card className='flex flex-col items-center gap-3 p-8 text-center'>
              <BookOpen className='h-8 w-8 text-muted-foreground' />
              <p className='text-sm text-muted-foreground'>No projects yet. Add one in Projects to start tracking decisions and backlog here.</p>
            </Card>
          ) : (
            <>
              <Card className='flex items-center gap-3 p-3'>
                <label htmlFor='memory-project-select' className='text-sm font-medium whitespace-nowrap'>
                  Project
                </label>
                <select
                  id='memory-project-select'
                  value={memoryProjectId}
                  onChange={(e) => setMemoryProjectId(e.target.value)}
                  className='flex-1 h-9 rounded-md border border-input bg-transparent px-3 text-sm'
                >
                  {sorted.map((p) => (
                    <option key={p.id} value={p.id}>{p.name}</option>
                  ))}
                </select>
              </Card>
              {memoryProjectId && <ProjectRecordsSection projectId={memoryProjectId} />}
            </>
          )}
        </div>
      ) : (
        <>

      {(importResult || importError) && (
        <Card
          role={importError ? 'alert' : 'status'}
          className={cn(
            'flex items-start justify-between gap-3 p-4 text-sm',
            importError
              ? 'border-destructive/40 bg-destructive/5 text-destructive'
              : 'border-emerald-500/30 bg-emerald-500/5'
          )}
        >
          <div className='space-y-1'>
            {importError ? (
              <p>
                <strong>ChatGPT import failed:</strong> {importError}
              </p>
            ) : importResult ? (
              <>
                <p>
                  <strong>Imported {importResult.imported} conversation
                  {importResult.imported === 1 ? '' : 's'}</strong> into the{' '}
                  <code className='font-mono'>{importResult.project_id}</code> project.
                </p>
                {(importResult.duplicates > 0 || importResult.skipped_empty > 0) && (
                  <p className='text-xs text-muted-foreground'>
                    {importResult.duplicates > 0 &&
                      `${importResult.duplicates} duplicate${importResult.duplicates === 1 ? '' : 's'} skipped. `}
                    {importResult.skipped_empty > 0 &&
                      `${importResult.skipped_empty} empty chat${importResult.skipped_empty === 1 ? '' : 's'} skipped.`}
                  </p>
                )}
                {importResult.note && (
                  <p className='text-xs text-muted-foreground'>{importResult.note}</p>
                )}
              </>
            ) : null}
          </div>
          <button
            type='button'
            aria-label='Dismiss'
            onClick={() => {
              setImportResult(null);
              setImportError(null);
            }}
            className='rounded p-1 text-muted-foreground hover:bg-accent hover:text-foreground'
          >
            <X className='h-4 w-4' />
          </button>
        </Card>
      )}

      {actionError && (
        <p role='alert' className='text-sm text-destructive'>
          {actionError}
        </p>
      )}

      {!projectsLoaded ? (
        <Card className='flex items-center justify-center gap-2 border-dashed p-12 text-center text-sm text-muted-foreground'>
          <Loader2 className='h-4 w-4 animate-spin' /> Loading your projects…
        </Card>
      ) : projectsError ? (
        <Card className='border-dashed p-12 text-center'>
          <h3 className='text-lg font-semibold'>Couldn&apos;t load your projects</h3>
          <p role='alert' className='mx-auto mt-2 max-w-md text-sm text-destructive'>{projectsError}</p>
          <div className='mt-4 flex justify-center'>
            <Button variant='outline' onClick={() => void refreshProjects()}>
              Retry
            </Button>
          </div>
        </Card>
      ) : projects.length === 0 ? (
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
              {query || kindFilter !== 'all'
                ? `${visible.length} of ${sorted.length} project${sorted.length === 1 ? '' : 's'}`
                : `${sorted.length} project${sorted.length === 1 ? '' : 's'}`}
            </span>
          </div>

          {/* Kind filter chips (v0.1.19). Only non-empty kinds are shown so
              the row stays tight while a registry has a narrow mix. The
              status legend (v0.1.35) sits at the end so users can decode
              idle vs stopped at a glance. */}
          <div className='flex flex-wrap items-center gap-1.5'>
            <KindChip
              label='All'
              count={sorted.length}
              active={kindFilter === 'all'}
              onClick={() => setKindFilter('all')}
            />
            {KIND_ORDER.filter((k) => (kindCounts[k] ?? 0) > 0).map((k) => (
              <KindChip
                key={k}
                label={KIND_META[k].label}
                count={kindCounts[k] ?? 0}
                active={kindFilter === k}
                onClick={() => setKindFilter(k)}
                icon={KIND_META[k].icon}
              />
            ))}
            <span className='ml-auto'>
              <StatusLegend />
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

      <ChatgptImportHelp
        open={importHelpOpen}
        onClose={() => setImportHelpOpen(false)}
      />
        </>
      )}
    </div>
  );
}


interface KindChipProps {
  label: string;
  count: number;
  active: boolean;
  onClick: () => void;
  icon?: typeof Search;
}

function KindChip({ label, count, active, onClick, icon: Icon }: KindChipProps): JSX.Element {
  return (
    <button
      type='button'
      onClick={onClick}
      className={cn(
        'flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium transition-colors',
        active
          ? 'border-primary bg-primary text-primary-foreground'
          : 'border-border bg-secondary/40 text-muted-foreground hover:text-foreground'
      )}
    >
      {Icon && <Icon className='h-3 w-3' />}
      <span>{label}</span>
      <span
        className={cn(
          'rounded-full px-1.5 text-[10px] font-semibold tabular-nums',
          active ? 'bg-primary-foreground/20 text-primary-foreground' : 'bg-background/60'
        )}
      >
        {count}
      </span>
    </button>
  );
}

function TopTab({
  active,
  onClick,
  label,
  icon: Icon,
}: {
  active: boolean;
  onClick: () => void;
  label: string;
  icon: typeof Search;
}): JSX.Element {
  return (
    <button
      type='button'
      role='tab'
      aria-selected={active}
      onClick={onClick}
      className={cn(
        'flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors',
        active
          ? 'bg-card text-foreground shadow-sm'
          : 'text-muted-foreground hover:text-foreground'
      )}
    >
      <Icon className='h-4 w-4' />
      {label}
    </button>
  );
}
