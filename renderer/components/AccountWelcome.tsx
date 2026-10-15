import { useEffect, useState, type FormEvent } from 'react';
import { ArrowRight, Cloud, Globe2, Laptop2, Loader2, LockKeyhole, RefreshCw, ShieldCheck } from 'lucide-react';
import { useDaemon } from '@shared/daemon-context';
import { openExternal } from '@shared/electron-bridge';
import { signInProfile, signUpProfile, startProfileAuth } from '@shared/profile-client';

/** Full-window entry gate; don't render local project data before profile sign-in. */
export function AccountWelcome(): JSX.Element {
  const { profile, profileError, refreshProfile } = useDaemon();
  const [mode, setMode] = useState<'signin' | 'signup'>('signin');
  const [email, setEmail] = useState('');
  const [username, setUsername] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [busy, setBusy] = useState(false);
  const [googlePending, setGooglePending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const reachable = profile?.account_backend_reachable === true;
  const googleAvailable = (profile?.available_auth_providers ?? []).includes('google');

  // OAuth happens in a separate browser. Refresh until the local callback has
  // exchanged the one-time handoff and the daemon reports a signed-in profile.
  useEffect(() => {
    if (!googlePending || profile?.signed_in) return;
    const timer = window.setInterval(() => void refreshProfile().catch(() => undefined), 1500);
    return () => window.clearInterval(timer);
  }, [googlePending, profile?.signed_in, refreshProfile]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    if (!reachable || busy) return;
    if (mode === 'signup' && (password !== confirm || password.length < 8)) {
      setError('Use at least 8 characters and make sure both passwords match.');
      return;
    }
    setBusy(true);
    try {
      if (mode === 'signin') {
        await signInProfile({ login: email.trim(), password });
      } else {
        await signUpProfile({
          email: email.trim(),
          username: (username.trim() || email.trim()),
          display_name: displayName.trim() || null,
          password,
        });
      }
      setPassword('');
      setConfirm('');
      await refreshProfile();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Unable to sign in. Try again.');
    } finally {
      setBusy(false);
    }
  }

  async function signInGoogle() {
    if (!googleAvailable || busy) return;
    setBusy(true);
    setError(null);
    try {
      const result = await startProfileAuth('google');
      await openExternal(result.url);
      setGooglePending(true);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Google sign-in could not start.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center overflow-y-auto bg-background px-4 py-8 text-foreground">
      <div className="pointer-events-none fixed inset-0 bg-[radial-gradient(ellipse_at_30%_0%,hsl(var(--primary)/0.12),transparent_60%)]" />
      <div className="relative grid w-full max-w-4xl overflow-hidden rounded-3xl border border-border bg-card shadow-2xl lg:grid-cols-[0.95fr_1.05fr]">
        <aside className="hidden flex-col justify-between bg-primary/5 p-9 lg:flex">
          <div className="space-y-5">
            <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-primary/15 text-primary"><Cloud className="h-6 w-6" /></div>
            <h1 className="text-4xl font-semibold tracking-tight">One account. Every Synapse machine.</h1>
            <p className="text-sm leading-7 text-muted-foreground">Sign in to see your connected computers, portable settings and tools together. Your files and running projects stay on their original computers.</p>
          </div>
          <div className="space-y-4 text-sm text-muted-foreground">
            <div className="flex items-center gap-3"><Laptop2 className="h-5 w-5 text-primary" /> Multiple Windows computers, one identity</div>
            <div className="flex items-center gap-3"><ShieldCheck className="h-5 w-5 text-primary" /> Account sessions stay separate from machine control</div>
            <div className="flex items-center gap-3"><Globe2 className="h-5 w-5 text-primary" /> Secure shared accounts over HTTPS</div>
          </div>
        </aside>
        <section className="p-6 sm:p-9" aria-label="Synapse account">
          <div className="mb-7">
            <div className="text-sm font-semibold tracking-wider text-primary">SYNAPSE</div>
            <h2 className="mt-3 text-2xl font-semibold">{mode === 'signin' ? 'Welcome back' : 'Create your account'}</h2>
            <p className="mt-1 text-sm text-muted-foreground">Sign in to open your Synapse workspace.</p>
          </div>
          <div className="mb-5 grid grid-cols-2 rounded-xl bg-secondary p-1 text-sm">
            <button type="button" className={'rounded-lg px-3 py-2 ' + (mode === 'signin' ? 'bg-background font-semibold shadow-sm' : 'text-muted-foreground')} onClick={() => { setMode('signin'); setError(null); }}>Sign in</button>
            <button type="button" className={'rounded-lg px-3 py-2 ' + (mode === 'signup' ? 'bg-background font-semibold shadow-sm' : 'text-muted-foreground')} onClick={() => { setMode('signup'); setError(null); }}>Create account</button>
          </div>
          <form onSubmit={event => void submit(event)} className="space-y-3">
            {mode === 'signup' && (
              <>
                <label className="block text-sm">Username <input className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2.5" value={username} onChange={e => setUsername(e.target.value)} autoComplete="username" placeholder="Your username" minLength={3} maxLength={32} required /></label>
                <label className="block text-sm">Display name (optional) <input className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2.5" value={displayName} onChange={e => setDisplayName(e.target.value)} autoComplete="name" /></label>
              </>
            )}
            <label className="block text-sm">{mode === 'signin' ? 'Email or username' : 'Email'}<input className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2.5" type={mode === 'signin' ? 'text' : 'email'} autoComplete="email" value={email} onChange={e => setEmail(e.target.value)} placeholder="you@example.com" required /></label>
            <label className="block text-sm">Password <input className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2.5" type="password" autoComplete={mode === 'signin' ? 'current-password' : 'new-password'} minLength={8} value={password} onChange={e => setPassword(e.target.value)} required /></label>
            {mode === 'signup' && <label className="block text-sm">Confirm password <input className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2.5" type="password" autoComplete="new-password" value={confirm} onChange={e => setConfirm(e.target.value)} required /></label>}
            {(error || profileError) && <p role="alert" className="rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">{error || profileError}</p>}
            {!reachable && <div className="flex items-center justify-between gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-foreground"><span>Account service unavailable. Internet access is required for first sign-in.</span><button type="button" onClick={() => void refreshProfile()} className="flex items-center gap-1 underline"><RefreshCw className="h-3 w-3" />Retry</button></div>}
            <button type="submit" disabled={!reachable || busy} className="flex w-full items-center justify-center gap-2 rounded-xl bg-primary px-4 py-3 font-semibold text-primary-foreground disabled:opacity-50">{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <ArrowRight className="h-4 w-4" />}{mode === 'signin' ? 'Sign in to Synapse' : 'Create account'}</button>
          </form>
          <div className="my-5 flex items-center gap-3 text-xs text-muted-foreground"><div className="h-px flex-1 bg-border" />or<div className="h-px flex-1 bg-border" /></div>
          <button type="button" disabled={!reachable || !googleAvailable || busy} onClick={() => void signInGoogle()} className="flex w-full items-center justify-center gap-2 rounded-xl border border-border px-4 py-3 text-sm font-medium disabled:opacity-50"><LockKeyhole className="h-4 w-4" />Continue with Google</button>
          {!googleAvailable && <p className="mt-2 text-center text-xs text-muted-foreground">Google sign-in is not configured on the account server yet. Email sign-in is available.</p>}
          {googlePending && <p className="mt-3 text-center text-xs text-muted-foreground">Finish Google sign-in in your browser; Synapse will continue automatically.</p>}
        </section>
      </div>
    </main>
  );
}
