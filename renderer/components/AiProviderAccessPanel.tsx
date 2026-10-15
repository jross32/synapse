import { useEffect, useState } from 'react';
import { apiFetch } from '@shared/api-client';
import { Card } from './ui/card';
import { Button } from './ui/button';

type Access = {
  enabled: boolean;
  access: 'unknown' | 'free' | 'subscription' | 'api' | 'local';
  authenticated: boolean;
  supports_automation: boolean;
  included_usage_available: boolean;
  extra_cost_per_request_usd: number | null;
};
type Provider = { id: string; label: string; method: string; installed: boolean;
  capabilities: string[]; access: Access; eligible_without_extra_spend: boolean };
type Response = { configured: boolean; allow_additional_spend: boolean; providers: Provider[] };

export function AiProviderAccessPanel(): JSX.Element {
  const [data, setData] = useState<Response | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [saved, setSaved] = useState('');
  useEffect(() => { void apiFetch<Response>('/ai-provider-access').then(setData).catch(e => setError(String(e))); }, []);
  function change(id: string, patch: Partial<Access>) {
    setSaved('');
    setData(old => old ? {...old, providers: old.providers.map(p => p.id === id ?
      {...p, access: {...p.access, ...patch}} : p)} : old);
  }
  async function save() {
    if (!data) return;
    setBusy(true); setError(''); setSaved('');
    try {
      const result = await apiFetch<Response>('/ai-provider-access', {
        method: 'PUT', body: JSON.stringify({allow_additional_spend: data.allow_additional_spend,
          providers: Object.fromEntries(data.providers.map(p => [p.id, p.access]))}) });
      setData(result); setSaved('Saved. Eligibility is still subject to live provider verification.');
    } catch (e) { setError(String(e)); } finally { setBusy(false); }
  }
  return <Card className='space-y-4 p-6' data-testid='ai-provider-access'>
    <div><h2 className='text-lg font-semibold'>AI providers & usage</h2>
      <p className='text-sm text-muted-foreground'>Connect the AI access you already have. ChatGPT UI is preferred; local Ollama is last. Installed does not mean authenticated. API credentials must be configured through supported secure integrations, not entered here.</p></div>
    <label className='flex items-center gap-2 text-sm'><input type='checkbox' checked={data?.allow_additional_spend ?? false}
      onChange={e => setData(old => old ? {...old, allow_additional_spend: e.target.checked} : old)} />
      Allow additional paid API usage (off by default; requires known per-request cost)</label>
    {data && <div className='grid gap-3 md:grid-cols-2'>{data.providers.map(p =>
      <div key={p.id} className='rounded-lg border border-border p-3 space-y-2'>
        <div className='flex justify-between gap-2'><strong className='text-sm'>{p.label}</strong><span className='text-xs text-muted-foreground'>{p.installed ? 'Detected' : 'Not detected'} · {p.method}</span></div>
        <label className='flex items-center gap-2 text-xs'><input type='checkbox' checked={p.access.enabled} onChange={e => change(p.id, {enabled: e.target.checked})} /> Enable provider</label>
        <label className='block text-xs'>My access
          <select className='mt-1 w-full rounded border border-border bg-background p-1.5' value={p.access.access}
            onChange={e => change(p.id, {access: e.target.value as Access['access']})}>
            {['unknown','free','subscription','api','local'].map(v => <option key={v} value={v}>{v}</option>)}
          </select></label>
        <label className='flex items-center gap-2 text-xs'><input type='checkbox' checked={p.access.authenticated} onChange={e => change(p.id, {authenticated: e.target.checked})} /> Account/API access confirmed by me</label>
        <label className='flex items-center gap-2 text-xs'><input type='checkbox' checked={p.access.supports_automation} onChange={e => change(p.id, {supports_automation: e.target.checked})} /> Supported automation method confirmed</label>
        <label className='flex items-center gap-2 text-xs'><input type='checkbox' checked={p.access.included_usage_available} onChange={e => change(p.id, {included_usage_available: e.target.checked})} /> Included/free usage available</label>
        <p className='text-xs text-muted-foreground'>Coding / reasoning · {p.eligible_without_extra_spend ? 'Eligible by saved declarations' : 'Not yet eligible'}</p>
      </div> )}</div>}
    {error && <p role='alert' className='text-sm text-destructive'>{error}</p>}
    {saved && <p role='status' className='text-sm text-muted-foreground'>{saved}</p>}
    <Button type='button' disabled={busy || !data} onClick={() => void save()}>{busy ? 'Saving...' : 'Save provider preferences'}</Button>
  </Card>;
}
