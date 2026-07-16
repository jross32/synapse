// Needs-Review / approval inbox (ADR-0016 Phase R). Clear the AI workforce's
// handoffs + blocked items from one queue -- built mobile-first.

import { useCallback, useEffect, useState } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  ChevronRight,
  Inbox,
  Lightbulb,
  Loader2,
  RotateCcw,
  XCircle,
} from 'lucide-react';

import {
  approveProposal,
  approveReview,
  getReviewInbox,
  promoteProposal,
  rejectProposal,
  rejectReview,
  reviseReview,
  type Proposal,
  type ReviewInbox,
  type ReviewItem,
} from '@shared/review-client';
import { useDaemon } from '@shared/daemon-context';
import { cn } from '@shared/utils';
import { Button } from '../components/ui/button';
import { Card } from '../components/ui/card';
import { Modal } from '../components/ui/modal';
import { PageHeader } from '../components/PageHeader';

// Friendly category names for the raw metadata.kind an AI files a proposal under.
const CATEGORY_LABELS: Record<string, string> = {
  bug: 'Bugs',
  ux: 'Design & UX',
  ui: 'Design & UX',
  perf: 'Performance',
  performance: 'Performance',
  feature: 'New features',
  reliability: 'Reliability',
  devex: 'Developer experience',
  dedup: 'Cleanup',
  'doc-drift': 'Docs',
  idea: 'Ideas',
};

function proposalKind(proposal: Proposal): string {
  return typeof proposal.metadata?.kind === 'string' ? proposal.metadata.kind : 'idea';
}

function categoryOf(proposal: Proposal): string {
  const kind = proposalKind(proposal);
  return CATEGORY_LABELS[kind] ?? kind.charAt(0).toUpperCase() + kind.slice(1);
}

export interface ReviewPageProps {
  headerless?: boolean;
}

export function ReviewPage({ headerless = false }: ReviewPageProps): JSX.Element {
  const { subscribeRaw } = useDaemon();
  const [inbox, setInbox] = useState<ReviewInbox | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [openProposal, setOpenProposal] = useState<Proposal | null>(null);

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
        if (
          event.name === 'v1.review.resolved' ||
          event.name === 'v1.review.proposal_filed' ||
          event.name.startsWith('v1.agent_work_item')
        ) {
          void refresh();
        }
      }),
    [subscribeRaw, refresh]
  );

  const count = inbox?.count ?? 0;
  const proposals = inbox?.proposals ?? [];
  const isEmpty = count === 0 && proposals.length === 0;

  // Group ideas by friendly category so a growing inbox stays organized.
  const proposalGroups = new Map<string, Proposal[]>();
  for (const proposal of proposals) {
    const category = categoryOf(proposal);
    const list = proposalGroups.get(category) ?? [];
    list.push(proposal);
    proposalGroups.set(category, list);
  }
  const sortedGroups = [...proposalGroups.entries()].sort((a, b) => a[0].localeCompare(b[0]));
  const header = headerless ? null : (
    <PageHeader
      title='Review'
      subtitle='Work your AI workforce handed back plus improvement ideas it filed — approve, send back, block, or promote.'
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
      ) : isEmpty ? (
        <Card className='mx-auto flex max-w-md flex-col items-center gap-2 p-10 text-center'>
          <Inbox className='h-8 w-8 text-primary' />
          <h2 className='text-lg font-semibold'>All caught up</h2>
          <p className='text-sm text-muted-foreground'>
            When an AI squad finishes a chunk of work, gets stuck, or files an improvement idea, it
            shows up here to <span className='text-foreground'>approve</span>,
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
          {proposals.length > 0 && (
            <>
              <div className='mt-2 flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-muted-foreground'>
                <Lightbulb className='h-3.5 w-3.5' /> Improvement ideas from your AI workforce
              </div>
              {sortedGroups.map(([category, list]) => (
                <div key={category} className='flex flex-col gap-2'>
                  <div className='flex items-center gap-2 text-sm font-semibold'>
                    {category}
                    <span className='rounded-full bg-secondary/60 px-1.5 py-0.5 text-[10px] font-normal text-muted-foreground'>
                      {list.length}
                    </span>
                  </div>
                  {list.map((proposal) => (
                    <ProposalSummaryCard
                      key={proposal.id}
                      proposal={proposal}
                      onOpen={() => setOpenProposal(proposal)}
                    />
                  ))}
                </div>
              ))}
            </>
          )}
        </div>
      )}

      {openProposal && (
        <ProposalDetailModal
          proposal={openProposal}
          onClose={() => setOpenProposal(null)}
          onResolved={() => {
            setOpenProposal(null);
            void refresh();
          }}
        />
      )}
    </div>
  );
}

