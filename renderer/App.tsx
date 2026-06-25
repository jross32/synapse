// Synapse app shell (Milestone F) -- icon-rail sidebar + the active page.
//
// The whole tree sits under <DaemonProvider> so every page shares one
// daemon connection. "Routing" is just an activePage enum -- no URL router.

import { useEffect, useRef, useState } from 'react';

import { DaemonProvider, useDaemon } from '@shared/daemon-context';
import {
  bootstrapRuntimeAuth,
  clearDeviceToken,
  forgetDeviceToken,
  getStoredDeviceIdentity,
  isMobileRoute,
  tryResumeDeviceSession,
  type RuntimeAuthMode,
} from '@shared/browser-runtime';
import { DEFAULT_PAGE, NAV_ITEMS, type PageId } from '@shared/nav';
import { applyPortablePreferences, isProfilePreferencesEmpty, readLocalPortablePreferences } from '@shared/profile-preferences';
import { updateProfilePreferences } from '@shared/profile-client';
import { applyTheme, getStoredTheme, watchOsTheme } from '@shared/theme';
import { cn } from '@shared/utils';
import { Sidebar } from './components/Sidebar';
import { CaptureButton } from './components/CaptureButton';
import { CommandPalette } from './components/CommandPalette';
import { MobilePairingScreen } from './components/MobilePairingScreen';
import { ProfileHub } from './components/ProfileHub';
import { ShortcutsHelp } from './components/ShortcutsHelp';
import { HomePage } from './pages/Home';
import { AppsPage } from './pages/Apps';
import { ToolsPage } from './pages/Tools';
import { SessionsPage } from './pages/Sessions';
import { ProcessesPage } from './pages/Processes';
import { AssistantPage } from './pages/Assistant';
import { ReviewPage } from './pages/Review';
import { MarketplacePage } from './pages/Marketplace';
import { SettingsPage } from './pages/Settings';

export default function App(): JSX.Element {
  // Apply the stored theme as early as possible to avoid a flash of dark
  // when the user is on light. Also re-apply if the OS preference flips
  // while we're in 'system' mode (Contract #14).
  const mobileRoute = isMobileRoute();
  const [authMode, setAuthMode] = useState<RuntimeAuthMode | 'booting'>('booting');
  // Guards the unauthorized handler so a burst of 401s can't re-enter it.
  const handlingUnauthorized = useRef(false);

  useEffect(() => {
    applyTheme(getStoredTheme());
    return watchOsTheme(() => {
      if (getStoredTheme() === 'system') applyTheme('system');
    });
  }, []);

  useEffect(() => {
    let cancelled = false;
    void bootstrapRuntimeAuth()
      .then((mode) => {
        if (!cancelled) setAuthMode(mode);
      })
      .catch(() => {
        if (!cancelled) setAuthMode(mobileRoute ? 'pair-required' : 'local');
      });
    return () => {
      cancelled = true;
    };
  }, [mobileRoute]);

  useEffect(() => {
    function onUnauthorized(): void {
      if (!mobileRoute) return;
      if (handlingUnauthorized.current) return;
      handlingUnauthorized.current = true;
      void (async () => {
        try {
          clearDeviceToken();
          if (await tryResumeDeviceSession()) {
            setAuthMode('paired-device');
            return;
          }
          setAuthMode(getStoredDeviceIdentity() ? 'reconnect-required' : 'pair-required');
        } finally {
          handlingUnauthorized.current = false;
        }
      })();
    }
    window.addEventListener('synapse:unauthorized', onUnauthorized);
    return () => window.removeEventListener('synapse:unauthorized', onUnauthorized);
  }, [mobileRoute]);

  if (authMode === 'booting') return <BootSplash />;
  if (mobileRoute && authMode !== 'paired-device' && authMode !== 'local') {
    return (
      <MobilePairingScreen
        mode={authMode}
        onPaired={() => setAuthMode('paired-device')}
        onRequireFullReset={() => {
          forgetDeviceToken();
          setAuthMode('pair-required');
        }}
      />
    );
  }

  return (
    <DaemonProvider>
      <PortablePreferencesBridge />
      <Shell
        mobileRoute={mobileRoute}
        onForgetDevice={() => {
          forgetDeviceToken();
          setAuthMode('pair-required');
        }}
      />
    </DaemonProvider>
  );
}

