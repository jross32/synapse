import { useEffect, useState } from 'react';
import {
  AlertTriangle, Check, CheckCircle2, Cloud, HardDrive, Laptop, LockKeyhole,
  Monitor, RefreshCw, ShieldCheck, X,
} from 'lucide-react';
import { getProfile, getProfileHosts, updateProfileConfig } from '../lib/profile-client';
import type { HostPresence, ProfileSummary } from '../lib/generated-types';
import { SyncNeuralMark } from './SyncNeuralMark';
import './device-sync-onboarding.css';

type Step = 'offer' | 'syncing' | 'success' | 'warning';
interface Props {
  signedIn: boolean;
  accountId?: string | null;
  currentHostId?: string | null;
  onClose?: () => void;
}
const dismissedKey = (id: string, device: string) => 'synapse.device-sync.dismissed.v2.' + id + '.' + device;
function timestamp(value: string): string {
  const ms = Date.parse(value);
  if (!Number.isFinite(ms)) return 'Status not verified';
  return 'Last reported ' + new Date(ms).toLocaleString();
}
function stageMessage(step: Step, profile: ProfileSummary | null): string {
  if (step === 'syncing') return 'Contacting your Synapse account and verifying saved settings.';
  if (step === 'success') return 'Account preferences synchronized. Project files stay on their original machines.';
  if (profile?.last_sync_error) return 'Sync is enabled, but the cloud reported a problem.';
  return 'Account sync is enabled. Cloud confirmation is not available yet.';
}

