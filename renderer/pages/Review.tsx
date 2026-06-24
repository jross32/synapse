// Needs-Review / approval inbox (ADR-0016 Phase R). Clear the AI workforce's
// handoffs + blocked items from one queue -- built mobile-first.

import { useCallback, useEffect, useState } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  Inbox,
  Loader2,
  RotateCcw,
  XCircle,
} from 'lucide-react';

import {
  approveReview,
  getReviewInbox,
  rejectReview,
  reviseReview,
  type ReviewInbox,
  type ReviewItem,
} from '@shared/review-client';
import { useDaemon } from '@shared/daemon-context';
import { cn } from '@shared/utils';
import { Button } from '../components/ui/button';
import { Card } from '../components/ui/card';
import { PageHeader } from '../components/PageHeader';

export function ReviewPage(): JSX.Element {
  const { subscribeRaw } = useDaemon();
  const [inbox, setInbox] = useState<ReviewInbox | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setInbox(await getReviewInbox());
      setError(null);
    } catch (e) {
      setError((e as Error).message || 'Could not load the review inbox.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // Clear live when anything resolves an item (here or on another device) or a
  // squad hands more work back.
  useEffect(
    () =>
      subscribeRaw((event) => {
        if (event.name === 'v1.review.resolved' || event.name.startsWith('v1.agent_work_item')) {
          void refresh();
        }
      }),
    [subscribeRaw, refresh]
  );

  const count = inbox?.count ?? 0;
  const header = (
    <PageHeader
      title='Review'
      subtitle='Work your AI workforce handed back — approve it, send it back with feedback, or block it.'
    />
  );

  return (
    <div className='flex h-full flex-col gap-4'>
      {header}
      {error && <p role='alert' className='text-xs text-destructive'>{error}</p>}

      {loading ? (
        <Card className='flex items-center gap-2 p-6 text-sm text-muted-foreground'>
          <Loader2 className='h-4 w-4 animate-spin' /> Loading the inbox…
        </Card>
      ) : count === 0 ? (
        <Card className='mx-auto flex max-w-md flex-col items-center gap-2 p-10 text-center'>
          <Inbox className='h-8 w-8 text-primary' />
          <h2 className='text-lg font-semibold'>All caught up</h2>
          <p className='text-sm text-muted-foreground'>
            When an AI squad finishes a chunk of work or gets stuck, it shows up here to
            <span className='text-foreground'> approve</span>,
            <span className='text-foreground'> revise</span>, or
            <span className='text-foreground'> reject</span> — from your desk or your phone.
          </p>
          <p className='text-xs text-muted-foreground'>Start a squad from the Sessions tab to put your AI workforce to work.</p>
        </Card>
      ) : (
        <div className='flex flex-col gap-3'>
          {inbox!.items.map((item) => (
            <ReviewCard key={item.id} item={item} onResolved={refresh} />
          ))}
        </div>
      )}
    </div>
  );
}

function ReviewCard({ item, onResolved }: { item: ReviewItem; onResolved: () => void }): JSX.Element {
  const [busy, setBusy] = useState(false);
  const [mode, setMode] = useState<null | 'revise' | 'reject'>(null);
  const [note, setNote] = useState('');
  const [err, setErr] = useState<string | null>(null);
  const blocked = item.kind === 'blocked';

  async function run(fn: () => Promise<unknown>): Promise<void> {
    setBusy(true);
    setErr(null);
    try {
      await fn();
      onResolved();
    } catch (e) {
      setErr((e as Error).message || 'Action failed.');
      setBusy(false);
    }
  }

  const body = blocked ? item.blockers_md : item.summary_md;

  return (
    <Card className='flex flex-col gap-2 p-4'>
      <div className='flex flex-wrap items-center gap-2'>
        <span
          className={cn(
            'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium',
            blocked ? 'bg-amber-500/15 text-amber-200' : 'bg-emerald-500/15 text-emerald-300'
          )}
        >
          {blocked ? <AlertTriangle className='h-3 w-3' /> : <CheckCircle2 className='h-3 w-3' />}
          {blocked ? 'AI is stuck' : 'Ready for review'}
        </span>
        <h3 className='font-semibold'>{item.title}</h3>
        <span className='ml-auto text-xs text-muted-foreground'>
          {item.project_name ?? item.project_id} · {item.squad_name}
        </span>
      </div>

      {body && <p className='whitespace-pre-wrap text-sm text-muted-foreground'>{body}</p>}

      {item.files_touched.length > 0 && (
        <div className='flex flex-wrap gap-1'>
          {item.files_touched.map((f) => (
            <span key={f} className='rounded bg-secondary/50 px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground'>{f}</span>
          ))}
        </div>
      )}
      {item.suggested_next_role && (
        <p className='text-xs text-muted-foreground'>Suggested next: <span className='text-foreground'>{item.suggested_next_role}</span></p>
      )}

      {mode ? (
        <div className='flex flex-col gap-2'>
          <textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder={mode === 'revise' ? 'What should they change?' : 'Why are you blocking this?'}
            aria-label={mode === 'revise' ? 'Revision feedback' : 'Reject reason'}
            rows={2}
            className='rounded-md border border-input bg-transparent px-2 py-1.5 text-sm outline-none focus:border-primary'
          />
          <div className='flex gap-2'>
            <Button
              size='sm'
              variant={mode === 'reject' ? 'destructive' : 'default'}
              disabled={busy}
              onClick={() => void run(() => (mode === 'revise' ? reviseReview(item.id, note) : rejectReview(item.id, note)))}
            >
              {busy ? <Loader2 className='h-4 w-4 animate-spin' /> : null}
              {mode === 'revise' ? 'Send back' : 'Block it'}
            </Button>
            <Button size='sm' variant='ghost' disabled={busy} onClick={() => { setMode(null); setNote(''); }}>Cancel</Button>
          </div>
        </div>
      ) : (
        <div className='flex flex-wrap gap-2'>
          <Button size='sm' disabled={busy} onClick={() => void run(() => approveReview(item.id))}>
            <CheckCircle2 className='h-4 w-4' /> Approve
          </Button>
          <Button size='sm' variant='outline' disabled={busy} onClick={() => setMode('revise')}>
            <RotateCcw className='h-4 w-4' /> Revise
          </Button>
          <Button size='sm' variant='ghost' className='text-destructive' disabled={busy} onClick={() => setMode('reject')}>
            <XCircle className='h-4 w-4' /> Reject
          </Button>
        </div>
      )}
      {err && <p role='alert' className='text-xs text-destructive'>{err}</p>}
    </Card>
  );
}
