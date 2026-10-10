import { useEffect, useState } from 'react';
import { AlertTriangle, Cloud, DollarSign, RefreshCw, ShieldCheck } from 'lucide-react';

import { apiFetch } from '../lib/api-client';

interface RailwayServiceCost {
  name: string;
  project: string;
  purpose: string;
  cpu_vcpu: number | null;
  ram_gb: number | null;
  disk_used_gb: number | null;
  volume_gb_allocated: number | null;
  network_tx_gb_observed_window: number | null;
  baseline_usd_month: number | null;
}
interface RailwayCostStatus {
  workspace: string;
  observed_at: string | null;
  observation_age_seconds: number | null;
  connected_for_auto_refresh: boolean;
  refresh_error: string | null;
  state: 'healthy' | 'warning' | 'critical' | 'stale' | 'incomplete' | 'not_configured';
  warning_usd: number;
  critical_usd: number;
  estimated_monthly_baseline_usd: number | null;
  estimate_covers: string;
  not_in_estimate: string[];
  billing_total_usd: number | null;
  billing_total_verified: boolean;
  source: string;
  services: RailwayServiceCost[];
  inactive_projects: string[];
  prices_url: string;
}

const usd = (n: number | null) => n === null ? 'Unavailable' : '$' + n.toFixed(2);
const nfmt = (n: number | null, digits = 2) => n === null ? '—' : n.toFixed(digits);

