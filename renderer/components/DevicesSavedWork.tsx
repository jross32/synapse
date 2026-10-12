import { useState } from 'react';
import { BookOpen, CheckCircle2, Cloud, HardDrive, Info, Laptop, Loader2, Monitor, Plus, RefreshCw, UserRound } from 'lucide-react';
import type { HostPresence, ProfileSummary } from '@shared/generated-types';
import type { McpConnections } from '@shared/profile-client';
import { formatLocal } from '@shared/format-time';
import './devices-saved-work.css';

interface Props {
  profile: ProfileSummary;
  hosts: HostPresence[];
  connections: McpConnections | null;
  busy: boolean;
  onRefresh: () => Promise<void>;
  onToggleAccess: (enabled: boolean) => Promise<void>;
}
export function DevicesSavedWork({ profile, hosts, connections, busy, onRefresh, onToggleAccess }: Props): JSX.Element {
  const [details, setDetails] = useState<string | null>(null);
  const [connectHelp, setConnectHelp] = useState(false);
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
    <div className="saved-work-footer"><span><BookOpen size={30}/></span><div><h3>Back online? You’re ready.</h3><p>When the computer reconnects with access enabled, its saved local work can be reached again. Cloud files need their storage service connected.</p><small>Local sign-ins and device permissions stay on each computer. Files are not automatically copied between computers or uploaded to the account service.</small></div></div>
  </section>;
}
