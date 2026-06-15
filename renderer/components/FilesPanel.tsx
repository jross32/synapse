// FilesPanel -- per-project (or shared) file management (ADR-0003 Phase A · v0.1.31).
//
// Drag-drop multi-file upload, click-to-pick fallback, listing of existing
// files with size + source + uploaded_at, per-row download + delete. Drives
// the Project tile's "Files" dialog and -- eventually -- the workbench
// landing pane.

import { useEffect, useRef, useState } from 'react';
import {
  ArrowDownToLine,
  FileText,
  Loader2,
  Plus,
  ScrollText,
  Sparkles,
  Trash2,
  Upload,
} from 'lucide-react';

import type { ProjectFile } from '@shared/generated-types';
import {
  deleteFile,
  downloadFile,
  listProjectFiles,
  listSharedFiles,
  uploadFiles,
} from '@shared/files-client';
import { cn } from '@shared/utils';
import { Button } from './ui/button';
import { Card } from './ui/card';
import { UploadPreviewDialog } from './UploadPreviewDialog';

export interface FilesPanelProps {
  /** Pass null for the shared workspace. */
  projectId: string | null;
}

function fmtSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

function fmtDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

function SourceIcon({ source }: { source: ProjectFile['source'] }): JSX.Element {
  if (source === 'transcript') return <ScrollText className='h-3.5 w-3.5 text-amber-400' />;
  if (source === 'chatgpt-import') return <Sparkles className='h-3.5 w-3.5 text-emerald-400' />;
  return <FileText className='h-3.5 w-3.5 text-muted-foreground' />;
}

export function FilesPanel({ projectId }: FilesPanelProps): JSX.Element {
  const [files, setFiles] = useState<ProjectFile[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  // Phase B: picked files sit here until the user confirms in the preview dialog.
  const [previewing, setPreviewing] = useState<File[] | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  async function refresh(): Promise<void> {
    setError(null);
    try {
      const list = projectId === null ? await listSharedFiles() : await listProjectFiles(projectId);
      setFiles(list);
    } catch (err) {
      setError((err as Error).message || 'Failed to load files');
    }
  }

  useEffect(() => {
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  async function handleUpload(filesToSend: File[]): Promise<void> {
    if (filesToSend.length === 0) return;
    setBusy(true);
    setError(null);
    setUploadProgress(0);
    try {
      const res = await uploadFiles(projectId, filesToSend, {
        onProgress: (loaded, total) =>
          setUploadProgress(total > 0 ? Math.round((loaded / total) * 100) : null),
      });
      const failed = res.files.filter((f) => !f.ok);
      if (failed.length > 0) {
        setError(`${failed.length} file${failed.length === 1 ? '' : 's'} rejected: ${failed.map((f) => f.reason).join(', ')}`);
      }
      await refresh();
    } catch (err) {
      setError((err as Error).message || 'Upload failed');
    } finally {
      setBusy(false);
      setUploadProgress(null);
    }
  }

  async function handleDelete(file: ProjectFile): Promise<void> {
    if (!window.confirm(`Delete "${file.original_name}"?`)) return;
    try {
      await deleteFile(projectId, file.id);
      setFiles((prev) => prev?.filter((f) => f.id !== file.id) ?? null);
    } catch (err) {
      setError((err as Error).message || 'Delete failed');
    }
  }

  return (
    <div className='flex min-h-[300px] flex-col gap-4'>
      {/* Drop zone + picker */}
      <div
        role='button'
        tabIndex={0}
        aria-label='Drag files here or click to pick'
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          const dropped = Array.from(e.dataTransfer.files);
          if (dropped.length > 0) setPreviewing(dropped);
        }}
        className={cn(
          'flex cursor-pointer items-center justify-center gap-3 rounded-lg border-2 border-dashed p-6 text-sm transition-colors',
          dragOver
            ? 'border-primary bg-primary/10 text-foreground'
            : 'border-border bg-secondary/30 text-muted-foreground hover:bg-secondary/50'
        )}
      >
        {busy ? (
          <>
            <Loader2 className='h-5 w-5 animate-spin text-primary' />
            <span>
              Uploading{uploadProgress !== null ? ` -- ${uploadProgress}%` : '...'}
            </span>
          </>
        ) : (
          <>
            <Upload className='h-5 w-5 text-primary' />
            <span>
              Drop files here, or <span className='font-semibold text-foreground'>click to pick</span>
            </span>
          </>
        )}
        <input
          ref={inputRef}
          type='file'
          multiple
          className='hidden'
          onChange={(e) => {
            const picked = Array.from(e.target.files ?? []);
            if (picked.length > 0) setPreviewing(picked);
            e.target.value = ''; // allow re-picking the same file
          }}
        />
      </div>

      {error && (
        <p role='alert' className='text-sm text-destructive'>
          {error}
        </p>
      )}

      {/* File list */}
      {files === null ? (
        <Card className='flex items-center justify-center gap-2 p-8 text-sm text-muted-foreground'>
          <Loader2 className='h-4 w-4 animate-spin' /> Loading...
        </Card>
      ) : files.length === 0 ? (
        <Card className='flex flex-col items-center gap-2 border-dashed p-8 text-center text-sm text-muted-foreground'>
          <Plus className='h-6 w-6' />
          <p>
            No files {projectId === null ? 'in the shared workspace yet' : 'in this project yet'}.
          </p>
          <p className='text-xs'>
            AI sessions launched in a workbench see uploaded files under{' '}
            <code className='font-mono'>$SYNAPSE_FILES</code>.
          </p>
        </Card>
      ) : (
        <ul className='flex flex-col divide-y divide-border rounded-md border border-border'>
          {files.map((f) => (
            <li
              key={f.id}
              className='flex flex-wrap items-center gap-3 px-3 py-2 text-sm'
            >
              <SourceIcon source={f.source} />
              <div className='min-w-0 flex-1'>
                <div className='truncate font-medium'>{f.original_name}</div>
                <div className='font-mono text-[11px] text-muted-foreground'>
                  {fmtSize(f.size_bytes)} · {f.source}
                  {f.duplicate_of && ' · duplicate'}
                  {' · '}
                  {fmtDate(f.uploaded_at)}
                </div>
              </div>
              <Button
                variant='ghost'
                size='sm'
                className='h-7 px-2 text-xs'
                onClick={() => void downloadFile(projectId, f.id, f.original_name)}
                title='Download'
              >
                <ArrowDownToLine className='h-3.5 w-3.5' />
              </Button>
              <Button
                variant='ghost'
                size='sm'
                className='h-7 px-2 text-xs text-destructive hover:bg-destructive/10'
                onClick={() => void handleDelete(f)}
                title='Delete'
              >
                <Trash2 className='h-3.5 w-3.5' />
              </Button>
            </li>
          ))}
        </ul>
      )}

      {/* Phase B: pre-upload inspection. Drives the actual POST only after
          the user confirms in the dialog. */}
      <UploadPreviewDialog
        open={previewing !== null}
        pickedFiles={previewing ?? []}
        onCancel={() => setPreviewing(null)}
        onConfirm={(confirmed) => {
          setPreviewing(null);
          void handleUpload(confirmed);
        }}
      />
    </div>
  );
}
