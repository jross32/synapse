import { useEffect, useState } from 'react';
import { Activity, CheckCircle2, ClipboardCheck, RefreshCw, Target } from 'lucide-react';
import {
  getMayaGrowthReview,
  recordMayaGrowthReview,
  getMayaExperimentPlan,
  recordMayaExperimentPlan,
  type MayaExperimentPlan,
  type MayaGrowthReview,
} from '../lib/staff-client';

const readinessLabel: Record<string, string> = {
  ready_for_internal_funnel_test: 'Ready to verify',
  unverified: 'Verification needed',
  runtime_blocked: 'Runtime blocked',
};

/** This is a registry evidence preview, not a simulated autonomous staff run. */
export function MayaGrowthReviewPanel({ onRecorded }: { onRecorded: () => void }): JSX.Element {
  const [review, setReview] = useState<MayaGrowthReview | null>(null);
  const [plan, setPlan] = useState<MayaExperimentPlan | null>(null);
  const [planBusy, setPlanBusy] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  async function refresh(): Promise<void> {
    try {
      const fresh = await getMayaGrowthReview();
      setReview(fresh);
      const freshPlan = await getMayaExperimentPlan();
      setPlan(freshPlan);
      setError('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Growth review is not available yet.');
    }
  }

  useEffect(() => {
    let mounted = true;
    void getMayaGrowthReview()
      .then((value) => { if (mounted) setReview(value); })
      .catch((err: unknown) => {
        if (mounted) setError(err instanceof Error ? err.message : 'Growth review is not available yet.');
      });
    void getMayaExperimentPlan().then((value) => {
      if (mounted) setPlan(value);
    }).catch((err: unknown) => {
      if (mounted) setError(err instanceof Error ? err.message : 'Experiment plan preview unavailable.');
    });
    return () => { mounted = false; };
  }, []);

  async function savePlan(): Promise<void> {
    if (planBusy) return;
    setPlanBusy(true);
    setError('');
    setMessage('');
    try {
      const receipt = await recordMayaExperimentPlan();
      setPlan(receipt.plan);
      setMessage(receipt.created
        ? 'Measurable draft saved to Maya’s history. No experiment has run.'
        : 'Existing draft reused; no experiment has run.');
      onRecorded();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save the draft experiment.');
    } finally {
      setPlanBusy(false);
    }
  }

  async function saveReview(): Promise<void> {
    if (busy) return;
    setBusy(true);
    setMessage('');
    setError('');
    try {
      const result = await recordMayaGrowthReview();
      setReview(result.brief);
      setMessage(result.created
        ? 'Evidence review recorded in Maya’s activity history.'
        : 'This evidence snapshot was already recorded; no duplicate created.');
      onRecorded();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save the review.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className='rounded-3xl border border-primary/25 bg-[radial-gradient(circle_at_12%_0%,rgba(59,130,246,.12),transparent_50%)] p-5'>
      <div className='flex flex-wrap items-start justify-between gap-3'>
        <div>
          <div className='flex items-center gap-2 text-sm font-semibold text-foreground'>
            <Target className='h-4 w-4 text-primary' />
            Maya's Growth Review
          </div>
          <p className='mt-1 text-xs leading-5 text-muted-foreground'>
            Real project-registry signals. No assumed customers, revenue, or completed experiments.
          </p>
        </div>
        <button
          type='button'
          onClick={() => void refresh()}
          aria-label='Refresh Maya growth evidence'
          className='rounded-xl border border-border p-2 text-muted-foreground hover:text-foreground'
        >
          <RefreshCw className='h-4 w-4' />
        </button>
      </div>

      {review && (
        <div className='mt-4 space-y-3'>
          <div className='flex flex-wrap gap-2 text-[11px] text-muted-foreground'>
            <span className='rounded-full border border-border px-2.5 py-1'>{review.projects_examined} projects reviewed</span>
            <span className='rounded-full border border-border px-2.5 py-1'>{review.commercial_candidates} commercial candidates</span>
            <span className='rounded-full border border-border px-2.5 py-1'>ROI unknown</span>
          </div>
          <div className='rounded-2xl border border-primary/20 bg-background/55 p-4'>
            <p className='text-[10px] font-semibold uppercase tracking-[0.15em] text-primary'>
              First internal verification
            </p>
            <p className='mt-1 text-sm font-semibold text-foreground'>
              {review.candidates.find((item) => item.project_id === review.recommended_project_id)?.name
                ?? 'No eligible project identified'}
            </p>
            <p className='mt-2 text-xs leading-5 text-muted-foreground'>{review.recommendation}</p>
          </div>
          <div className='space-y-2'>
            {review.candidates.slice(0, 4).map((candidate) => (
              <div key={candidate.project_id} className='flex flex-wrap items-center justify-between gap-2 rounded-xl border border-border/65 bg-card/45 px-3 py-2'>
                <div className='min-w-0'>
                  <p className='text-xs font-semibold text-foreground'>{candidate.name}</p>
                  <p className='text-[11px] text-muted-foreground'>
                    Status: {candidate.registered_status} · Health: {candidate.recorded_health ?? 'unknown'}
                  </p>
                </div>
                <span className='text-[10px] text-muted-foreground'>
                  {readinessLabel[candidate.readiness] ?? 'Unverified'}
                </span>
              </div>
            ))}
          </div>
          {plan && plan.status === 'draft_unexecuted' && (
            <div className='space-y-3 rounded-2xl border border-border bg-card/55 p-4'>
              <div className='flex flex-wrap items-center justify-between gap-2'>
                <p className='text-xs font-semibold text-foreground'>Proposed first-value experiment</p>
                <span className='text-[10px] text-muted-foreground'>Draft · Not executed</span>
              </div>
              <p className='text-xs leading-5 text-foreground'>{plan.hypothesis}</p>
              <p className='text-[11px] text-muted-foreground'>
                Gate: {plan.readiness_gate.replace(/_/g, ' ')} ·
                Health evidence: {plan.health_freshness ?? 'unknown'}
              </p>
              <ol className='list-decimal space-y-1 pl-4 text-xs text-muted-foreground'>
                {plan.funnel_steps.map((step) => <li key={step}>{step}</li>)}
              </ol>
              <p className='text-xs text-foreground'>{plan.metric?.name}:</p>
              <p className='text-[11px] text-muted-foreground'>
                Baseline unknown · Attempts unknown · Completions unknown
              </p>
              <p className='text-xs leading-5 text-muted-foreground'>{plan.next_action}</p>
              <p className='text-[11px] text-muted-foreground'>
                Internal testing only. No outside publication, outreach, spending, or customer-data access is authorized.
              </p>
              <button
                type='button'
                onClick={() => void savePlan()}
                disabled={planBusy}
                className='w-full rounded-xl border border-border px-3 py-2.5 text-xs font-semibold text-foreground disabled:opacity-50'
              >
                {planBusy ? 'Saving draft…' : 'Save measurable draft to Maya'}
              </button>
            </div>
          )}
          <p className='text-[11px] leading-5 text-muted-foreground'>
            Source: Synapse project registry and backlog. Status may be stale. Saving is not a worker launch or growth campaign.
          </p>
          <button
            type='button'
            onClick={() => void saveReview()}
            disabled={busy}
            className='flex w-full items-center justify-center gap-2 rounded-xl bg-primary px-3 py-2.5 text-xs font-semibold text-primary-foreground disabled:opacity-50'
          >
            <ClipboardCheck className='h-4 w-4' />
            {busy ? 'Recording evidence…' : 'Record Maya review'}
          </button>
        </div>
      )}
      {!review && !error && (
        <div className='mt-4 flex items-center gap-2 text-xs text-muted-foreground'>
          <Activity className='h-4 w-4' /> Loading portfolio evidence…
        </div>
      )}
      {message && (
        <p className='mt-3 flex items-center gap-2 text-xs text-emerald-300'>
          <CheckCircle2 className='h-4 w-4' /> {message}
        </p>
      )}
      {error && (
        <p className='mt-3 rounded-xl border border-amber-400/20 bg-amber-500/10 p-3 text-xs text-amber-200'>
          Review service unavailable: {error}
        </p>
      )}
    </section>
  );
}