function plainSnippet(markdown: string): string {
  return markdown
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/[#*`_>[\]]/g, '')
    .replace(/\s+/g, ' ')
    .trim();
}

// Compact, clickable summary row -- opens the full detail popup.
function proposalAddressedBy(proposal: Proposal): string {
  return typeof proposal.metadata?.addressed_by === 'string' ? proposal.metadata.addressed_by : '';
}

function ProposalSummaryCard({ proposal, onOpen }: { proposal: Proposal; onOpen: () => void }): JSX.Element {
  const snippet = plainSnippet(proposal.rationale_md).slice(0, 130);
  const addressed = proposalAddressedBy(proposal);
  return (
    <Card className='p-0'>
      <button
        type='button'
        onClick={onOpen}
        className='flex w-full items-center gap-3 rounded-lg p-4 text-left transition-colors hover:bg-secondary/30 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary'
      >
        <Lightbulb className='h-4 w-4 shrink-0 text-primary' />
        <div className='min-w-0 flex-1'>
          <div className='flex items-center gap-2'>
            <h3 className='truncate font-semibold'>{proposal.title}</h3>
            {addressed && (
              <span className='shrink-0 rounded bg-status-launching/15 px-1.5 py-0.5 text-[10px] text-status-launching'>
                possibly addressed
              </span>
            )}
            {proposal.est_effort && (
              <span className='shrink-0 rounded bg-secondary/60 px-1.5 py-0.5 text-[10px] text-muted-foreground'>
                {proposal.est_effort}
              </span>
            )}
          </div>
          {snippet && <p className='truncate text-xs text-muted-foreground'>{snippet}</p>}
        </div>
        <ChevronRight className='h-4 w-4 shrink-0 text-muted-foreground' aria-hidden='true' />
        <span className='sr-only'>View idea details</span>
      </button>
    </Card>
  );
}

// Full detail popup: plain-language impact + full reasoning + approve/reject/promote.
function ProposalDetailModal({
  proposal,
  onClose,
  onResolved,
}: {
  proposal: Proposal;
  onClose: () => void;
  onResolved: () => void;
}): JSX.Element {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const kind = proposalKind(proposal);
  const impact = typeof proposal.metadata?.impact === 'string' ? proposal.metadata.impact : '';
  const addressed = proposalAddressedBy(proposal);

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

  return (
    <Modal open onClose={onClose} labelledBy='proposal-detail-title' className='max-w-2xl'>
      <div className='flex flex-col gap-3'>
        <div className='flex flex-wrap items-center gap-2'>
          <span className='inline-flex items-center gap-1 rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary'>
            <Lightbulb className='h-3 w-3' /> {CATEGORY_LABELS[kind] ?? kind}
          </span>
          {proposal.est_effort && (
            <span className='rounded-full bg-secondary/60 px-2 py-0.5 text-xs text-muted-foreground'>
              Effort: {proposal.est_effort}
            </span>
          )}
        </div>

        <h2 id='proposal-detail-title' className='text-lg font-semibold'>{proposal.title}</h2>

        {impact && (
          <div className='rounded-md border border-border bg-secondary/20 p-3'>
            <p className='text-xs font-medium uppercase tracking-wide text-muted-foreground'>What this means for you</p>
            <p className='mt-1 text-sm'>{impact}</p>
          </div>
        )}

        {addressed && (
          <div className='rounded-md border border-status-launching/30 bg-status-launching/10 p-3'>
            <p className='text-xs font-medium uppercase tracking-wide text-status-launching'>Possibly already done</p>
            <p className='mt-1 text-sm text-muted-foreground'>
              A recent commit references this idea: <span className='font-mono text-xs'>{addressed}</span>. If it's
              handled, <span className='text-foreground'>Approve</span> to clear it from the inbox.
            </p>
          </div>
        )}

        <div>
          <p className='text-xs font-medium uppercase tracking-wide text-muted-foreground'>Why + how</p>
          <p className='mt-1 whitespace-pre-wrap text-sm text-muted-foreground'>{proposal.rationale_md}</p>
        </div>

        <p className='text-xs text-muted-foreground'>
          Filed by <span className='text-foreground'>{proposal.source_runtime || 'an AI'}</span>
          {proposal.project_id ? <> · {proposal.project_id}</> : null}
        </p>

        {err && <p role='alert' className='text-xs text-destructive'>{err}</p>}

        <div className='flex flex-wrap items-center gap-2'>
          {proposal.project_id && (
            <Button size='sm' disabled={busy} onClick={() => void run(() => promoteProposal(proposal.id))}>
              <CheckCircle2 className='h-4 w-4' /> Approve + add to backlog
            </Button>
          )}
          <Button
            size='sm'
            variant={proposal.project_id ? 'outline' : 'default'}
            disabled={busy}
            onClick={() => void run(() => approveProposal(proposal.id))}
          >
            <CheckCircle2 className='h-4 w-4' /> Approve
          </Button>
          <Button
            size='sm'
            variant='ghost'
            className='text-destructive'
            disabled={busy}
            onClick={() => void run(() => rejectProposal(proposal.id))}
          >
            <XCircle className='h-4 w-4' /> Reject
          </Button>
          <Button size='sm' variant='ghost' className='ml-auto' disabled={busy} onClick={onClose}>
            Close
          </Button>
        </div>
      </div>
    </Modal>
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
            blocked ? 'bg-status-launching/15 text-status-launching' : 'bg-status-launched/15 text-status-launched'
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
