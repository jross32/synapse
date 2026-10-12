import { useEffect, useState } from 'react';
import { Cloud, ExternalLink, RefreshCw, ShieldCheck, Unplug } from 'lucide-react';
import { apiFetch } from '../lib/api-client';
import { openExternal } from '../lib/electron-bridge';
import { Button } from './ui/button';
import { Card } from './ui/card';

interface RailwayConnection { configured: boolean; connected: boolean; railway_email: string | null; account_bound: boolean }
export function RailwayConnect({ emailVerified }: { emailVerified: boolean }): JSX.Element {
  const [info, setInfo] = useState<RailwayConnection | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  async function refresh(): Promise<void> {
    if (!emailVerified) { setInfo(null); setError('Verify your Synapse account email before authorizing Railway.'); return; }
    try {
      setInfo(await apiFetch<RailwayConnection>('/system/railway-oauth/status'));
      setError('');
    } catch (e) { setError(e instanceof Error ? e.message : 'Could not read connection status'); }
  }
  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => void refresh(), 10000);
    return () => window.clearInterval(timer);
  }, [emailVerified]);
  async function connect(): Promise<void> {
    setBusy(true);
    try {
      const result = await apiFetch<{ url: string }>('/system/railway-oauth/start', { method: 'POST' });
      const opened = await openExternal(result.url);
      if (!opened.ok) throw new Error(opened.error || 'Could not open Railway authorization');
      setError('');
    } catch (e) { setError(e instanceof Error ? e.message : 'Connection failed'); }
    finally { setBusy(false); }
  }
  async function disconnect(): Promise<void> {
    setBusy(true);
    try { await apiFetch('/system/railway-oauth', { method: 'DELETE' }); await refresh(); }
    catch (e) { setError(e instanceof Error ? e.message : 'Could not disconnect'); }
    finally { setBusy(false); }
  }
  return <Card className="space-y-4 p-5" data-testid="railway-developer-connection">
    <div className="flex items-center gap-3">
      <span className="rounded-xl border border-violet-400/30 bg-violet-400/10 p-3 text-violet-300"><Cloud className="h-5 w-5"/></span>
      <div><h3 className="font-semibold">Railway ? Developer</h3><p className="text-xs text-muted-foreground">Private infrastructure connection for the Synapse owner only</p></div>
    </div>
    <p className="text-sm text-muted-foreground">Authorize through Railway's official website. Only projects you approve can be viewed. Other Synapse users do not need this connection.</p>
    <div className="flex flex-wrap items-center gap-2">
      <span className="rounded-full border border-border bg-secondary px-3 py-1 text-xs">{!emailVerified ? 'Email verification required' : info?.connected ? 'Connected' : info?.configured ? 'Not connected' : 'OAuth app setup required'}</span>
      {info?.railway_email && <span className="text-xs text-muted-foreground">{info.railway_email}</span>}
    </div>
    {error && <p role="alert" className="text-xs text-red-400">{error}</p>}
    <div className="flex flex-wrap gap-2">
      {info?.connected
        ? <Button variant="outline" disabled={busy} onClick={() => void disconnect()}><Unplug className="h-4 w-4"/>Disconnect</Button>
        : <Button disabled={busy || !emailVerified || !info?.configured} onClick={() => void connect()}><ShieldCheck className="h-4 w-4"/>Connect Railway <ExternalLink className="h-4 w-4"/></Button>}
      <Button variant="outline" disabled={busy} onClick={() => void refresh()}><RefreshCw className="h-4 w-4"/>Refresh status</Button>
    </div>
    {emailVerified && !info?.configured && <p className="text-xs text-amber-300">Register the Synapse OAuth application in Railway Developer settings and set SYNAPSE_RAILWAY_OAUTH_CLIENT_ID on this computer to enable the Connect button.</p>}
  </Card>;
}
