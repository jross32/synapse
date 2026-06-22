import { useEffect, useMemo, useState } from 'react';
import {
  ArrowRight,
  CheckCircle2,
  Cloud,
  Globe2,
  Laptop2,
  Link2,
  Loader2,
  LockKeyhole,
  Mail,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  Star,
  Unplug,
  UserRound,
  Wand2,
} from 'lucide-react';

import { useDaemon } from '@shared/daemon-context';
import { openExternal } from '@shared/electron-bridge';
import { formatLocal } from '@shared/format-time';
import type {
  CatalogPreferenceItem,
  CatalogPreferenceState,
  HostPresence,
  ServiceConnection,
} from '@shared/generated-types';
import {
  connectService,
  deleteServiceConnection,
  getCatalogState,
  getProfile,
  getProfileHosts,
  getServiceConnections,
  linkProfileAuth,
  setFavorite,
  signInProfile,
  signOutProfile,
  signUpProfile,
  startProfileAuth,
  unlinkProfileProvider,
  updateProfileConfig,
} from '@shared/profile-client';
import { cn } from '@shared/utils';
import { Button } from './ui/button';
import { Card } from './ui/card';
import { Input } from './ui/input';
import { Modal } from './ui/modal';

export interface ProfileHubProps {
  open: boolean;
  onClose: () => void;
  mobileRoute?: boolean;
}

interface SignInFormState {
  login: string;
  password: string;
}

interface SignUpFormState {
  username: string;
  email: string;
  password: string;
  confirmPassword: string;
  displayName: string;
}

const STATUS_TONE: Record<string, string> = {
  ready: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30',
  'needs-attention': 'bg-amber-500/15 text-amber-200 border-amber-500/30',
  disconnected: 'bg-secondary text-muted-foreground border-border/70',
  'local-only': 'bg-sky-500/15 text-sky-200 border-sky-500/30',
};