function PortablePreferencesBridge(): null {
  const { profile, refreshProfile } = useDaemon();
  const seededSignatureRef = useRef<string | null>(null);
  const appliedSignatureRef = useRef<string | null>(null);

  useEffect(() => {
    function onPortablePreferences(event: Event): void {
      const detail = (event as CustomEvent<Record<string, unknown>>).detail;
      if (!detail || typeof detail !== 'object') return;
      void updateProfilePreferences(detail).catch(() => undefined);
    }
    window.addEventListener('synapse:portable-preferences', onPortablePreferences);
    return () => window.removeEventListener('synapse:portable-preferences', onPortablePreferences);
  }, []);

  useEffect(() => {
    if (!profile) return;
    if (isProfilePreferencesEmpty(profile.preferences)) {
      const local = readLocalPortablePreferences();
      if (isProfilePreferencesEmpty(local)) return;
      const signature = JSON.stringify(local);
      if (seededSignatureRef.current === signature) return;
      seededSignatureRef.current = signature;
      void updateProfilePreferences(local)
        .then(() => refreshProfile())
        .catch(() => undefined);
      return;
    }
    const signature = JSON.stringify(profile.preferences);
    if (appliedSignatureRef.current === signature) return;
    appliedSignatureRef.current = signature;
    applyPortablePreferences(profile.preferences);
  }, [profile, refreshProfile]);

  return null;
}

function BootSplash(): JSX.Element {
  return (
    <div className='flex min-h-screen items-center justify-center bg-background text-foreground'>
      <div className='flex flex-col items-center gap-5 text-center'>
        <svg viewBox='0 0 120 120' className='synapse-art h-28 w-28' role='img' aria-label='Synapse'>
          <circle className='glow' cx='60' cy='60' r='34' fill='hsl(var(--primary))' opacity='0.25' />
          <g
            className='flow'
            stroke='hsl(var(--primary))'
            strokeWidth='1.6'
            strokeLinecap='round'
            fill='none'
            opacity='0.65'
            strokeDasharray='4 5'
          >
            <line x1='60' y1='60' x2='30' y2='30' />
            <line x1='60' y1='60' x2='92' y2='28' />
            <line x1='60' y1='60' x2='98' y2='66' />
            <line x1='60' y1='60' x2='72' y2='98' />
            <line x1='60' y1='60' x2='28' y2='86' />
            <line x1='60' y1='60' x2='22' y2='54' />
          </g>
          <g className='nodes' fill='hsl(var(--primary))'>
            <circle cx='60' cy='60' r='7' />
            <circle cx='30' cy='30' r='4' />
            <circle cx='92' cy='28' r='4' />
            <circle cx='98' cy='66' r='4' />
            <circle cx='72' cy='98' r='4' />
            <circle cx='28' cy='86' r='4' />
            <circle cx='22' cy='54' r='4' />
          </g>
        </svg>
        <div>
          <h1 className='text-2xl font-semibold tracking-tight'>Synapse</h1>
          <p className='text-sm text-muted-foreground'>Preparing the app shell…</p>
        </div>
      </div>
    </div>
  );
}

interface ShellProps {
  mobileRoute: boolean;
  onForgetDevice: () => void;
}

