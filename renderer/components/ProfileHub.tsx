import { useEffect, useMemo, useState } from 'react';
import {
  CheckCircle2,
  Cloud,
  GitBranch,
  Loader2,
  RefreshCw,
  ShieldCheck,
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
  getProfileHosts,
  getServiceConnections,
  setFavorite,
  signInProfile,
  signOutProfile,
  signUpProfile,
  startProfileAuth,
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

interface ConfigFormState {
  supabaseUrl: string;
  supabaseAnonKey: string;
  syncEnabled: boolean;
}

interface AuthFormState {
  email: string;
  password: string;
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
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [configForm, setConfigForm] = useState<ConfigFormState>({
    supabaseUrl: '',
    supabaseAnonKey: '',
    syncEnabled: true,
  });
  const [authForm, setAuthForm] = useState<AuthFormState>({
    email: '',
    password: '',
    displayName: '',
  });

  useEffect(() => {
    if (!open) return;
    setConfigForm({
      supabaseUrl: profile?.supabase_url ?? '',
      supabaseAnonKey: '',
      syncEnabled: profile?.sync_enabled ?? true,
    });
  }, [open, profile?.supabase_url, profile?.sync_enabled]);

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

  async function loadHubData(): Promise<void> {
    setError(null);
    const [profileRes, catalogRes, servicesRes, hostsRes] = await Promise.allSettled([
      refreshProfile(),
      getCatalogState(),
      getServiceConnections(),
      getProfileHosts(),
    ]);

    if (catalogRes.status === 'fulfilled') setCatalogState(catalogRes.value);
    if (servicesRes.status === 'fulfilled') setServices(servicesRes.value);
    if (hostsRes.status === 'fulfilled') setHosts(hostsRes.value);

    const issues: string[] = [];
    if (profileRes.status === 'rejected') issues.push((profileRes.reason as Error).message);
    if (catalogRes.status === 'rejected') issues.push((catalogRes.reason as Error).message);
    if (servicesRes.status === 'rejected') issues.push((servicesRes.reason as Error).message);
    if (hostsRes.status === 'rejected') issues.push((hostsRes.reason as Error).message);
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

  async function saveConfig(): Promise<void> {
    await runAction('save-config', async () => {
      await updateProfileConfig({
        supabase_url: configForm.supabaseUrl || null,
        supabase_anon_key: configForm.supabaseAnonKey || null,
        sync_enabled: configForm.syncEnabled,
      });
      await loadHubData();
      setNotice('Profile cloud settings updated.');
      setConfigForm((prev) => ({ ...prev, supabaseAnonKey: '' }));
    });
  }

  async function signIn(): Promise<void> {
    await runAction('signin', async () => {
      await signInProfile({
        email: authForm.email,
        password: authForm.password,
      });
      await loadHubData();
      setNotice('Signed into your Synapse account.');
      setAuthForm((prev) => ({ ...prev, password: '' }));
    });
  }

  async function signUp(): Promise<void> {
    await runAction('signup', async () => {
      const res = await signUpProfile({
        email: authForm.email,
        password: authForm.password,
        display_name: authForm.displayName || null,
      });
      await loadHubData();
      setNotice(res.notice ?? 'Synapse account created and connected.');
      setAuthForm((prev) => ({ ...prev, password: '' }));
    });
  }

  async function beginSocial(provider: 'google' | 'github'): Promise<void> {
    await runAction(`social:${provider}`, async () => {
      const res = await startProfileAuth(provider);
      await openExternal(res.url);
      setNotice(
        `Finish ${provider === 'google' ? 'Google' : 'GitHub'} sign-in in the browser tab that just opened.`
      );
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
        'max-w-5xl p-0',
        mobileRoute &&
          'h-[100dvh] max-h-[100dvh] max-w-none rounded-none border-x-0 border-b-0 sm:h-auto sm:max-h-[92vh] sm:max-w-5xl sm:rounded-2xl sm:border'
      )}
    >
      <div className='flex items-center justify-between gap-3 border-b border-border/70 px-5 py-4 sm:px-6'>
        <div className='min-w-0'>
          <div className='flex items-center gap-3'>
            <div className='flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-primary/15 text-primary'>
              {profile?.avatar_url ? (
                <img
                  src={profile.avatar_url}
                  alt=''
                  className='h-11 w-11 rounded-2xl object-cover'
                />
              ) : (
                <UserRound className='h-5 w-5' aria-hidden='true' />
              )}
            </div>
            <div className='min-w-0'>
              <p className='text-[11px] font-semibold uppercase tracking-[0.18em] text-primary/85'>
                Synapse profile
              </p>
              <h2 id='profile-hub-title' className='truncate text-xl font-semibold tracking-tight'>
                {profile?.display_name || profile?.email || 'Account, sync, and connected services'}
              </h2>
            </div>
          </div>
          <p className='mt-2 text-sm text-muted-foreground'>
            Optional cloud identity, host-aware favorites/history, and service readiness without
            turning Synapse into a cloud-only app.
          </p>
        </div>
        <Button
          variant='outline'
          size='sm'
          onClick={() => void runAction('reload', loadHubData)}
          disabled={busyKey !== null}
        >
          {busyKey === 'reload' ? (
            <Loader2 className='h-4 w-4 animate-spin' />
          ) : (
            <RefreshCw className='h-4 w-4' />
          )}
          Refresh
        </Button>
      </div>

      <div className='grid gap-4 p-5 sm:grid-cols-[minmax(0,1.2fr)_minmax(0,0.8fr)] sm:p-6'>
        <div className='space-y-4'>
          <Card className='space-y-4 p-5'>
            <div className='flex items-start justify-between gap-3'>
              <div>
                <h3 className='text-lg font-semibold'>Account</h3>
                <p className='mt-1 text-sm text-muted-foreground'>
                  Connect an optional Synapse account through Supabase to carry your profile,
                  favorites, recent tools, and host inventory across machines.
                </p>
              </div>
              <SyncBadge syncStatus={profile?.sync_status ?? 'config-required'} />
            </div>

            <div className='grid gap-3 sm:grid-cols-2'>
              <label className='flex flex-col gap-1.5 text-sm'>
                <span className='font-medium'>Supabase URL</span>
                <Input
                  value={configForm.supabaseUrl}
                  onChange={(e) => setConfigForm((prev) => ({ ...prev, supabaseUrl: e.target.value }))}
                  placeholder='https://your-project.supabase.co'
                />
              </label>
              <label className='flex flex-col gap-1.5 text-sm'>
                <span className='font-medium'>Anon key</span>
                <Input
                  value={configForm.supabaseAnonKey}
                  onChange={(e) => setConfigForm((prev) => ({ ...prev, supabaseAnonKey: e.target.value }))}
                  placeholder={profile?.has_anon_key ? 'Already configured locally' : 'Paste the Supabase anon key'}
                />
              </label>
            </div>

            <label className='flex items-center gap-2 text-sm text-muted-foreground'>
              <input
                type='checkbox'
                className='h-4 w-4 rounded border-border'
                checked={configForm.syncEnabled}
                onChange={(e) => setConfigForm((prev) => ({ ...prev, syncEnabled: e.target.checked }))}
              />
              Keep sync enabled when signed in.
            </label>

            <div className='flex flex-wrap gap-2'>
              <Button onClick={() => void saveConfig()} disabled={busyKey === 'save-config'}>
                {busyKey === 'save-config' ? <Loader2 className='h-4 w-4 animate-spin' /> : <Cloud className='h-4 w-4' />}
                Save cloud settings
              </Button>
              {profile?.signed_in && (
                <Button variant='outline' onClick={() => void signOut()} disabled={busyKey === 'signout'}>
                  {busyKey === 'signout' ? <Loader2 className='h-4 w-4 animate-spin' /> : <Unplug className='h-4 w-4' />}
                  Sign out
                </Button>
              )}
            </div>

            {profile?.signed_in ? (
              <div className='rounded-2xl border border-border/70 bg-secondary/20 p-4 text-sm'>
                <div className='flex items-center gap-2 font-medium text-foreground'>
                  <CheckCircle2 className='h-4 w-4 text-emerald-300' />
                  Signed in
                </div>
                <p className='mt-2 text-muted-foreground'>
                  {profile.display_name || profile.email} on {profile.current_host.name}
                </p>
                <div className='mt-3 flex flex-wrap gap-2 text-xs text-muted-foreground'>
                  {profile.provider && <Pill label={`Primary: ${profile.provider}`} />}
                  {profile.provider_identities.map((identity) => (
                    <Pill key={`${identity.provider}:${identity.identity_id ?? identity.email ?? 'id'}`} label={`${identity.provider}${identity.email ? ` · ${identity.email}` : ''}`} />
                  ))}
                </div>
              </div>
            ) : (
              <div className='space-y-3 rounded-2xl border border-border/70 bg-secondary/20 p-4'>
                <div className='grid gap-3 sm:grid-cols-2'>
                  <label className='flex flex-col gap-1.5 text-sm'>
                    <span className='font-medium'>Email</span>
                    <Input
                      value={authForm.email}
                      onChange={(e) => setAuthForm((prev) => ({ ...prev, email: e.target.value }))}
                      placeholder='you@example.com'
                    />
                  </label>
                  <label className='flex flex-col gap-1.5 text-sm'>
                    <span className='font-medium'>Password</span>
                    <Input
                      type='password'
                      value={authForm.password}
                      onChange={(e) => setAuthForm((prev) => ({ ...prev, password: e.target.value }))}
                      placeholder='At least 6 characters'
                    />
                  </label>
                </div>
                <label className='flex flex-col gap-1.5 text-sm'>
                  <span className='font-medium'>Display name for sign-up</span>
                  <Input
                    value={authForm.displayName}
                    onChange={(e) => setAuthForm((prev) => ({ ...prev, displayName: e.target.value }))}
                    placeholder='Justin Ross'
                  />
                </label>
                <div className='flex flex-wrap gap-2'>
                  <Button onClick={() => void signIn()} disabled={busyKey === 'signin' || !profile?.config_ready}>
                    {busyKey === 'signin' ? <Loader2 className='h-4 w-4 animate-spin' /> : <ShieldCheck className='h-4 w-4' />}
                    Sign in
                  </Button>
                  <Button variant='outline' onClick={() => void signUp()} disabled={busyKey === 'signup' || !profile?.config_ready}>
                    {busyKey === 'signup' ? <Loader2 className='h-4 w-4 animate-spin' /> : <Wand2 className='h-4 w-4' />}
                    Create account
                  </Button>
                </div>
                <div className='flex flex-wrap gap-2 border-t border-border/70 pt-3'>
                  <Button variant='outline' onClick={() => void beginSocial('google')} disabled={!profile?.config_ready || busyKey === 'social:google'}>
                    {busyKey === 'social:google' ? <Loader2 className='h-4 w-4 animate-spin' /> : <Cloud className='h-4 w-4' />}
                    Continue with Google
                  </Button>
                  <Button variant='outline' onClick={() => void beginSocial('github')} disabled={!profile?.config_ready || busyKey === 'social:github'}>
                    {busyKey === 'social:github' ? <Loader2 className='h-4 w-4 animate-spin' /> : <GitBranch className='h-4 w-4' />}
                    Continue with GitHub
                  </Button>
                </div>
              </div>
            )}
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
                <div
                  key={connection.id}
                  className='rounded-2xl border border-border/70 bg-secondary/20 p-4'
                >
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
                        {busyKey === `service:${connection.provider}` ? (
                          <Loader2 className='h-4 w-4 animate-spin' />
                        ) : (
                          <RefreshCw className='h-4 w-4' />
                        )}
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
                Favorites and usage history stay local-first, then sync when your account is connected.
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
                Synced usage is host-aware, so you can see what you used before without pretending it is installed here.
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
                Which computers have seen this Synapse profile recently, and which one you are on now.
              </p>
            </div>
            <div className='space-y-2'>
              {hosts.map((host) => (
                <div
                  key={host.id}
                  className='rounded-2xl border border-border/70 bg-secondary/20 px-4 py-3 text-sm'
                >
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
                Synapse should keep working offline. Cloud sync is an overlay, not a requirement.
              </p>
            </div>
            <div className='space-y-2 text-sm'>
              <MetaRow label='Status' value={profile?.sync_status ?? 'unknown'} />
              <MetaRow label='Signed in' value={profile?.signed_in ? 'Yes' : 'No'} />
              <MetaRow label='Sync enabled' value={profile?.sync_enabled ? 'Yes' : 'No'} />
              <MetaRow
                label='Last sync'
                value={profile?.last_sync_at ? formatLocal(profile.last_sync_at, 'long') : 'Not yet'}
              />
            </div>
            {profile?.last_sync_error && (
              <p className='rounded-2xl border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive'>
                {profile.last_sync_error}
              </p>
            )}
          </Card>
        </div>
      </div>

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

function SyncBadge({ syncStatus }: { syncStatus: string }): JSX.Element {
  const tone =
    syncStatus === 'connected'
      ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30'
      : syncStatus === 'error'
        ? 'bg-destructive/10 text-destructive border-destructive/30'
        : syncStatus === 'local-only'
          ? 'bg-sky-500/15 text-sky-200 border-sky-500/30'
          : 'bg-secondary text-muted-foreground border-border/70';
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
          {busy ? (
            <Loader2 className='h-4 w-4 animate-spin' />
          ) : (
            <Star className={cn('h-4 w-4', item.favorite && 'fill-current text-yellow-300')} />
          )}
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
