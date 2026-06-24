// Global Capture button (ADR-0016 Phase R). A floating "+" reachable on every
// screen (desktop + mobile) -> jot a note (typed or dictated) into a project's
// backlog or its AI memory, without leaving what you're doing.

import { useCallback, useEffect, useState } from 'react';
import { BrainCircuit, Inbox, Loader2, Mic, MicOff, Plus, X } from 'lucide-react';

import { postCapture, type CaptureDestination } from '@shared/capture-client';
import { isMobileRoute } from '@shared/browser-runtime';
import { listProjects } from '@shared/projects-client';
import type { Project } from '@shared/generated-types';
import { useSpeechDictation } from '@shared/use-speech';
import { cn } from '@shared/utils';
import { Button } from './ui/button';
import { Modal } from './ui/modal';

export function CaptureButton(): JSX.Element {
  // On the mobile route the bottom nav is shown at every width, so the FAB +
  // toast must float clear of it (the nav is ~94px + the home-indicator inset).
  const mobile = isMobileRoute();
  const [open, setOpen] = useState(false);
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState('');
  const [destination, setDestination] = useState<CaptureDestination>('backlog');
  const [content, setContent] = useState('');
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const dictation = useSpeechDictation(
    useCallback((t: string) => setContent((c) => (c ? `${c} ${t}` : t)), [])
  );

  useEffect(() => {
    if (!open) return;
    listProjects()
      .then((list) => {
        setProjects(list);
        setProjectId((id) => id || list[0]?.id || '');
      })
      .catch((e) => setError((e as Error).message));
  }, [open]);

  function close(): void {
    setOpen(false);
    setError(null);
    if (dictation.listening) dictation.stop();
  }

  async function submit(): Promise<void> {
    const text = content.trim();
    if (!text || !projectId) return;
    setBusy(true);
    setError(null);
    try {
      const res = await postCapture({ content: text, destination, project_id: projectId });
      setContent('');
      close();
      setToast(res.message);
      window.setTimeout(() => setToast(null), 3500);
    } catch (e) {
      setError((e as Error).message || 'Could not capture that.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        aria-label='Capture a note'
        title='Capture a note'
        className={cn(
          'fixed right-4 z-40 flex h-12 w-12 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-lg transition hover:opacity-90 md:right-6',
          mobile ? 'bottom-[calc(7rem+env(safe-area-inset-bottom))]' : 'bottom-6'
        )}
      >
        <Plus className='h-6 w-6' />
      </button>

      {toast && (
        <div
          className={cn(
            'fixed right-4 z-50 max-w-xs rounded-md border border-border bg-card px-3 py-2 text-sm shadow-lg md:right-6',
            mobile ? 'bottom-[calc(11rem+env(safe-area-inset-bottom))]' : 'bottom-20'
          )}
        >
          {toast}
        </div>
      )}

      <Modal open={open} onClose={close} labelledBy='capture-title' className='max-w-md'>
        <div className='flex items-center justify-between'>
          <h2 id='capture-title' className='text-base font-semibold'>Capture a note</h2>
          <button onClick={close} aria-label='Close' className='text-muted-foreground hover:text-foreground'>
            <X className='h-5 w-5' />
          </button>
        </div>

        <div className='inline-flex self-start rounded-md border border-border p-0.5 text-xs'>
          {([
            { id: 'backlog', label: 'Backlog', icon: Inbox },
            { id: 'ai_context', label: 'AI memory', icon: BrainCircuit },
          ] as const).map((d) => (
            <button
              key={d.id}
              onClick={() => setDestination(d.id)}
              className={cn(
                'inline-flex items-center gap-1 rounded px-3 py-1 font-medium transition-colors',
                destination === d.id ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground'
              )}
            >
              <d.icon className='h-3.5 w-3.5' /> {d.label}
            </button>
          ))}
        </div>

        <label className='flex flex-col gap-1 text-xs text-muted-foreground'>
          Project
          <select
            value={projectId}
            onChange={(e) => setProjectId(e.target.value)}
            className='h-9 rounded-md border border-input bg-transparent px-2 text-sm text-foreground'
          >
            {projects.length === 0 && <option value=''>no projects yet</option>}
            {projects.map((p) => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>
        </label>

        <div className='relative'>
          <textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            placeholder={dictation.listening ? (dictation.interim || 'Listening…') : 'Type or dictate a note…'}
            aria-label='Note'
            rows={4}
            className='w-full rounded-md border border-input bg-transparent px-3 py-2 pr-11 text-sm outline-none focus:border-primary'
          />
          {dictation.supported && (
            <button
              type='button'
              onClick={() => dictation.toggle()}
              aria-label={dictation.listening ? 'Stop dictation' : 'Dictate'}
              className={cn(
                'absolute right-2 top-2 flex h-7 w-7 items-center justify-center rounded-md border',
                dictation.listening ? 'border-primary bg-primary text-primary-foreground' : 'border-border text-muted-foreground'
              )}
            >
              {dictation.listening ? <MicOff className='h-4 w-4' /> : <Mic className='h-4 w-4' />}
            </button>
          )}
        </div>

        {dictation.error && <p role='alert' className='text-xs text-destructive'>{dictation.error}</p>}
        {error && <p role='alert' className='text-xs text-destructive'>{error}</p>}

        <div className='flex justify-end gap-2'>
          <Button variant='ghost' size='sm' onClick={close} disabled={busy}>Cancel</Button>
          <Button size='sm' onClick={() => void submit()} disabled={busy || !content.trim() || !projectId}>
            {busy ? <Loader2 className='h-4 w-4 animate-spin' /> : <Plus className='h-4 w-4' />} Capture
          </Button>
        </div>
      </Modal>
    </>
  );
}
