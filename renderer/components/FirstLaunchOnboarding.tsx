import { useEffect, useState } from 'react';
import { ArrowLeft, ArrowRight, Bot, CheckCircle2, Cloud, Cpu, KeyRound, Laptop, Link2, LoaderCircle, Monitor, RefreshCw, ShieldCheck, Sparkles, WifiOff } from 'lucide-react';
import { apiFetch } from '../lib/api-client';
import { getProfile, getProfileHosts, signInProfile, signUpProfile, startProfileAuth } from '../lib/profile-client';
import { openExternal } from '../lib/electron-bridge';
import type { ProfileSummary, HostPresence } from '../lib/generated-types';
import { advanceProgress, retreatProgress, readProgress, saveProgress, saveCompanion, canAdvanceWithNext, type FirstLaunchProgress, ONBOARDING_STEPS } from '../lib/first-launch-state';
import './first-launch-onboarding.css';

type Status = 'checking' | 'online' | 'offline';
const companions = [
  { id: 'nova', emoji: '\u{1F916}', name: 'Nova', description: 'Bright and curious' },
  { id: 'ninja', emoji: '\u{1F977}', name: 'Ninja', description: 'Fast and focused' },
  { id: 'orbit', emoji: '\u{1F6F8}', name: 'Orbit', description: 'Calm and analytical' },
];
export function FirstLaunchOnboarding({ onComplete }: { onComplete: () => void }): JSX.Element {
  const [progress, setProgress] = useState<FirstLaunchProgress>(() => readProgress(window.localStorage));
  const [profile, setProfile] = useState<ProfileSummary | null>(null);
  const [hosts, setHosts] = useState<HostPresence[]>([]);
  const [daemon, setDaemon] = useState<Status>('checking');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [authView, setAuthView] = useState<'signin' | 'signup'>('signin');
  const [login, setLogin] = useState('');
  const [email, setEmail] = useState('');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [providerPending, setProviderPending] = useState(false);
  const index = ONBOARDING_STEPS.indexOf(progress.step);
  useEffect(() => { saveProgress(window.localStorage, progress); }, [progress]);
  async function checkConnections() {
    setDaemon('checking'); setError('');
    try {
      await apiFetch('/health', { method: 'GET' });
      setDaemon('online');
    } catch { setDaemon('offline'); }
    try {
      const next = await getProfile(); setProfile(next);
      if (next.signed_in) {
        try { setHosts(await getProfileHosts()); } catch { setHosts([]); }
      } else { setHosts([]); }
    } catch { setProfile(null); setHosts([]); }
  }
  useEffect(() => { void checkConnections(); }, []);
  function next() { setError(''); setNotice(''); setProgress(p => advanceProgress(p)); }
  function back() { setError(''); setProgress(p => retreatProgress(p)); }
  async function authenticate() {
    setBusy(true); setError('');
    try {
      if (authView === 'signin') {
        const result = await signInProfile({ login, password });
        setProfile(result); if (!result.signed_in) throw new Error('Sign-in was not confirmed. Please retry.'); setProgress(p => advanceProgress({ ...p, mode: 'account' }));
      } else {
        const result = await signUpProfile({ username, email, password });
        setProfile(result.profile);
        setProgress(p => ({ ...p, mode: result.profile.signed_in ? 'account' : 'undecided' }));
        setNotice(result.notice || 'Account created. Sign in after verifying your email if required.');
        if (result.profile.signed_in) setProgress(p => advanceProgress({ ...p, mode: 'account' }));
      }
      setPassword('');
    } catch (e) { setError(e instanceof Error ? e.message : 'Authentication failed. Try again.'); }
    finally { setBusy(false); }
  }
  async function provider(providerName: 'google' | 'github') {
    setError(''); setProviderPending(true);
    try {
      const result = await startProfileAuth(providerName);
      const opened = await openExternal(result.url);
      if (!opened.ok) throw new Error(opened.error || 'Could not open the browser.');
      setNotice('Finish signing in in your browser, then select Check sign-in.');
    } catch (e) { setError(e instanceof Error ? e.message : 'Could not start sign-in.'); }
    finally { setProviderPending(false); }
  }
  async function refreshSignIn() {
    setBusy(true); setError('');
    try {
      const p = await getProfile(); setProfile(p);
      if (!p.signed_in) { setNotice('No authenticated account session yet.'); return; }
      setProgress(prev => advanceProgress({ ...prev, mode: 'account' }));
    } catch { setError('Could not verify sign-in. Check your connection.'); }
    finally { setBusy(false); }
  }
  function finish() {
    const completed: FirstLaunchProgress = { ...progress, completed: true };
    if (!saveCompanion(window.localStorage, completed.companion)) {
      setError('Could not save your companion preference. Check storage permissions and retry.'); return;
    }
    if (!saveProgress(window.localStorage, completed)) {
      setError('Unable to save setup progress. Check your local storage and retry.'); return;
    }
    setProgress(completed); onComplete();
  }
  const account = progress.mode === 'account' && !!profile?.signed_in;
  return <main className="fl-root">
    <div className="fl-orb fl-orb-one" aria-hidden="true" /><div className="fl-orb fl-orb-two" aria-hidden="true" />
    <header className="fl-top"><div className="fl-brand"><Sparkles size={22} /> SYNAPSE</div><span>FIRST-LAUNCH SETUP</span></header>
    <div className={progress.step === 'welcome' ? 'fl-layout fl-layout-welcome' : 'fl-layout'}>
      <aside className="fl-sidebar" aria-label="Setup progress">
        <p>YOUR JOURNEY</p>
        {ONBOARDING_STEPS.map((step, i) => <div className={'fl-step ' + (i === index ? 'active' : '')} key={step} aria-current={i === index ? 'step' : undefined}>
          <span className="fl-step-number">{i < index ? '✓' : i + 1}</span><span>{['Welcome', 'Your account', 'This computer', 'AI & MCP', 'Companion', 'Ready'][i]}</span>
        </div>)}
        <div className="fl-sidebar-bottom">Each computer has its own private daemon and local token. Your Synapse account can link multiple devices.</div>
      </aside>
      <section className="fl-content" aria-live="polite">
        {progress.step === 'welcome' && <div className="fl-welcome-reference">
          <img src="./onboarding/welcome-reference-v1.jpeg" alt="Synapse premium first-launch welcome artwork with glowing brain and companion mascot" className="fl-welcome-reference-image" />
          <div className="fl-welcome-reference-actions"><button className="fl-primary" onClick={next}>Get started <ArrowRight size={16}/></button></div>
        </div>}
        {progress.step === 'account' && <div className="fl-form">
          <div className="fl-icon"><KeyRound /></div><h1>Your Synapse account</h1>
          <p>Sign in to connect this computer to your account, or continue locally. A fresh installation never silently signs you into an existing account.</p>
          <div className="fl-tabs"><button className={authView === 'signin' ? 'selected' : ''} onClick={() => setAuthView('signin')}>Sign in</button><button className={authView === 'signup' ? 'selected' : ''} onClick={() => setAuthView('signup')}>Create account</button></div>
          {profile?.signed_in && progress.mode === 'account' ? <div className="fl-status good"><CheckCircle2 /> Signed in as {profile.email || profile.username}<button className="fl-secondary" onClick={next}>Continue with this account</button></div> : <form onSubmit={e => { e.preventDefault(); void authenticate(); }}>
            {authView === 'signup' && <><label htmlFor="fl-user">Username</label><input id="fl-user" required value={username} onChange={e => setUsername(e.target.value)} autoComplete="username" /><label htmlFor="fl-email">Email</label><input id="fl-email" required type="email" value={email} onChange={e => setEmail(e.target.value)} autoComplete="email" /></>}
            {authView === 'signin' && <><label htmlFor="fl-login">Email or username</label><input id="fl-login" required value={login} onChange={e => setLogin(e.target.value)} autoComplete="username" /></>}
            <label htmlFor="fl-password">Password</label><input id="fl-password" required type="password" minLength={8} value={password} onChange={e => setPassword(e.target.value)} autoComplete={authView === 'signup' ? 'new-password' : 'current-password'} />
            <button className="fl-primary fl-full" type="submit" disabled={busy}>{busy ? 'Please wait...' : authView === 'signin' ? 'Sign in' : 'Create account'} <ArrowRight size={17} /></button>
          </form>}
          <div className="fl-social"><button onClick={() => void provider('google')} disabled={providerPending}>Continue with Google</button><button onClick={() => void provider('github')} disabled={providerPending}>Continue with GitHub</button></div>
          <button className="fl-link" onClick={() => void refreshSignIn()} disabled={busy}>Check browser sign-in</button>
          <button className="fl-guest" onClick={() => { setProgress(p => advanceProgress({ ...p, mode: 'guest' })); }}>Continue locally without an account <ArrowRight size={16}/></button>
        </div>}
        {progress.step === 'computer' && <div className="fl-form fl-wide"><div className="fl-icon"><Laptop /></div><h1>This computer</h1><p>Synapse runs a private daemon on every computer. Its local authentication token stays on that computer — it is never copied from another device.</p>
          <div className="fl-detail"><Monitor /><div><strong>{profile?.current_host?.name || 'This computer'}</strong><small>{profile?.current_host?.platform || 'Local installation'} · Device identity supplied by Synapse</small></div></div>
          <div className={'fl-status ' + (daemon === 'online' ? 'good' : daemon === 'offline' ? 'bad' : '')}>{daemon === 'checking' ? <LoaderCircle /> : daemon === 'online' ? <CheckCircle2 /> : <WifiOff />}{daemon === 'checking' ? 'Checking local daemon...' : daemon === 'online' ? 'Local daemon responded to health check' : 'Local daemon not reachable'}</div>
          <div className={'fl-status ' + (account ? 'good' : '')}>{account ? <CheckCircle2 /> : <Link2 />}{account ? 'Account session present — device cloud link not independently verified' : 'Local-only mode — you can link an account later'}</div>
          <button className="fl-secondary" onClick={() => void checkConnections()}><RefreshCw size={16}/> Retry checks</button>
        </div>}
        {progress.step === 'connections' && <div className="fl-form fl-wide"><div className="fl-icon"><Cpu /></div><h1>AI and MCP connections</h1><p>Connect ChatGPT and supported AI clients to this installation. A healthy local daemon does not by itself prove an external MCP client is authenticated.</p>
          <div className="fl-detail"><Bot /><div><strong>ChatGPT and other MCP clients</strong><small>Configure a supported authenticated client after entering Synapse. Never paste your private daemon token.</small></div><span className="fl-tag">Not verified</span></div>
          <div className="fl-detail"><Cloud /><div><strong>Other account devices</strong><small>{account ? hosts.length + ' registered host record(s) returned' : 'Sign in to discover your other devices'}</small></div><span className="fl-tag">{account ? 'Registry only' : 'Not linked'}</span></div>
          {account && hosts.map(host => <div className="fl-host" key={host.id}><Monitor size={15}/>{host.name} <small>{host.platform} · {host.current_host ? 'This device' : 'Remote status not verified'}</small></div>)}
          <button className="fl-secondary" onClick={() => void checkConnections()}><RefreshCw size={16}/> Refresh connection status</button>
        </div>}
        {progress.step === 'companion' && <div className="fl-form fl-wide"><div className="fl-icon"><Bot /></div><h1>Choose your companion</h1><p>Pick a friendly face for Synapse. This is a visual preference, not an AI connection. You can change it later.</p><div className="fl-companions">{companions.map(c => <button key={c.id} className={progress.companion === c.id ? 'selected' : ''} onClick={() => setProgress(p => ({ ...p, companion: c.id }))} aria-pressed={progress.companion === c.id}><span>{c.emoji}</span><strong>{c.name}</strong><small>{c.description}</small></button>)}</div><button className="fl-link" onClick={() => { setProgress(p => advanceProgress({ ...p, companion: null })); }}>Skip for now</button></div>}
        {progress.step === 'ready' && <div className="fl-form fl-wide"><div className="fl-icon"><CheckCircle2 /></div><h1>Ready to launch</h1><p>Your workspace is ready to open. Optional connections can be completed later in Settings.</p>
          <div className={'fl-status ' + (daemon === 'online' ? 'good' : 'bad')}>{daemon === 'online' ? <CheckCircle2/> : <WifiOff/>}Local daemon: {daemon === 'online' ? 'responding' : 'not verified'}</div>
          <div className="fl-status">{account ? 'Account session present' : 'Local guest mode'} · Remote device routing not verified</div>
          <div className="fl-status">MCP client authentication: not verified</div><div className="fl-status">Companion: {progress.companion || 'not selected'}</div>
          <button className="fl-primary fl-full" onClick={finish}>Open Synapse <ArrowRight size={17}/></button>
        </div>}
        {(error || notice) && <div className={'fl-feedback ' + (error ? 'fl-error' : '')} role={error ? 'alert' : 'status'}>{error || notice}</div>}
        <footer className="fl-footer"><button className="fl-secondary" disabled={index === 0} onClick={back}><ArrowLeft size={16}/> Back</button><span>{index + 1} of {ONBOARDING_STEPS.length}</span>{progress.step === 'ready' ? <span /> : <button className="fl-primary" onClick={next} disabled={!canAdvanceWithNext(progress, daemon === 'checking')}>{progress.step === 'welcome' ? 'Get started' : 'Continue'} <ArrowRight size={16}/></button>}</footer>
      </section>
    </div>
  </main>;
}




