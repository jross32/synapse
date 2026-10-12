import { useEffect, useMemo, useState } from 'react';
import { BookOpen, CheckCircle2, Cloud, HardDrive, Info, Laptop, Loader2, Monitor, Plus, RefreshCw, UserRound } from 'lucide-react';
import type { CatalogPreferenceState, HostPresence, ProfileSummary } from '@shared/generated-types';
import { getDeviceParity, type DeviceParityResult, type McpConnections } from '@shared/profile-client';
import { formatLocal } from '@shared/format-time';
import './devices-saved-work.css';

interface Props {
  profile: ProfileSummary;
  hosts: HostPresence[];
  catalog: CatalogPreferenceState | null;
  connections: McpConnections | null;
  busy: boolean;
  onRefresh: () => Promise<void>;
  onToggleAccess: (enabled: boolean) => Promise<void>;
}
export function DevicesSavedWork({ profile, hosts, catalog, connections, busy, onRefresh, onToggleAccess }: Props): JSX.Element {
  const [details, setDetails] = useState<string | null>(null);
  const [connectHelp, setConnectHelp] = useState(false);
  const [sourceId, setSourceId] = useState('');
  const [selectedKeys, setSelectedKeys] = useState<string[]>([]);
  const [parity, setParity] = useState<DeviceParityResult | null>(null);
  const [parityError, setParityError] = useState('');
  const [parityLoading, setParityLoading] = useState(false);
  const candidateSources = hosts.filter(h => h.id !== profile.current_host.id && !h.current_host);
  const source = candidateSources.find(h => h.id === sourceId) ?? candidateSources[0];
  useEffect(() => {
    let active = true; setParity(null); setParityError('');
    if (!source?.id) return;
    setParityLoading(true);
    void getDeviceParity(source.id).then(result => { if(active) setParity(result); }).catch(err => {if(active) setParityError((err as Error).message || 'Unable to verify comparison');}).finally(() => {if(active) setParityLoading(false);});
    return () => {active=false;};
  }, [source?.id, catalog]);
  const missing = useMemo(() => (catalog?.items ?? []).filter(item =>
    (item.kind === 'tool' || item.kind === 'bundle') &&
    !item.installed_here && Boolean(source && item.installed_host_ids.includes(source.id))
  ), [catalog, source?.id]);
  const missingKey = missing.map(item => item.item_key).sort().join('|');
  useEffect(() => { setSelectedKeys(missing.map(item => item.item_key)); }, [source?.id, missingKey]);
  const chosen = missing.filter(item => selectedKeys.includes(item.item_key));
  const planText = ['Synapse device parity plan', `Source: ${source?.name ?? 'Unknown'}`, `Destination: ${profile.current_host.name}`,
    ...chosen.map(item => `- ${item.kind}: ${item.item_id}`),
    'Install selection only. No files, credentials or account permissions are transferred by this plan.'].join('\n');
  const [copied, setCopied] = useState(false);
  async function copyPlan(): Promise<void> {
    try { await navigator.clipboard.writeText(planText); setCopied(true); }
    catch { setCopied(false); }
  }
  const syncProblem = !!profile.last_sync_error || !profile.account_backend_reachable;
  const status = !profile.sync_enabled ? 'Automatic sync needs attention' : syncProblem ? 'Saved locally · waiting to sync' : profile.last_sync_at ? 'Account settings synchronized' : 'Waiting for sync confirmation';
  const otherHosts = hosts.filter(host => host.id !== profile.current_host.id && !host.current_host);
  // Preserve old registration identities while keeping the current machine prominent.
  const previousRegistrations = otherHosts.filter(host => host.name === profile.current_host.name && host.platform === profile.current_host.platform);
  const devices = [profile.current_host, ...otherHosts.filter(host => !previousRegistrations.includes(host))];
  return <section className="saved-work" aria-labelledby="saved-work-title">
    <header className="saved-work-header">
      <div><h2 id="saved-work-title">Devices &amp; saved work</h2><p>Synapse saves automatically. Pick up where you left off.</p></div>
      <span className="saved-work-status" role="status">{busy ? <Loader2 className="saved-work-spin" size={17}/> : syncProblem ? <Info size={17}/> : <CheckCircle2 size={17}/>} {busy ? 'Checking status' : status}</span>
    </header>
    <div className={'saved-work-banner' + (syncProblem || !profile.sync_enabled ? ' saved-work-banner--waiting' : '')}>
      <CheckCircle2 size={33}/><div><h3>{profile.sync_enabled ? 'Automatic sync is on' : 'Automatic sync needs attention'}</h3><p>Your preferences follow you. Your work stays where you save it.</p>
      {profile.last_sync_at && <small>Last account sync: {formatLocal(profile.last_sync_at, 'long')}</small>}
      {(syncProblem || !profile.sync_enabled) && <p>Local work is retained. Check your connection to resume account sync.</p>}</div>
      <button type="button" disabled={busy} onClick={() => void onRefresh()}><RefreshCw size={15}/> {syncProblem || !profile.sync_enabled ? 'Retry sync' : 'Refresh'}</button>
    </div>
    <div className="saved-work-grid">
      <section className="saved-work-panel"><h3>Your computers</h3>
        {devices.map(host => {
          const current = host.current_host || host.id === profile.current_host.id;
          const enabled = connections?.device?.enabled;
          const Icon = host.platform.toLowerCase().includes('darwin') ? Laptop : Monitor;
          return <div className="saved-work-device" key={host.id}>
            <Icon className="saved-work-device-icon" size={39}/>
            <div className="saved-work-device-copy"><div className="saved-work-device-title"><strong>{host.name}</strong><span className={'saved-work-pill ' + (current ? 'saved-work-pill--online' : '')}>{current ? 'Online · this computer' : 'Previously connected'}</span></div>
              <p>{current ? enabled === false ? 'AI access paused. Saved work stays on this computer.' : 'Local work accessible' : 'Local work needs this computer online and access enabled.'}</p>
              {!current && <small>Last reported: {formatLocal(host.last_seen_at, 'long')}</small>}
              {details === host.id && <p className="saved-work-details">{host.platform} · Live remote availability has not been verified. Disconnecting access does not delete saved files.</p>}
            </div>
            {current && typeof enabled === 'boolean' ? <button type="button" disabled={busy} onClick={() => void onToggleAccess(!enabled)} aria-label={(enabled ? 'Disconnect AI access to ' : 'Reconnect AI access to ') + host.name}>{enabled ? 'Disconnect' : 'Reconnect'}</button> : <button type="button" onClick={() => setDetails(details === host.id ? null : host.id)} aria-expanded={details === host.id}>Details</button>}
          </div>;
        })}
        {previousRegistrations.length > 0 && <details className="saved-work-history"><summary>{previousRegistrations.length} other {previousRegistrations.length === 1 ? 'registration uses' : 'registrations use'} this computer name</summary><p>These are separate saved registration records. They have not been deleted or assumed to be the same physical computer.</p>{previousRegistrations.map(host => <p key={host.id}>{host.name} · Last reported {formatLocal(host.last_seen_at, 'long')}</p>)}</details>}
        <button className="saved-work-connect" type="button" onClick={() => setConnectHelp(!connectHelp)} aria-expanded={connectHelp}><Plus size={23}/> Connect a computer</button>
        {connectHelp && <p className="saved-work-details">Install Synapse on your other computer and sign in to this same account. Its saved preferences and device registration will appear here. Enable AI access on that computer to make it available to your AI tools.</p>}
        <p className="saved-work-note"><Info size={17}/> Disconnect pauses AI access on this computer. It does not delete saved work or stop account preference sync.</p>
      </section>
      <section className="saved-work-panel"><h3>Where your work lives</h3>
        <div className="saved-work-location"><span><HardDrive size={25}/></span><div><strong>On your computers</strong><p>Projects, files, logs &amp; conversations</p></div></div>
        <div className="saved-work-location"><span><Cloud size={25}/></span><div><strong>Connected storage</strong><p>Files you save to your connected services</p></div><small className="saved-work-pill">Optional</small></div>
        <div className="saved-work-location"><span><UserRound size={25}/></span><div><strong>Your Synapse account</strong><p>Preferences, favorites &amp; device list</p></div></div>
      </section>
    </div>
    <section className="saved-work-parity" aria-labelledby="saved-work-parity-title">
      <div className="saved-work-parity-head"><div><h3 id="saved-work-parity-title">Match another computer</h3><p>Review what your other computer has installed. Missing tools are preselected, but nothing installs without your approval.</p></div><span className="saved-work-pill">Review only</span></div>
      {candidateSources.length === 0 ? <p>No other registered computer yet. Sign in on another machine to compare its recorded installs.</p> : <>
        <label className="saved-work-parity-source">Compare with <select value={source?.id ?? ''} onChange={event => setSourceId(event.target.value)}>{candidateSources.map(host => <option value={host.id} key={host.id}>{host.name}</option>)}</select></label>
        {parityLoading && <p role="status">Checking the account catalog for recorded device differences...</p>}
        {parityError && <p role="alert">Parity endpoint unavailable: {parityError}. Showing cached catalog entries, not verified live installs.</p>}
        {!catalog ? <p role="status">Install history has not loaded. Refresh to retry; no changes were made.</p> : <>
          {parity && <p role="status">Verified catalog comparison returned {parity.items.length} missing records. Full device inventory and automatic installation are not available.</p>}
          <div className="saved-work-parity-actions"><strong>{chosen.length} of {missing.length} missing items selected</strong><button type="button" onClick={() => setSelectedKeys(missing.map(item => item.item_key))}>Select all</button><button type="button" onClick={() => setSelectedKeys([])}>Clear all</button></div>
          {missing.length ? <div className="saved-work-parity-list">{missing.map(item => <label key={item.item_key} className="saved-work-parity-item"><input type="checkbox" checked={selectedKeys.includes(item.item_key)} onChange={event => setSelectedKeys(current => event.target.checked ? [...current, item.item_key] : current.filter(key => key !== item.item_key))}/><span><strong>{item.item_id}</strong><small>{item.kind === 'bundle' ? 'Skill/bundle' : 'Tool'} � Recorded on {source?.name}; install availability not verified</small></span></label>)}</div> : <p>No recorded tool or bundle differences for this device. This does not confirm project files or apps match.</p>}
          <div className="saved-work-parity-actions"><button type="button" disabled={!chosen.length} onClick={() => void copyPlan()}>{copied ? 'Plan copied' : 'Copy selected setup plan'}</button></div>
        </>}
      </>}
      <p className="saved-work-parity-note"><Info size={15}/> Synapse can currently compare recorded tool and bundle installs, not every installed Windows program. Project files, local credentials, tokens, browser sessions, and host-specific drivers are not automatically copied. Those require separately verified inventory, authorization, and migration.</p>
    </section>
    <div className="saved-work-footer"><span><BookOpen size={30}/></span><div><h3>Back online? You’re ready.</h3><p>When the computer reconnects with access enabled, its saved local work can be reached again. Cloud files need their storage service connected.</p><small>Local sign-ins and device permissions stay on each computer. Files are not automatically copied between computers or uploaded to the account service.</small></div></div>
  </section>;
}

