// In-page file preview (v0.1.35 · AUDIT punch-list).
//
// Until now the "Download" button was the only way to read an uploaded
// .md / .txt / .log -- which meant a download dialog, then opening the
// file in another app, then alt-tabbing back. For text payloads under
// a few hundred KB an inline preview is dramatically faster.
//
// Renders raw text inside a <pre>; explicitly does NOT parse markdown
// (no new deps, no XSS surface). Binary / unknown files surface a
// "Use Download instead" hint with the size + sha256 so the user
// knows what's there.

import { useEffect, useState } from 'react';
import { ArrowDownToLine, Loader2 } from 'lucide-react';

import type { ProjectFile } from '@shared/generated-types';
import { downloadFile, downloadFileBlob } from '@shared/files-client';
import { Button } from './ui/button';
import { Modal } from './ui/modal';

export interface FilePreviewDialogProps {
  open: boolean;
  file: ProjectFile | null;
  projectId: string | null;
  onClose: () => void;
}

//: Extensions we will render inline. Conservative; anything that's
//: definitely text. Binary types (images, archives, executables) get
//: the "Use Download" surface instead so we never blast 2 MB of
//: ASCII-rendered binary into the DOM.
const TEXT_EXTENSIONS = new Set([
  'md', 'markdown', 'txt', 'log', 'json', 'jsonl', 'yaml', 'yml',
  'csv', 'tsv', 'env', 'ini', 'toml', 'xml', 'html', 'css', 'js',
  'jsx', 'ts', 'tsx', 'py', 'rs', 'go', 'rb', 'sh', 'ps1', 'sql',
]);

//: Stop loading after this much -- bigger than this and we suggest
//: download. xterm can render larger but a <pre> in a modal is the
//: wrong tool for the job past ~1 MB.
const MAX_PREVIEW_BYTES = 1024 * 1024;

export function isPreviewable(file: ProjectFile): boolean {
  const ext = file.original_name.split('.').pop()?.toLowerCase();
  if (!ext) return false;
  if (!TEXT_EXTENSIONS.has(ext)) return false;
  if (file.size_bytes > MAX_PREVIEW_BYTES) return false;
  // Transcripts are always text by construction.
  if (file.source === 'transcript') return true;
  return true;
}

export function FilePreviewDialog({
  open,
  file,
  projectId,
  onClose,
}: FilePreviewDialogProps): JSX.Element | null {
  const [text, setText] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open || !file) {
      setText(null);
      setError(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    setText(null);
    void downloadFileBlob(projectId, file.id)
      .then((blob) => blob.text())
      .then((body) => {
        if (cancelled) return;
        setText(body);
      })
      .catch((err: Error) => {
        if (cancelled) return;
        setError(err.message || 'Failed to load file');
      })
      .finally(() => {
        if (cancelled) return;
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, file, projectId]);

  if (!open || !file) return null;
  return (
    <Modal open onClose={onClose} labelledBy='file-preview-title' className='max-w-3xl'>
      <div className='flex items-start justify-between gap-3'>
        <div className='min-w-0'>
          <h2 id='file-preview-title' className='truncate text-base font-semibold'>
            {file.original_name}
          </h2>
          <p className='mt-0.5 font-mono text-xs text-muted-foreground'>
            {file.mime} · {file.size_bytes.toLocaleString()} B · {file.source}
          </p>
        </div>
        <Button
          variant='outline'
          size='sm'
          onClick={() => void downloadFile(projectId, file.id, file.original_name)}
          aria-label={`Download ${file.original_name}`}
        >
          <ArrowDownToLine className='h-3.5 w-3.5' aria-hidden='true' />
          Download
        </Button>
      </div>
      {loading && (
        <div className='flex items-center gap-2 py-6 text-sm text-muted-foreground'>
          <Loader2 className='h-4 w-4 animate-spin' /> Loading file…
        </div>
      )}
      {error && (
        <p role='alert' className='text-sm text-destructive'>
          {error}
        </p>
      )}
      {!loading && !error && text !== null && (
        <pre
          className='max-h-[60vh] overflow-auto whitespace-pre-wrap break-words rounded-md border border-border bg-secondary/40 p-3 font-mono text-xs leading-relaxed'
          aria-label='File contents'
        >
          {text}
        </pre>
      )}
    </Modal>
  );
}