export function RailwayCostPanel(): JSX.Element {
  const [snapshot, setSnapshot] = useState<RailwayCostStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [warning, setWarning] = useState('3');
  const [critical, setCritical] = useState('5');
  const [editing, setEditing] = useState(false);

  async function load(force = false): Promise<void> {
    if (force) setBusy(true);
    try {
      const data = await apiFetch<RailwayCostStatus>('/system/railway-costs' + (force ? '?refresh=true' : ''), {
        method: 'GET', timeoutMs: 18000,
      });
      setSnapshot(data);
      if (!editing) {
        setWarning(String(data.warning_usd));
        setCritical(String(data.critical_usd));
      }
      setError(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    void load();
    const refreshTimer = window.setInterval(() => void load(), 60_000);
    return () => window.clearInterval(refreshTimer);
  }, []);

  async function saveBudget(): Promise<void> {
    const warn = Number(warning);
    const stop = Number(critical);
    if (!Number.isFinite(warn) || !Number.isFinite(stop) || warn <= 0 || stop <= warn) {
      setError('Set a warning amount greater than $0, and a higher critical amount.');
      return;
    }
    setBusy(true);
    try {
      const result = await apiFetch<RailwayCostStatus>('/system/railway-costs/budget', {
        method: 'POST',
        body: { warning_usd: warn, critical_usd: stop },
      });
      setSnapshot(result);
      setEditing(false);
      setError(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(false);
    }
  }

  const state = snapshot?.state ?? 'not_configured';
  const stateLabel: Record<RailwayCostStatus['state'], string> = {
    healthy: 'Below budget', warning: 'Budget warning', critical: 'Budget exceeded',
    stale: 'Old observation', incomplete: 'Incomplete metrics', not_configured: 'No observations',
  };
  const stateColor = state === 'critical' ? 'text-status-error' :
    state === 'warning' || state === 'stale' ? 'text-amber-500' : 'text-muted-foreground';

  return (
    <section aria-labelledby='railway-cost-heading' className='space-y-4 rounded-2xl border border-border bg-card p-4 sm:p-5'>
      <div className='flex flex-wrap items-start justify-between gap-3'>
        <div className='flex items-center gap-3'>
          <div className='rounded-xl bg-primary/10 p-2 text-primary'><Cloud className='h-5 w-5' /></div>
          <div>
            <h2 id='railway-cost-heading' className='font-semibold text-base'>Railway cost monitor</h2>
            <p className='text-xs text-muted-foreground'>Cloud usage • Synapse infrastructure • {snapshot?.workspace ?? 'Workspace'}</p>
          </div>
        </div>
        <button onClick={() => void load(true)} disabled={busy} type='button'
          className='inline-flex items-center gap-2 rounded-xl border border-border bg-secondary px-3 py-2 text-xs font-medium hover:bg-accent disabled:opacity-50'>
          <RefreshCw className={'h-3.5 w-3.5 ' + (busy ? 'animate-spin' : '')} />
          Refresh
        </button>
      </div>
      {error && <div role='alert' className='flex items-start gap-2 rounded-lg bg-status-error/10 p-3 text-sm text-status-error'>
        <AlertTriangle className='mt-0.5 h-4 w-4 shrink-0' />{error}</div>}
      <div className='grid gap-3 sm:grid-cols-3'>
        <div className='rounded-xl bg-secondary/60 p-4'>
          <div className='mb-2 flex items-center gap-2 text-xs text-muted-foreground'><DollarSign className='h-4 w-4'/> Estimated monthly baseline</div>
          <div className='text-2xl font-semibold tracking-tight'>{usd(snapshot?.estimated_monthly_baseline_usd ?? null)}</div>
          <p className='mt-1 text-xs text-muted-foreground'>Not your actual Railway invoice</p>
        </div>
        <div className='rounded-xl bg-secondary/60 p-4'>
          <p className='mb-2 text-xs text-muted-foreground'>Cost guard</p>
          <div className={'text-lg font-semibold ' + stateColor}>{stateLabel[state]}</div>
          <p className='mt-1 text-xs text-muted-foreground'>Warn {usd(snapshot?.warning_usd ?? 3)} · Critical {usd(snapshot?.critical_usd ?? 5)}</p>
        </div>
        <div className='rounded-xl bg-secondary/60 p-4'>
          <p className='mb-2 text-xs text-muted-foreground'>Telemetry</p>
          <div className='text-lg font-semibold'>{snapshot?.connected_for_auto_refresh ? 'API connected' : 'Saved snapshot'}</div>
          <p className='mt-1 text-xs text-muted-foreground'>
            {snapshot?.observed_at ? 'Observed ' + new Date(snapshot.observed_at).toLocaleString() : 'Not measured'}
          </p>
        </div>
      </div>
      {snapshot?.refresh_error && <p role='alert' className='text-xs text-amber-500'>{snapshot.refresh_error}</p>}
      {!snapshot?.connected_for_auto_refresh && (
        <p className='text-xs text-muted-foreground'>
          Automatic local refresh is not connected. Set RAILWAY_API_TOKEN in the Synapse daemon environment for direct Railway metrics; the saved observation is not a live billing feed.
        </p>
      )}
      {(snapshot?.services ?? []).map((svc) => (
        <div key={svc.project + '/' + svc.name} className='rounded-xl border border-border p-3'>
          <div className='mb-3 flex flex-wrap items-center justify-between gap-2'>
            <div>
              <div className='font-medium text-sm'>{svc.name} <span className='font-normal text-muted-foreground'>· {svc.project}</span></div>
              <p className='text-xs text-muted-foreground'>{svc.purpose}</p>
            </div>
            <span className='text-sm font-semibold'>{usd(svc.baseline_usd_month)}/mo</span>
          </div>
          <div className='grid grid-cols-2 gap-2 text-xs text-muted-foreground sm:grid-cols-4'>
            <div>CPU <strong className='block text-foreground'>{nfmt(svc.cpu_vcpu, 4)} vCPU</strong></div>
            <div>RAM <strong className='block text-foreground'>{svc.ram_gb === null ? '—' : nfmt(svc.ram_gb * 1000, 1) + ' MB'}</strong></div>
            <div>Volume <strong className='block text-foreground'>{nfmt(svc.disk_used_gb, 3)} GB used / {nfmt(svc.volume_gb_allocated, 2)} GB capacity</strong></div>
            <div>TX traffic <strong className='block text-foreground'>{nfmt(svc.network_tx_gb_observed_window, 6)} GB sampled</strong></div>
          </div>
        </div>
      ))}
      {snapshot?.inactive_projects.length ? <p className='text-xs text-muted-foreground'>
        Other Railway projects without observed services: {snapshot.inactive_projects.join(', ')}.
      </p> : null}
      <div className='flex flex-wrap items-center justify-between gap-3'>
        <button type='button' className='text-xs font-semibold text-primary hover:underline' onClick={() => setEditing(!editing)}>
          {editing ? 'Cancel budget edit' : 'Adjust cost thresholds'}
        </button>
        <a className='text-xs text-primary hover:underline' href='https://railway.com/dashboard' target='_blank' rel='noreferrer'>
          Open Railway billing ↗
        </a>
      </div>
      {editing && <div className='flex flex-wrap items-end gap-3 rounded-xl border border-border p-3'>
        <label className='text-xs'>Warning USD<input aria-label='Warning amount in USD' value={warning} onChange={e=>setWarning(e.target.value)}
          type='number' min='0.01' step='0.5' className='mt-1 block w-28 rounded-lg border border-border bg-background p-2'/></label>
        <label className='text-xs'>Critical USD<input aria-label='Critical amount in USD' value={critical} onChange={e=>setCritical(e.target.value)}
          type='number' min='0.01' step='0.5' className='mt-1 block w-28 rounded-lg border border-border bg-background p-2'/></label>
        <button type='button' onClick={() => void saveBudget()} disabled={busy} className='rounded-lg bg-primary px-3 py-2 text-xs font-medium text-primary-foreground disabled:opacity-50'>
          Save thresholds
        </button>
      </div>}
      <div className='flex items-start gap-2 border-t border-border pt-3 text-xs text-muted-foreground'>
        <ShieldCheck className='h-4 w-4 shrink-0'/>
        Estimates assume today’s observed CPU/RAM continues for 30 days plus observed used disk. Network egress, plan minimums, taxes and Railway Agent charges are excluded. Alerts do not shut anything down. Use Railway's own usage limits for enforceable spending caps.
      </div>
    </section>
  );
}