/** Device discovery is informational; this never initiates a project-file transfer. */
export function DeviceSyncOnboarding({ signedIn, accountId, currentHostId, onClose }: Props): JSX.Element | null {
  const [hosts, setHosts] = useState<HostPresence[]>([]);
  const [visible, setVisible] = useState(false);
  const [step, setStep] = useState<Step>('offer');
  const [profile, setProfile] = useState<ProfileSummary | null>(null);
  const [error, setError] = useState('');
  const [selected, setSelected] = useState(true);
  const [retrying, setRetrying] = useState(false);
  const [showDetails, setShowDetails] = useState(false);
  const [syncStartedAt, setSyncStartedAt] = useState<number | null>(null);
  const [completion, setCompletion] = useState(0);
  useEffect(() => {
    if (step !== 'success') { setCompletion(0); return; }
    let frame = 0;
    const interval = window.setInterval(() => {
      frame += 1;
      setCompletion(Math.min(100, Math.round(100 * (1 - Math.pow(1 - frame / 30, 3)))));
      if (frame >= 30) window.clearInterval(interval);
    }, 30);
    return () => window.clearInterval(interval);
  }, [step]);
  useEffect(() => {
    let alive = true;
    setVisible(false);
    setStep('offer');
    setError('');
    if (!signedIn || !accountId || !currentHostId ||
        sessionStorage.getItem(dismissedKey(accountId, currentHostId))) return;
    void getProfileHosts().then((items) => {
      if (!alive) return;
      const others = items.filter((host) => host.id !== currentHostId && !host.current_host);
      setHosts(others);
      setVisible(others.length > 0);
    }).catch(() => { /* No discovery means no speculative devices shown. */ });
    return () => { alive = false; };
  }, [signedIn, accountId, currentHostId]);

  function close() {
    if (accountId && currentHostId) sessionStorage.setItem(dismissedKey(accountId, currentHostId), '1');
    setVisible(false);
    onClose?.();
  }
  async function enable() {
    if (!selected) return;
    const started = Date.now();
    setSyncStartedAt(started);
    setStep('syncing');
    setError('');
    try {
      const result = await updateProfileConfig({ sync_enabled: true });
      setProfile(result);
      // A failed cloud sync can be swallowed by the backend as best-effort.
      // Re-read the returned profile before displaying success.
      const latest = await getProfile();
      setProfile(latest);
      setStep(latest.sync_enabled && latest.account_backend_reachable &&
        !latest.last_sync_error && Boolean(latest.last_sync_at) &&
        Date.parse(latest.last_sync_at ?? '') >= started - 3000 ? 'success' : 'warning');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not enable sync.');
      setStep('offer');
    }
  }
  async function retry() {
    setRetrying(true);
    setError('');
    try {
      const updated = await getProfile();
      setProfile(updated);
      setStep(updated.sync_enabled && updated.account_backend_reachable &&
        !updated.last_sync_error && Boolean(updated.last_sync_at) &&
        syncStartedAt !== null && Date.parse(updated.last_sync_at ?? '') >= syncStartedAt - 3000 ? 'success' : 'warning');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unable to verify account status.');
    } finally { setRetrying(false); }
  }
  if (!visible) return null;
  return <div className="syn-sync-backdrop">
    <section className="syn-sync-dialog" role="dialog" aria-modal="true"
      aria-labelledby="syn-sync-title" aria-describedby="syn-sync-description">
      <button className="syn-sync-close" type="button" aria-label="Close sync setup" onClick={close}><X size={19}/></button>
      <div className="syn-sync-symbol"><SyncNeuralMark /></div>
      <div className="syn-sync-eyebrow"><LockKeyhole size={14}/> Secure Synapse device connection</div>
      {step === 'offer' ? <>
        <h2 id="syn-sync-title">Sync your Synapse experience?</h2>
        <p id="syn-sync-description">We found {hosts.length} other {hosts.length === 1 ? 'device' : 'devices'} previously registered to your Synapse account. Choose whether to bring supported settings and workspace information together.</p>
        <div className="syn-sync-machines">
          <div className="syn-sync-machine"><Laptop size={37}/><strong>{hosts[0]?.name ?? 'Another device'}</strong><small>{timestamp(hosts[0]?.last_seen_at ?? '')}</small></div>
          <div className="syn-sync-link" aria-hidden="true"><span/><RefreshCw size={20}/><span/></div>
          <div className="syn-sync-machine"><Monitor size={37}/><strong>This computer</strong><small>Current session</small></div>
        </div>
        <label className="syn-sync-option"><input type="checkbox" checked={selected} onChange={e=>setSelected(e.target.checked)}/><span><strong>Sync account settings and preferences</strong><small>Dashboard layout, supported account preferences, and portable catalog settings</small></span><Check size={16}/></label>
        <div className="syn-sync-details"><ShieldCheck size={18}/><div><strong>Private by design</strong><p>No files, project source code, local AI credentials, or browser sessions will be copied automatically. Remote project access requires an enrolled and online device.</p></div></div>
        {hosts.length > 1 && <button className="syn-sync-details-toggle" type="button" onClick={()=>setShowDetails(v=>!v)}>{showDetails?'Hide':'Show'} {hosts.length} discovered devices</button>}
        {showDetails && <ul className="syn-sync-host-list">{hosts.map(h=><li key={h.id}><Monitor size={14}/><span>{h.name}</span><small>{timestamp(h.last_seen_at)}</small></li>)}</ul>}
        {error && <p className="syn-sync-error" role="alert">{error}</p>}
        <div className="syn-sync-actions"><button className="syn-sync-secondary" onClick={close}>Not now</button><button className="syn-sync-primary" onClick={()=>void enable()} disabled={!selected}><RefreshCw size={17}/> Enable sync</button></div>
      </> : <>
        <h2 id="syn-sync-title">{step==='syncing'?'Connecting your Synapse account':step==='success'?'Account settings synchronized':'Account sync needs attention'}</h2>
        <p id="syn-sync-description" role="status">{stageMessage(step,profile)}</p>
        <div className="syn-sync-machines syn-sync-machines--active"><div className="syn-sync-machine"><Laptop size={38}/><strong>{hosts[0]?.name ?? 'Other device'}</strong><small>Previously registered</small></div><div className="syn-sync-link" aria-hidden="true"><span/><RefreshCw className={step==='syncing'?'syn-sync-spin':''} size={23}/><span/></div><div className="syn-sync-machine"><Monitor size={38}/><strong>This computer</strong><small>Signed in</small></div></div>
        {step === 'success' && <div className="syn-sync-completion" role="status" aria-label={'Account settings synchronization ' + completion + ' percent'}><span>{completion}%</span><small>Account settings synchronized</small></div>}
        <div className="syn-sync-progress" aria-label="Synchronization stages">
          <div style={step==='success'?{width:completion+'%'}:undefined} className={step==='syncing'?'syn-sync-progress-indeterminate':step==='success'?'syn-sync-progress-complete':'syn-sync-progress-partial'}/>
        </div>
        <ul className="syn-sync-stages">
          <li><CheckCircle2 size={17}/> Account signed in <span>Verified</span></li>
          <li>{step==='syncing'?<RefreshCw className="syn-sync-spin" size={17}/>:step==='success'?<CheckCircle2 size={17}/>:<AlertTriangle size={17}/>} Cloud settings synchronization <span>{step==='syncing'?'Checking':step==='success'?'Verified':'Not verified'}</span></li>
          <li><HardDrive size={17}/> Other device and project files <span>Not transferred</span></li>
        </ul>
        {profile?.last_sync_at && <p className="syn-sync-timestamp">Last cloud sync: {timestamp(profile.last_sync_at)}</p>}
        {profile?.last_sync_error && <p className="syn-sync-error" role="alert">{profile.last_sync_error}</p>}
        {error && <p className="syn-sync-error" role="alert">{error}</p>}
        {step!=='syncing' && <div className="syn-sync-actions">
          {step==='warning' && <button className="syn-sync-secondary" disabled={retrying} onClick={()=>void retry()}>{retrying?'Checking…':'Check again'}</button>}
          <button className="syn-sync-primary" onClick={close}>{step==='success'?'Continue to Synapse':'Continue with local workspace'}</button>
        </div>}
      </>}
    </section>
  </div>;
}