function Shell({ mobileRoute, onForgetDevice }: ShellProps): JSX.Element {
  const [page, setPage] = useState<PageId>(DEFAULT_PAGE);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const [shortcutsOpen, setShortcutsOpen] = useState(false);
  const [toolsIntent, setToolsIntent] = useState<{
    tab?: 'installed' | 'discover';
    focusId?: string;
    nonce: number;
  } | null>(null);
  // Set by ToolCard "Open in Sessions" → SessionsPage reads it on mount and
  // auto-attaches a tab so the user doesn't have to know the session id.
  const [pendingSession, setPendingSession] = useState<string | null>(null);

  // Global Ctrl+K / Cmd+K — the universal command palette (Contract #21).
  // Global `?` — the keyboard shortcuts help modal. We skip the binding
  // when the event target is an input / textarea / contenteditable so a
  // user typing "?" into the palette filter doesn't trigger it.
  useEffect(() => {
    function isTypingTarget(target: EventTarget | null): boolean {
      if (!(target instanceof HTMLElement)) return false;
      const tag = target.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA') return true;
      if (target.isContentEditable) return true;
      return false;
    }
    function onKey(e: KeyboardEvent): void {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setPaletteOpen((open) => !open);
        return;
      }
      if (
        e.key === '?' &&
        !e.ctrlKey &&
        !e.metaKey &&
        !e.altKey &&
        !isTypingTarget(e.target)
      ) {
        e.preventDefault();
        setShortcutsOpen((open) => !open);
      }
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  // ToolCard fires `synapse:open-session` when a `pty.spawn` action lands a
  // session id. We catch it here -- ToolCard never has to know which page
  // owns the terminal UI.
  useEffect(() => {
    function onOpenSession(event: Event): void {
      const detail = (event as CustomEvent<{ sessionId?: string }>).detail;
      if (typeof detail?.sessionId !== 'string' || !detail.sessionId) return;
      setPendingSession(detail.sessionId);
      setPage('sessions');
    }
    window.addEventListener('synapse:open-session', onOpenSession);
    return () => window.removeEventListener('synapse:open-session', onOpenSession);
  }, []);

  // Generic page-navigation event (v0.1.36) -- any deep surface can
  // fire it to jump to another page without holding a ref to setPage.
  // Today: NetworkPanel "Install Cloudtap" CTA fires this with
  // { page: 'tools', tab: 'discover', focusId: 'cloudtap' }.
  useEffect(() => {
    function onNavigate(event: Event): void {
      const detail = (event as CustomEvent<{
        page?: PageId;
        tab?: 'installed' | 'discover';
        focusId?: string;
      }>).detail;
      if (!detail?.page) return;
      const allowed = NAV_ITEMS.find((n) => n.id === detail.page);
      if (!allowed) return;
      setPage(detail.page);
      if (detail.page === 'tools') {
        setToolsIntent({
          tab: detail.tab,
          focusId: detail.focusId,
          nonce: Date.now(),
        });
      }
    }
    window.addEventListener('synapse:navigate', onNavigate);
    return () => window.removeEventListener('synapse:navigate', onNavigate);
  }, []);

  const activeNav = NAV_ITEMS.find((item) => item.id === page) ?? NAV_ITEMS[0];

  return (
    <div className='flex h-screen w-screen overflow-hidden bg-background text-foreground'>
      {!mobileRoute && (
        <Sidebar
          active={page}
          onNavigate={setPage}
          onOpenPalette={() => setPaletteOpen(true)}
          onOpenProfile={() => setProfileOpen(true)}
        />
      )}
      <div className='flex min-w-0 flex-1 flex-col'>
        {mobileRoute && (
          <header className='border-b border-border bg-card/95 backdrop-blur'>
            <div className='mx-auto flex max-w-[1400px] items-center justify-between gap-3 px-4 pb-3 pt-4'>
              <div className='flex min-w-0 items-center gap-3'>
                <div className='flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-primary/15 text-base font-semibold text-primary'>
                  S
                </div>
                <div className='min-w-0'>
                  <p className='text-[11px] font-semibold uppercase tracking-[0.22em] text-primary/90'>
                    Synapse Mobile
                  </p>
                  <h1 className='truncate text-lg font-semibold tracking-tight'>
                    {activeNav.label}
                  </h1>
                </div>
              </div>
              <div className='flex items-center gap-2'>
                <button
                  type='button'
                  onClick={() => setPaletteOpen(true)}
                  className='rounded-full border border-border bg-secondary px-3 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground'
                >
                  Search
                </button>
                <button
                  type='button'
                  onClick={() => setProfileOpen(true)}
                  className='rounded-full border border-border bg-secondary px-3 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground'
                >
                  Profile
                </button>
              </div>
            </div>
          </header>
        )}
        <main className='flex-1 overflow-y-auto'>
          <div
            className={cn(
              'mx-auto max-w-[1400px] p-4 sm:p-6 lg:p-8',
              mobileRoute && 'pb-44'
            )}
          >
            {page === 'home' && <HomePage onNavigate={setPage} />}
            {page === 'apps' && <AppsPage />}
            {page === 'tools' && <ToolsPage intent={toolsIntent} />}
            {page === 'sessions' && (
              <SessionsPage
                initialSessionId={pendingSession}
                onConsumedInitial={() => setPendingSession(null)}
              />
            )}
            {page === 'assistant' && <AssistantPage />}
            {page === 'review' && <ReviewPage />}
            {page === 'marketplace' && <MarketplacePage />}
            {page === 'processes' && <ProcessesPage />}
            {page === 'settings' && (
              <SettingsPage mobileRoute={mobileRoute} onForgetDevice={onForgetDevice} />
            )}
          </div>
        </main>
        {mobileRoute && (
          <nav className='border-t border-border bg-card/95 backdrop-blur'>
            <div className='mx-auto max-w-[1400px] px-3 pb-[calc(0.9rem+env(safe-area-inset-bottom))] pt-3'>
              <div className='grid grid-cols-3 gap-2'>
              {NAV_ITEMS.map((item) => {
                const Icon = item.icon;
                const active = item.id === page;
                return (
                  <button
                    key={item.id}
                    type='button'
                    onClick={() => setPage(item.id)}
                    className={cn(
                      'flex min-h-[68px] w-full flex-col items-center justify-center gap-1 rounded-2xl border px-3 py-2 text-[11px] font-medium transition-colors',
                      active
                        ? 'border-primary/35 bg-accent text-foreground'
                        : 'border-transparent text-muted-foreground hover:bg-accent/60 hover:text-foreground'
                    )}
                    aria-current={active ? 'page' : undefined}
                  >
                    <Icon
                      className={cn('h-4 w-4', active ? 'text-primary' : 'text-current')}
                      aria-hidden='true'
                    />
                    <span>{item.label}</span>
                  </button>
                );
              })}
              </div>
            </div>
          </nav>
        )}
      </div>
      <CommandPalette
        open={paletteOpen}
        onClose={() => setPaletteOpen(false)}
        onNavigate={(p) => setPage(p)}
        onOpenProfile={() => setProfileOpen(true)}
      />
      <ProfileHub open={profileOpen} onClose={() => setProfileOpen(false)} mobileRoute={mobileRoute} />
      <ShortcutsHelp open={shortcutsOpen} onClose={() => setShortcutsOpen(false)} />
      <CaptureButton />
    </div>
  );
}
