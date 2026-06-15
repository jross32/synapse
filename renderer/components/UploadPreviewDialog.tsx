// Pre-upload "are you sure?" dialog (ADR-0003 Phase B · v0.1.31.5).
//
// Sits between the file picker and the actual multipart POST. Inspects each
// picked File via lib/file-inspect, surfaces executable warnings (the
// safety-critical ones), shows a text preview for plain files, and lets the
// user untick anything before confirming.

import { useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  CheckSquare,
  FileCode,
  FileImage,
  FileText,
  FileWarning,
  FolderTree,
  Loader2,
  Music2,
  Package,
  Shapes,
  Square,
  Video,
  X,
} from 'lucide-react';

import { formatSize, inspectAll, type InspectedFile } from '@shared/file-inspect';
import { cn } from '@shared/utils';
import { Button } from './ui/button';
import { Modal } from './ui/modal';

export interface UploadPreviewDialogProps {
  open: boolean;
  pickedFiles: File[];
  onCancel: () => void;
  onConfirm: (files: File[]) => void;
}

function KindIcon({ kind, isExe }: { kind: InspectedFile['detected_kind']; isExe: boolean }): JSX.Element {
  if (isExe) return <FileWarning className='h-4 w-4 text-destructive' />;
  if (kind === 'text') return <FileText className='h-4 w-4 text-muted-foreground' />;
  if (kind === 'image') return <FileImage className='h-4 w-4 text-sky-400' />;
  if (kind === 'archive') return <Package className='h-4 w-4 text-amber-400' />;
  if (kind === 'audio') return <Music2 className='h-4 w-4 text-emerald-400' />;
  if (kind === 'video') return <Video className='h-4 w-4 text-emerald-400' />;
  if (kind === 'pdf') return <FileText className='h-4 w-4 text-rose-400' />;
  if (kind === 'office') return <FileCode className='h-4 w-4 text-sky-400' />;
  return <Shapes className='h-4 w-4 text-muted-foreground' />;
}

export function UploadPreviewDialog({
  open,
  pickedFiles,
  onCancel,
  onConfirm,
}: UploadPreviewDialogProps): JSX.Element | null {
  const [inspected, setInspected] = useState<InspectedFile[] | null>(null);
  const [keep, setKeep] = useState<Record<number, boolean>>({});

  useEffect(() => {
    if (!open || pickedFiles.length === 0) {
      setInspected(null);
      setKeep({});
      return;
    }
    let cancelled = false;
    void inspectAll(pickedFiles).then((rows) => {
      if (cancelled) return;
      setInspected(rows);
      // Default: keep everything that isn't a folder / a zero-byte folder entry.
      const defaults: Record<number, boolean> = {};
      rows.forEach((r, i) => {
        defaults[i] = !r.looks_like_folder;
      });
      setKeep(defaults);
    });
    return () => {
      cancelled = true;
    };
  }, [open, pickedFiles]);

  const selected = useMemo(
    () => (inspected ?? []).filter((_, i) => keep[i]),
    [inspected, keep]
  );
  const exeCount = selected.filter((r) => r.is_executable).length;
  const folderCount = (inspected ?? []).filter((r) => r.looks_like_folder).length;
  const totalBytes = selected.reduce((acc, r) => acc + r.size_bytes, 0);

  if (!open) return null;

  return (
    <Modal
      open
      onClose={onCancel}
      labelledBy='upload-preview-title'
      className='!max-w-3xl'
    >
      <div className='flex items-start justify-between gap-3'>
        <div>
          <h2 id='upload-preview-title' className='text-lg font-semibold'>
            Review {pickedFiles.length} file{pickedFiles.length === 1 ? '' : 's'} before upload
          </h2>
          <p className='mt-1 text-sm text-muted-foreground'>
            Synapse inspected each file before sending. Untick anything you don't want.
          </p>
        </div>
        <button
          type='button'
          aria-label='Cancel upload'
          onClick={onCancel}
          className='rounded-md p-1 text-muted-foreground hover:bg-accent hover:text-foreground'
        >
          <X className='h-4 w-4' />
        </button>
      </div>

      {folderCount > 0 && (
        <p
          role='alert'
          className='flex items-center gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-200'
        >
          <FolderTree className='h-4 w-4' />
          {folderCount === 1 ? '1 entry looks like a folder' : `${folderCount} entries look like folders`}
          {' '} -- the browser doesn't expand folders into files automatically. Drop the
          files themselves, or pick them individually.
        </p>
      )}

      {exeCount > 0 && (
        <p
          role='alert'
          className='flex items-center gap-2 rounded-md border border-destructive/50 bg-destructive/15 px-3 py-2 text-sm text-destructive-foreground'
        >
          <AlertTriangle className='h-4 w-4' />
          <span>
            <strong>{exeCount} executable file{exeCount === 1 ? '' : 's'} in the batch.</strong>{' '}
            These run on this machine if anything launches them. Untick anything you don't trust.
          </span>
        </p>
      )}

      {inspected === null ? (
        <div className='flex items-center justify-center gap-2 py-8 text-sm text-muted-foreground'>
          <Loader2 className='h-4 w-4 animate-spin' /> Inspecting files...
        </div>
      ) : (
        <ul className='flex max-h-[50vh] flex-col divide-y divide-border overflow-y-auto rounded-md border border-border'>
          {inspected.map((row, i) => {
            const checked = keep[i] ?? false;
            const blockedByFolder = row.looks_like_folder;
            return (
              <li
                key={`${row.file.name}-${i}`}
                className={cn(
                  'flex flex-wrap items-start gap-3 px-3 py-2 text-sm',
                  row.is_executable && checked && 'bg-destructive/10',
                  blockedByFolder && 'opacity-60'
                )}
              >
                <button
                  type='button'
                  aria-label={checked ? 'Untick file' : 'Tick file'}
                  disabled={blockedByFolder}
                  onClick={() => setKeep((prev) => ({ ...prev, [i]: !prev[i] }))}
                  className='mt-0.5 shrink-0'
                >
                  {checked ? (
                    <CheckSquare className='h-4 w-4 text-primary' />
                  ) : (
                    <Square className='h-4 w-4 text-muted-foreground' />
                  )}
                </button>
                <KindIcon kind={row.detected_kind} isExe={row.is_executable} />
                <div className='min-w-0 flex-1'>
                  <div className='truncate font-medium'>{row.file.name}</div>
                  <div className='font-mono text-[11px] text-muted-foreground'>
                    {formatSize(row.size_bytes)} · {row.detected_mime}
                    {row.is_empty && ' · empty'}
                    {row.is_executable && ' · EXECUTABLE'}
                  </div>
                  {row.text_preview !== null && row.text_preview.length > 0 && (
                    <pre className='mt-1 max-h-32 overflow-y-auto rounded bg-secondary/40 p-2 font-mono text-[11px] leading-tight'>
                      {row.text_preview}
                    </pre>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}

      <div className='flex flex-wrap items-center justify-between gap-2'>
        <span className='text-xs text-muted-foreground'>
          {selected.length} of {pickedFiles.length} selected · {formatSize(totalBytes)}
          {exeCount > 0 && (
            <span className='ml-2 text-destructive'>· {exeCount} executable</span>
          )}
        </span>
        <div className='flex gap-2'>
          <Button variant='outline' onClick={onCancel}>
            Cancel
          </Button>
          <Button
            disabled={selected.length === 0}
            onClick={() => onConfirm(selected.map((s) => s.file))}
          >
            {exeCount > 0 ? `Upload anyway (${selected.length})` : `Upload ${selected.length}`}
          </Button>
        </div>
      </div>
    </Modal>
  );
}