export function ProfileHub({
  open,
  onClose,
  mobileRoute = false,
}: ProfileHubProps): JSX.Element | null {
  const { profile, profileError, refreshProfile } = useDaemon();
  const [catalogState, setCatalogState] = useState<CatalogPreferenceState | null>(null);
  const [services, setServices] = useState<ServiceConnection[]>([]);
  const [hosts, setHosts] = useState<HostPresence[]>([]);
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [loadingHub, setLoadingHub] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [authMode, setAuthMode] = useState<'signin' | 'signup'>('signin');
  const [syncEnabled, setSyncEnabled] = useState(true);
  const [signinForm, setSigninForm] = useState<SignInFormState>({
    login: '',
    password: '',
  });
  const [signupForm, setSignupForm] = useState<SignUpFormState>({
    username: '',
    email: '',
    password: '',
    confirmPassword: '',
    displayName: '',
  });

  useEffect(() => {
    if (!open) return;
    setSyncEnabled(profile?.sync_enabled ?? true);
  }, [open, profile?.sync_enabled]);

  useEffect(() => {
    if (!open) return;
    void loadHubData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const favorites = useMemo(
    () => (catalogState?.items ?? []).filter((item) => item.favorite).slice(0, 8),
    [catalogState]
  );
  const recent = useMemo(
    () =>
      [...(catalogState?.items ?? [])]
        .filter((item) => item.used_before || item.previously_installed)
        .sort((left, right) => {
          const leftStamp = left.last_used_at ?? left.last_installed_at ?? left.updated_at;
          const rightStamp = right.last_used_at ?? right.last_installed_at ?? right.updated_at;
          return rightStamp.localeCompare(leftStamp);
        })
        .slice(0, 10),
    [catalogState]
  );

  const linkedProviders = new Set((profile?.linked_identities ?? []).map((identity) => identity.provider));
  const availableProviders = new Set(profile?.available_auth_providers ?? []);
  const googleAvailable = availableProviders.has('google');
  // Sign-in only works against a reachable Synapse Accounts service. When none
  // is configured, show an honest "sync is optional" panel instead of forms
  // that always error. Synapse is fully usable without an account.
  const accountBackendReachable = profile?.account_backend_reachable ?? false;

  function validateSignUp(): string | null {
    if (signupForm.username.trim().length < 3) return 'Choose a username with at least 3 characters.';
    if (!signupForm.email.includes('@')) return 'Enter a valid email address.';
    if (signupForm.password.length < 8) return 'Use a password with at least 8 characters.';
    if (signupForm.password !== signupForm.confirmPassword) return 'Password confirmation does not match.';
    return null;
  }

  async function loadHubData(): Promise<void> {
    setLoadingHub(true);
    setError(null);
    const issues: string[] = [];
    try {
      const summary = (await refreshProfile()) ?? (await getProfile());
      if (!summary.signed_in) {
        setCatalogState(null);
        setServices([]);
        setHosts([]);
        return;
      }

      const [catalogRes, servicesRes, hostsRes] = await Promise.allSettled([
        getCatalogState(),
        getServiceConnections(),
        getProfileHosts(),
      ]);

      if (catalogRes.status === 'fulfilled') setCatalogState(catalogRes.value);
      else issues.push((catalogRes.reason as Error).message);

      if (servicesRes.status === 'fulfilled') setServices(servicesRes.value);
      else issues.push((servicesRes.reason as Error).message);

      if (hostsRes.status === 'fulfilled') setHosts(hostsRes.value);
      else issues.push((hostsRes.reason as Error).message);
    } catch (err) {
      issues.push((err as Error).message);
    } finally {
      setLoadingHub(false);
    }
    if (issues.length > 0) setError(issues.join(' '));
  }

  async function runAction(key: string, task: () => Promise<void>): Promise<void> {
    setBusyKey(key);
    setError(null);
    setNotice(null);
    try {
      await task();
    } catch (err) {
      setError((err as Error).message || 'Profile action failed.');
    } finally {
      setBusyKey(null);
    }
  }

  async function saveSyncSettings(): Promise<void> {
    await runAction('sync-settings', async () => {
      await updateProfileConfig({ sync_enabled: syncEnabled });
      await loadHubData();
      setNotice(syncEnabled ? 'Portable sync is enabled for this account.' : 'Portable sync is paused on this host.');
    });
  }

  async function signIn(): Promise<void> {
    await runAction('signin', async () => {
      await signInProfile({
        login: signinForm.login,
        password: signinForm.password,
      });
      await loadHubData();
      setNotice('Signed into your Synapse account.');
      setSigninForm((prev) => ({ ...prev, password: '' }));
    });
  }

  async function signUp(): Promise<void> {
    const validation = validateSignUp();
    if (validation) {
      setError(validation);
      return;
    }
    await runAction('signup', async () => {
      const res = await signUpProfile({
        username: signupForm.username.trim(),
        email: signupForm.email.trim(),
        password: signupForm.password,
        display_name: signupForm.displayName.trim() || null,
      });
      await loadHubData();
      setNotice(res.notice ?? 'Synapse account created and connected.');
      setSignupForm((prev) => ({
        ...prev,
        password: '',
        confirmPassword: '',
      }));
    });
  }

  async function beginSocial(provider: 'google' | 'github', mode: 'signin' | 'link'): Promise<void> {
    await runAction(`${mode}:${provider}`, async () => {
      const res = mode === 'link' ? await linkProfileAuth(provider) : await startProfileAuth(provider);
      await openExternal(res.url);
      setNotice(
        mode === 'link'
          ? `Finish linking ${provider === 'google' ? 'Google' : 'GitHub'} in the browser tab that just opened.`
          : `Finish ${provider === 'google' ? 'Google' : 'GitHub'} sign-in in the browser tab that just opened.`
      );
    });
  }

  async function unlinkProvider(provider: 'google' | 'github'): Promise<void> {
    await runAction(`unlink:${provider}`, async () => {
      await unlinkProfileProvider(provider);
      await loadHubData();
      setNotice(`${provider === 'google' ? 'Google' : 'GitHub'} was unlinked from this Synapse account.`);
    });
  }

  async function signOut(): Promise<void> {
    await runAction('signout', async () => {
      await signOutProfile();
      await loadHubData();
      setNotice('Signed out of the Synapse account on this host.');
    });
  }

  async function toggleFavorite(item: CatalogPreferenceItem): Promise<void> {
    await runAction(`favorite:${item.item_key}`, async () => {
      await setFavorite(item.kind as 'tool' | 'quick-action', item.item_id, !item.favorite);
      setCatalogState(await getCatalogState());
      await refreshProfile();
    });
  }

  async function reconnectService(connection: ServiceConnection): Promise<void> {
    await runAction(`service:${connection.provider}`, async () => {
      await connectService(connection.provider);
      setServices(await getServiceConnections());
      await refreshProfile();
      setNotice(`${connection.display_name} status refreshed.`);
    });
  }

  async function forgetService(connection: ServiceConnection): Promise<void> {
    await runAction(`delete-service:${connection.id}`, async () => {
      await deleteServiceConnection(connection.id);
      setServices(await getServiceConnections());
      await refreshProfile();
      setNotice(`${connection.display_name} saved status cleared.`);
    });
  }

  if (!open) return null;

  return (
    <Modal
      open={open}
      onClose={onClose}
      labelledBy='profile-hub-title'
      className={cn(
        'max-w-6xl p-0',
        mobileRoute &&
          'h-[100dvh] max-h-[100dvh] max-w-none rounded-none border-x-0 border-b-0 sm:h-auto sm:max-h-[92vh] sm:max-w-6xl sm:rounded-2xl sm:border'
      )}
    >
      <div className='flex items-center justify-between gap-3 border-b border-border/70 px-5 py-4 sm:px-6'>
        <div className='min-w-0'>
          <div className='flex items-center gap-3'>
            <div className='flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-primary/15 text-primary'>
              {profile?.avatar_url ? (
                <img src={profile.avatar_url} alt='' className='h-11 w-11 rounded-2xl object-cover' />
              ) : (
                <UserRound className='h-5 w-5' aria-hidden='true' />
              )}
            </div>
            <div className='min-w-0'>
              <p className='text-[11px] font-semibold uppercase tracking-[0.18em] text-primary/85'>
                Synapse Profile
              </p>
              <h2 id='profile-hub-title' className='truncate text-xl font-semibold tracking-tight'>
                {profile?.signed_in
                  ? profile.display_name || profile.username || profile.email || 'Synapse account'
                  : 'Synapse account, sync, and connected services'}
              </h2>
            </div>
          </div>
          <p className='mt-2 text-sm text-muted-foreground'>
            Native Synapse sign-in, cross-host setup memory, and linked services without turning
            Synapse into a cloud-only app.
          </p>
        </div>
        <div className='flex items-center gap-2'>
          {profile?.signed_in && <SyncBadge syncStatus={profile.sync_status} />}
          <Button
            variant='outline'
            size='sm'
            onClick={() => void runAction('reload', loadHubData)}
            disabled={busyKey !== null}
          >
            {busyKey === 'reload' ? <Loader2 className='h-4 w-4 animate-spin' /> : <RefreshCw className='h-4 w-4' />}
            Refresh
          </Button>
        </div>
      </div>

      {profile?.signed_in ? (
        <div className='grid gap-4 p-5 sm:grid-cols-[minmax(0,1.2fr)_minmax(0,0.8fr)] sm:p-6'>
          <div className='space-y-4'>
            <Card className='space-y-4 p-5'>
              <div className='flex flex-wrap items-start justify-between gap-4'>
                <div>
                  <div className='flex flex-wrap items-center gap-2'>
                    <h3 className='text-lg font-semibold'>Account</h3>
                    <Pill label={profile.account_provider ? `Primary: ${profile.account_provider}` : 'Native'} />
                    {profile.email_verified && <Pill label='Email ready for future verification flow' />}
                  </div>
                  <p className='mt-1 text-sm text-muted-foreground'>
                    Signed in as {profile.display_name || profile.username || profile.email} on{' '}
                    {profile.current_host.name}. Portable preferences, favorites, history, and host inventory follow you.
                  </p>
                </div>
                <Button variant='outline' onClick={() => void signOut()} disabled={busyKey === 'signout'}>
                  {busyKey === 'signout' ? <Loader2 className='h-4 w-4 animate-spin' /> : <Unplug className='h-4 w-4' />}
                  Sign out
                </Button>
              </div>

              <div className='grid gap-4 sm:grid-cols-2'>
                <div className='rounded-3xl border border-border/70 bg-secondary/20 p-4'>
                  <p className='text-xs font-semibold uppercase tracking-[0.18em] text-primary/85'>
                    Identity
                  </p>
                  <div className='mt-3 space-y-2 text-sm'>
                    <MetaRow label='Username' value={profile.username ?? 'Not set'} />
                    <MetaRow label='Email' value={profile.email ?? 'Not set'} />
                    <MetaRow label='Provider' value={profile.account_provider ?? 'native'} />
                    <MetaRow label='Sync backend' value={profile.sync_backend} />
                  </div>
                </div>

                <div className='rounded-3xl border border-border/70 bg-secondary/20 p-4'>
                  <p className='text-xs font-semibold uppercase tracking-[0.18em] text-primary/85'>
                    Sync controls
                  </p>
                  <label className='mt-3 flex items-start gap-3 rounded-2xl border border-border/60 bg-background/50 px-3 py-3 text-sm'>
                    <input
                      type='checkbox'
                      className='mt-0.5 h-4 w-4 rounded border-border'
                      checked={syncEnabled}
                      onChange={(e) => setSyncEnabled(e.target.checked)}
                    />
                    <span className='min-w-0'>
                      <span className='font-medium text-foreground'>Keep portable sync enabled</span>
                      <span className='mt-1 block text-xs text-muted-foreground'>
                        Favorites, recent tools, host memory, and UI setup follow you. Files, logs,
                        transcripts, uploads, paired devices, and local CLI sign-ins stay local.
                      </span>
                    </span>
                  </label>
                  <div className='mt-3 flex justify-end'>
                    <Button onClick={() => void saveSyncSettings()} disabled={busyKey === 'sync-settings'}>
                      {busyKey === 'sync-settings' ? <Loader2 className='h-4 w-4 animate-spin' /> : <Sparkles className='h-4 w-4' />}
                      Save sync settings
                    </Button>
                  </div>
                </div>
              </div>

              <div className='space-y-3 rounded-3xl border border-border/70 bg-secondary/20 p-4'>
                <div className='flex flex-wrap items-center justify-between gap-3'>
                  <div>
                    <h4 className='text-sm font-semibold'>Linked identities</h4>
                    <p className='mt-1 text-xs text-muted-foreground'>
                      Social identities are additive. Phone pairing remains a separate trust layer.
                    </p>
                  </div>
                </div>
                <div className='flex flex-wrap gap-2'>
                  {profile.linked_identities.map((identity) => (
                    <Pill
                      key={`${identity.provider}:${identity.identity_id ?? identity.email ?? 'linked'}`}
                      label={`${identity.provider}${identity.email ? ` · ${identity.email}` : ''}`}
                    />
                  ))}
                </div>
                <div className='flex flex-wrap gap-2'>
                  {googleAvailable && !linkedProviders.has('google') && (
                    <Button
                      variant='outline'
                      onClick={() => void beginSocial('google', 'link')}
                      disabled={busyKey === 'link:google'}
                    >
                      {busyKey === 'link:google' ? <Loader2 className='h-4 w-4 animate-spin' /> : <Link2 className='h-4 w-4' />}
                      Link Google
                    </Button>
                  )}
                  {linkedProviders.has('google') && (
                    <Button
                      variant='ghost'
                      className='text-destructive hover:bg-destructive/10'
                      onClick={() => void unlinkProvider('google')}
                      disabled={busyKey === 'unlink:google'}
                    >
                      {busyKey === 'unlink:google' ? <Loader2 className='h-4 w-4 animate-spin' /> : <Link2 className='h-4 w-4' />}
                      Unlink Google
                    </Button>
                  )}
                </div>
              </div>
            </Card>

            <Card className='space-y-4 p-5'>
              <div>
                <h3 className='text-lg font-semibold'>Connected services</h3>
                <p className='mt-1 text-sm text-muted-foreground'>
                  Portable official connections stay tied to your Synapse account. Local-detected
                  runtimes stay machine-local but Synapse remembers their last healthy host.
                </p>
              </div>
              <div className='space-y-3'>
                {services.map((connection) => (
                  <div key={connection.id} className='rounded-2xl border border-border/70 bg-secondary/20 p-4'>
                    <div className='flex flex-wrap items-start justify-between gap-3'>
                      <div>
                        <div className='flex flex-wrap items-center gap-2'>
                          <p className='text-sm font-semibold'>{connection.display_name}</p>
                          <span className={cn('rounded-full border px-2.5 py-1 text-[11px] font-medium', STATUS_TONE[connection.status] ?? STATUS_TONE.disconnected)}>
                            {connection.status}
                          </span>
                          <Pill label={connection.mode === 'portable-official' ? 'Portable official' : 'Local detected'} />
                        </div>
                        <p className='mt-2 text-sm text-muted-foreground'>
                          {String(connection.details.message ?? 'No diagnostic message yet.')}
                        </p>
                        {connection.last_verified_at && (
                          <p className='mt-1 text-xs text-muted-foreground'>
                            Last checked {formatLocal(connection.last_verified_at, 'long')}
                          </p>
                        )}
                      </div>
                      <div className='flex flex-wrap gap-2'>
                        <Button
                          variant='outline'
                          size='sm'
                          onClick={() => void reconnectService(connection)}
                          disabled={busyKey === `service:${connection.provider}`}
                        >
                          {busyKey === `service:${connection.provider}` ? <Loader2 className='h-4 w-4 animate-spin' /> : <RefreshCw className='h-4 w-4' />}
                          Verify
                        </Button>
                        {!connection.id.startsWith('account-') && (
                          <Button
                            variant='ghost'
                            size='sm'
                            onClick={() => void forgetService(connection)}
                            disabled={busyKey === `delete-service:${connection.id}`}
                          >
                            Clear saved status
                          </Button>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </Card>
          </div>

          <div className='space-y-4'>
            <Card className='space-y-4 p-5'>
              <div>
                <h3 className='text-lg font-semibold'>Favorites</h3>
                <p className='mt-1 text-sm text-muted-foreground'>
                  Favorites sync across hosts while install state stays honest per machine.
                </p>
              </div>
              {favorites.length === 0 ? (
                <EmptyBlurb label='No favorites yet' text='Star tools or quick actions in Discover and they will appear here.' />
              ) : (
                <div className='space-y-2'>
                  {favorites.map((item) => (
                    <CatalogRow
                      key={item.item_key}
                      item={item}
                      onToggleFavorite={() => void toggleFavorite(item)}
                      busy={busyKey === `favorite:${item.item_key}`}
                    />
                  ))}
                </div>
              )}
            </Card>

            <Card className='space-y-4 p-5'>
              <div>
                <h3 className='text-lg font-semibold'>Recent tools & workflows</h3>
                <p className='mt-1 text-sm text-muted-foreground'>
                  Usage memory follows you without pretending a tool is installed on every host.
                </p>
              </div>
              {recent.length === 0 ? (
                <EmptyBlurb label='No synced history yet' text='Launch a quick action, install a tool, or use a tool action and Synapse will remember it.' />
              ) : (
                <div className='space-y-2'>
                  {recent.map((item) => (
                    <CatalogRow
                      key={item.item_key}
                      item={item}
                      onToggleFavorite={() => void toggleFavorite(item)}
                      busy={busyKey === `favorite:${item.item_key}`}
                    />
                  ))}
                </div>
              )}
            </Card>

            <Card className='space-y-4 p-5'>
              <div>
                <h3 className='text-lg font-semibold'>Hosts & installs</h3>
                <p className='mt-1 text-sm text-muted-foreground'>
                  Machines that have seen this Synapse profile recently.
                </p>
              </div>
              <div className='space-y-2'>
                {hosts.map((host) => (
                  <div key={host.id} className='rounded-2xl border border-border/70 bg-secondary/20 px-4 py-3 text-sm'>
                    <div className='flex flex-wrap items-center gap-2'>
                      <p className='font-medium'>{host.name}</p>
                      {host.current_host && <Pill label='Current host' />}
                      <Pill label={host.platform} />
                    </div>
                    <p className='mt-1 text-xs text-muted-foreground'>
                      Last seen {formatLocal(host.last_seen_at, 'long')}
                    </p>
                  </div>
                ))}
              </div>
            </Card>

            <Card className='space-y-3 p-5'>
              <div>
                <h3 className='text-lg font-semibold'>Sync status</h3>
                <p className='mt-1 text-sm text-muted-foreground'>
                  Synapse keeps working offline. The account layer only adds identity and setup portability.
                </p>
              </div>
              <div className='space-y-2 text-sm'>
                <MetaRow label='Status' value={profile.sync_status} />
                <MetaRow label='Backend' value={profile.sync_backend} />
                <MetaRow label='Signed in' value='Yes' />
                <MetaRow label='Sync enabled' value={profile.sync_enabled ? 'Yes' : 'No'} />
                <MetaRow label='Last sync' value={profile.last_sync_at ? formatLocal(profile.last_sync_at, 'long') : 'Not yet'} />
              </div>
              {profile.last_sync_error && (
                <p className='rounded-2xl border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive'>
                  {profile.last_sync_error}
                </p>
              )}
            </Card>
          </div>
        </div>
      ) : (
        <div className='grid gap-4 p-5 lg:grid-cols-[minmax(0,1.05fr)_minmax(360px,0.95fr)] lg:gap-6 sm:p-6'>
          <div className='space-y-4'>
            <Card className='overflow-hidden rounded-[28px] border-border/70 bg-gradient-to-br from-card via-card to-primary/10 p-5 sm:p-6'>
              <div className='max-w-2xl space-y-4'>
                <div className='inline-flex items-center gap-2 rounded-full border border-primary/20 bg-primary/10 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-primary'>
                  <Sparkles className='h-3.5 w-3.5' />
                  Synapse Account
                </div>
                <div>
                  <h3 className='text-3xl font-semibold tracking-tight'>
                    Sign in once. Keep your Synapse setup feeling like yours on every host.
                  </h3>
                  <p className='mt-3 max-w-2xl text-sm leading-6 text-muted-foreground'>
                    Native Synapse auth is now first-class. Sign in with your own username, email,
                    and password, or continue with Google when available. Synapse stays local-first:
                    your identity and setup follow you, while sensitive machine-only state stays on that machine.
                  </p>
                </div>
                <div className='grid gap-3 sm:grid-cols-2'>
                  <AuthBenefitCard
                    icon={Star}
                    title='What syncs'
                    text='Favorites, recent tools, install memory, theme, sidebar layout, and portable service metadata.'
                  />
                  <AuthBenefitCard
                    icon={Laptop2}
                    title='What stays local'
                    text='Files, logs, transcripts, uploads, paired devices, binaries, and local CLI/browser sign-ins.'
                  />
                  <AuthBenefitCard
                    icon={Globe2}
                    title='Phone pairing stays separate'
                    text='Being signed in does not bypass pairing to a specific Synapse daemon.'
                  />
                  <AuthBenefitCard
                    icon={ShieldCheck}
                    title='Built for future recovery flows'
                    text='Email verification and password reset hooks are ready to grow in later passes.'
                  />
                </div>
              </div>
            </Card>

            <Card className='space-y-4 rounded-[28px] p-5 sm:p-6'>
              <div>
                <h4 className='text-lg font-semibold'>Why sign in?</h4>
                <p className='mt-1 text-sm text-muted-foreground'>
                  A Synapse account makes the app feel continuous across machines without turning it into a cloud drive.
                </p>
              </div>
              <div className='grid gap-3 sm:grid-cols-3'>
                <InfoPill icon={Mail} title='Identity' text='Your Synapse username, email, and linked providers travel with you.' />
                <InfoPill icon={Sparkles} title='Setup memory' text='Theme, discover state, and sidebar layout can follow you too.' />
                <InfoPill icon={LockKeyhole} title='Trust boundaries' text='Machine-local auth caches and device pairing stay device-specific.' />
              </div>
            </Card>
          </div>

          <Card className='rounded-[32px] border-border/70 p-5 sm:p-6'>
            {accountBackendReachable ? (
            <div className='space-y-4'>
              <div className='inline-flex rounded-full border border-border bg-secondary/30 p-1'>
                <button
                  type='button'
                  onClick={() => setAuthMode('signin')}
                  className={cn(
                    'rounded-full px-4 py-2 text-sm font-medium transition-colors',
                    authMode === 'signin'
                      ? 'bg-primary text-primary-foreground'
                      : 'text-muted-foreground hover:text-foreground'
                  )}
                >
                  Sign in
                </button>
                <button
                  type='button'
                  onClick={() => setAuthMode('signup')}
                  className={cn(
                    'rounded-full px-4 py-2 text-sm font-medium transition-colors',
                    authMode === 'signup'
                      ? 'bg-primary text-primary-foreground'
                      : 'text-muted-foreground hover:text-foreground'
                  )}
                >
                  Create account
                </button>
              </div>

              {authMode === 'signin' ? (
                <div className='space-y-4'>
                  <div>
                    <h4 className='text-2xl font-semibold tracking-tight'>Welcome back</h4>
                    <p className='mt-1 text-sm text-muted-foreground'>
                      Use your Synapse username or email, then pick up where you left off.
                    </p>
                  </div>

                  <label className='flex flex-col gap-1.5 text-sm'>
                    <span className='font-medium'>Username or email</span>
                    <Input
                      value={signinForm.login}
                      onChange={(e) => setSigninForm((prev) => ({ ...prev, login: e.target.value }))}
                      placeholder='justin or you@example.com'
                    />
                  </label>
                  <label className='flex flex-col gap-1.5 text-sm'>
                    <span className='font-medium'>Password</span>
                    <Input
                      type='password'
                      value={signinForm.password}
                      onChange={(e) => setSigninForm((prev) => ({ ...prev, password: e.target.value }))}
                      placeholder='At least 8 characters'
                    />
                  </label>
                  <Button
                    className='w-full rounded-2xl'
                    onClick={() => void signIn()}
                    disabled={
                      loadingHub ||
                      busyKey === 'signin' ||
                      signinForm.login.trim().length < 3 ||
                      signinForm.password.length < 8
                    }
                  >
                    {busyKey === 'signin' ? <Loader2 className='h-4 w-4 animate-spin' /> : <ShieldCheck className='h-4 w-4' />}
                    Sign in to Synapse
                  </Button>
                </div>
              ) : (
                <div className='space-y-4'>
                  <div>
                    <h4 className='text-2xl font-semibold tracking-tight'>Create your Synapse account</h4>
                    <p className='mt-1 text-sm text-muted-foreground'>
                      Your profile becomes the portable memory layer for hosts, tools, and setup.
                    </p>
                  </div>

                  <div className='grid gap-3 sm:grid-cols-2'>
                    <label className='flex flex-col gap-1.5 text-sm'>
                      <span className='font-medium'>Username</span>
                      <Input
                        value={signupForm.username}
                        onChange={(e) => setSignupForm((prev) => ({ ...prev, username: e.target.value }))}
                        placeholder='justin'
                      />
                    </label>
                    <label className='flex flex-col gap-1.5 text-sm'>
                      <span className='font-medium'>Display name</span>
                      <Input
                        value={signupForm.displayName}
                        onChange={(e) => setSignupForm((prev) => ({ ...prev, displayName: e.target.value }))}
                        placeholder='Justin Ross'
                      />
                    </label>
                  </div>
                  <label className='flex flex-col gap-1.5 text-sm'>
                    <span className='font-medium'>Email</span>
                    <Input
                      value={signupForm.email}
                      onChange={(e) => setSignupForm((prev) => ({ ...prev, email: e.target.value }))}
                      placeholder='you@example.com'
                    />
                  </label>
                  <div className='grid gap-3 sm:grid-cols-2'>
                    <label className='flex flex-col gap-1.5 text-sm'>
                      <span className='font-medium'>Password</span>
                      <Input
                        type='password'
                        value={signupForm.password}
                        onChange={(e) => setSignupForm((prev) => ({ ...prev, password: e.target.value }))}
                        placeholder='At least 8 characters'
                      />
                    </label>
                    <label className='flex flex-col gap-1.5 text-sm'>
                      <span className='font-medium'>Confirm password</span>
                      <Input
                        type='password'
                        value={signupForm.confirmPassword}
                        onChange={(e) => setSignupForm((prev) => ({ ...prev, confirmPassword: e.target.value }))}
                        placeholder='Repeat the password'
                      />
                    </label>
                  </div>
                  <Button
                    className='w-full rounded-2xl'
                    onClick={() => void signUp()}
                    disabled={loadingHub || busyKey === 'signup' || validateSignUp() !== null}
                  >
                    {busyKey === 'signup' ? <Loader2 className='h-4 w-4 animate-spin' /> : <Wand2 className='h-4 w-4' />}
                    Create Synapse account
                  </Button>
                </div>
              )}

              <div className='flex items-center gap-3 py-1 text-xs text-muted-foreground'>
                <div className='h-px flex-1 bg-border/70' />
                <span>or continue with</span>
                <div className='h-px flex-1 bg-border/70' />
              </div>

              <div className='space-y-2'>
                {googleAvailable ? (
                  <Button
                    variant='outline'
                    className='w-full rounded-2xl'
                    onClick={() => void beginSocial('google', 'signin')}
                    disabled={busyKey === 'signin:google'}
                  >
                    {busyKey === 'signin:google' ? <Loader2 className='h-4 w-4 animate-spin' /> : <Cloud className='h-4 w-4' />}
                    Continue with Google
                  </Button>
                ) : (
                  <div className='rounded-2xl border border-dashed border-border/70 bg-secondary/15 px-4 py-3 text-sm text-muted-foreground'>
                    Google sign-in is supported in this pass, but this local Synapse Accounts service is not configured for it yet.
                  </div>
                )}
              </div>

              <div className='rounded-3xl border border-border/70 bg-secondary/20 px-4 py-4 text-xs text-muted-foreground'>
                <p className='font-medium text-foreground'>What happens after you sign in?</p>
                <p className='mt-2 leading-6'>
                  Synapse can carry your favorites, recent tools, install memory, host inventory,
                  theme, and layout choices across machines. It does not upload project files, logs,
                  transcripts, uploads, paired-device trust, or local CLI/browser credentials by default.
                </p>
                <div className='mt-3 inline-flex items-center gap-2 text-primary'>
                  <ArrowRight className='h-3.5 w-3.5' />
                  Phone pairing remains separate from account identity.
                </div>
              </div>
            </div>
            ) : (
              <AccountSyncUnavailable />
            )}
          </Card>
        </div>
      )}

      {(error || profileError || notice) && (
        <div className='border-t border-border/70 px-5 py-3 sm:px-6'>
          {error && <p role='alert' className='text-sm text-destructive'>{error}</p>}
          {!error && profileError && <p role='alert' className='text-sm text-destructive'>{profileError}</p>}
          {!error && !profileError && notice && <p className='text-sm text-muted-foreground'>{notice}</p>}
        </div>
      )}
    </Modal>
  );
}

function AccountSyncUnavailable(): JSX.Element {
  return (
    <div className='space-y-4'>
      <div className='inline-flex items-center gap-2 rounded-full border border-border bg-secondary/30 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground'>
        <Cloud className='h-3.5 w-3.5' />
        Sync is optional
      </div>
      <div>
        <h4 className='text-2xl font-semibold tracking-tight'>You do not need an account</h4>
        <p className='mt-2 text-sm leading-6 text-muted-foreground'>
          Synapse works fully on this machine without signing in. A Synapse account only
          adds <span className='text-foreground'>cross-device sync</span> for favorites,
          recent tools, theme, and layout.
        </p>
      </div>
      <div className='rounded-3xl border border-dashed border-border/70 bg-secondary/15 px-4 py-4 text-sm text-muted-foreground'>
        <p className='font-medium text-foreground'>Account sync is not set up yet</p>
        <p className='mt-2 leading-6'>
          No Synapse Accounts service is reachable, so sign-in is turned off. To enable it,
          start the bundled service and press Refresh:
        </p>
        <p className='mt-3 rounded-2xl border border-border/70 bg-background/60 px-3 py-2 font-mono text-xs text-foreground'>
          python -m synapse_accounts
        </p>
        <p className='mt-2 leading-6'>
          It listens on <span className='font-mono text-foreground'>127.0.0.1:8788</span> by
          default. Point Synapse at another one with the{' '}
          <span className='font-mono text-foreground'>SYNAPSE_ACCOUNTS_BASE_URL</span>{' '}
          environment variable.
        </p>
      </div>
      <div className='inline-flex items-center gap-2 text-xs text-primary'>
        <ArrowRight className='h-3.5 w-3.5' />
        Everything else in Synapse already works without this.
      </div>
    </div>
  );
}

function SyncBadge({ syncStatus }: { syncStatus: string }): JSX.Element {
  const tone =
    syncStatus === 'connected'
      ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30'
      : syncStatus === 'error'
        ? 'bg-destructive/10 text-destructive border-destructive/30'
        : syncStatus === 'sync-disabled'
          ? 'bg-amber-500/15 text-amber-200 border-amber-500/30'
          : 'bg-sky-500/15 text-sky-200 border-sky-500/30';
  return (
    <span className={cn('rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em]', tone)}>
      {syncStatus}
    </span>
  );
}

function Pill({ label }: { label: string }): JSX.Element {
  return (
    <span className='rounded-full border border-border/70 bg-background/70 px-2.5 py-1 text-[11px] font-medium text-muted-foreground'>
      {label}
    </span>
  );
}

function EmptyBlurb({ label, text }: { label: string; text: string }): JSX.Element {
  return (
    <div className='rounded-2xl border border-dashed border-border/70 bg-secondary/10 px-4 py-6 text-center'>
      <p className='text-sm font-medium'>{label}</p>
      <p className='mt-1 text-sm text-muted-foreground'>{text}</p>
    </div>
  );
}

function CatalogRow({
  item,
  onToggleFavorite,
  busy,
}: {
  item: CatalogPreferenceItem;
  onToggleFavorite: () => void;
  busy: boolean;
}): JSX.Element {
  return (
    <div className='rounded-2xl border border-border/70 bg-secondary/20 px-4 py-3'>
      <div className='flex items-start justify-between gap-3'>
        <div className='min-w-0'>
          <div className='flex flex-wrap items-center gap-2'>
            <p className='truncate text-sm font-medium'>{item.item_id}</p>
            <Pill label={item.kind === 'tool' ? 'Tool' : 'Quick action'} />
            {item.installed_here && <Pill label='Installed here' />}
            {!item.installed_here && item.previously_installed && <Pill label='Previously installed' />}
          </div>
          <p className='mt-1 text-xs text-muted-foreground'>
            {item.last_used_at
              ? `Last used ${formatLocal(item.last_used_at, 'long')}`
              : item.last_installed_at
                ? `Last installed ${formatLocal(item.last_installed_at, 'long')}`
                : 'No recent usage timestamp yet'}
          </p>
        </div>
        <Button variant='ghost' size='sm' onClick={onToggleFavorite} disabled={busy}>
          {busy ? <Loader2 className='h-4 w-4 animate-spin' /> : <Star className={cn('h-4 w-4', item.favorite && 'fill-current text-yellow-300')} />}
          {item.favorite ? 'Unfavorite' : 'Favorite'}
        </Button>
      </div>
    </div>
  );
}

function MetaRow({ label, value }: { label: string; value: string }): JSX.Element {
  return (
    <div className='grid gap-1 sm:grid-cols-[110px_1fr] sm:gap-3'>
      <span className='text-muted-foreground'>{label}</span>
      <span className='font-mono text-foreground'>{value}</span>
    </div>
  );
}

function AuthBenefitCard({
  icon: Icon,
  title,
  text,
}: {
  icon: typeof Sparkles;
  title: string;
  text: string;
}): JSX.Element {
  return (
    <div className='rounded-3xl border border-border/60 bg-background/40 p-4'>
      <div className='flex items-center gap-2 text-sm font-semibold'>
        <Icon className='h-4 w-4 text-primary' />
        {title}
      </div>
      <p className='mt-2 text-sm text-muted-foreground'>{text}</p>
    </div>
  );
}

function InfoPill({
  icon: Icon,
  title,
  text,
}: {
  icon: typeof Sparkles;
  title: string;
  text: string;
}): JSX.Element {
  return (
    <div className='rounded-2xl border border-border/70 bg-secondary/20 px-4 py-4'>
      <div className='flex items-center gap-2 text-sm font-semibold'>
        <Icon className='h-4 w-4 text-primary' />
        {title}
      </div>
      <p className='mt-2 text-xs leading-5 text-muted-foreground'>{text}</p>
    </div>
  );
}
