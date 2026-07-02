// Synapse app shell -- grouped hubs, installed pages, and responsive desktop/mobile nav.

import { useEffect, useMemo, useRef, useState } from 'react';
import { ChevronUp } from 'lucide-react';

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
import {
  listInstalledPages,
  type InstalledPageView,
} from '@shared/installed-pages-client';
import {
  DEFAULT_ROUTE,
  MOBILE_NAV_ORDER,
  coreNavItem,
  routeIcon,
  routeLabel,
  type AiCodingSection,
  type AppRoute,
  type AppsSection,
  type MarketplaceSection,
  type NavigationIntent,
  type ToolsSection,
  type ToolsTab,
} from '@shared/nav';
import {
  applyPortablePreferences,
  isProfilePreferencesEmpty,
  readLocalPortablePreferences,
} from '@shared/profile-preferences';
import { updateProfilePreferences } from '@shared/profile-client';
import { applyTheme, getStoredTheme, watchOsTheme } from '@shared/theme';
import { cn } from '@shared/utils';
import { CaptureButton } from './components/CaptureButton';
import { CommandPalette } from './components/CommandPalette';
import { MobilePairingScreen } from './components/MobilePairingScreen';
import { ProfileHub } from './components/ProfileHub';
import { ShortcutsHelp } from './components/ShortcutsHelp';
import { Sidebar } from './components/Sidebar';
import { SidebarSettings } from './components/SidebarSettings';
import { HomePage } from './pages/Home';
import { AppsPage } from './pages/Apps';
import { ToolsPage } from './pages/Tools';
import { AiCodingPage } from './pages/AiCoding';
import { AiFactoryPage } from './pages/AiFactory';
import { WhatsnewPage } from './pages/Whatsnew';
import { SettingsPage } from './pages/Settings';
import { WebScraperPage } from './pages/WebScraper';

export default function App(): JSX.Element {
  const mobileRoute = isMobileRoute();
  const [authMode, setAuthMode] = useState<RuntimeAuthMode | 'booting'>('booting');
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
    return () =>
      window.removeEventListener('synapse:portable-preferences', onPortablePreferences);
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
          <circle className='glow' cx='60' cy='60' r='52' fill='#7c3aed' opacity='0.18' />
          <circle cx='60' cy='60' r='60' fill='#0b0e1c' />
          <circle cx='60' cy='60' r='43' fill='none' stroke='#7c3aed' strokeWidth='11' />
          <circle cx='60' cy='60' r='16' fill='#eef2fb' />
          <g className='nodes' fill='#22d3a6'>
            <circle cx='60' cy='17' r='5.5' />
            <circle cx='97.2' cy='38.5' r='5.5' />
            <circle cx='97.2' cy='81.5' r='5.5' />
            <circle cx='60' cy='103' r='5.5' />
            <circle cx='22.8' cy='81.5' r='5.5' />
            <circle cx='22.8' cy='38.5' r='5.5' />
          </g>
        </svg>
        <div>
          <h1 className='text-2xl font-semibold tracking-tight'>Synapse</h1>
          <p className='text-sm text-muted-foreground'>Preparing the app shell...</p>
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
  const { recentEvents } = useDaemon();
  const [route, setRoute] = useState<AppRoute>(DEFAULT_ROUTE);
  const [appsSection, setAppsSection] = useState<AppsSection>('projects');
  const [toolsSection, setToolsSection] = useState<ToolsSection>('tools');
  const [toolsTab, setToolsTab] = useState<ToolsTab>('installed');
  const [marketplaceSection, setMarketplaceSection] =
    useState<MarketplaceSection>('tools');
  const [aiCodingSection, setAiCodingSection] =
    useState<AiCodingSection>('sessions');
  const [toolsIntentNonce, setToolsIntentNonce] = useState(0);
  const [toolsFocusId, setToolsFocusId] = useState<string | undefined>(undefined);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const [shortcutsOpen, setShortcutsOpen] = useState(false);
  const [sidebarSettingsOpen, setSidebarSettingsOpen] = useState(false);
  const [pendingSession, setPendingSession] = useState<string | null>(null);
  const [installedPages, setInstalledPages] = useState<InstalledPageView[]>([]);
  const seenMcpEventId = useRef(0);
  const [navCollapsed, setNavCollapsed] = useState(() => {
    // Default to COLLAPSED on mobile so the nav never eats half the screen --
    // only stay expanded if the user explicitly opened it before.
    if (typeof localStorage === 'undefined') return true;
    return localStorage.getItem('synapse:mobile-nav-collapsed') !== '0';
  });

  async function refreshInstalledPages(): Promise<void> {
    try {
      const response = await listInstalledPages();
      setInstalledPages(response.pages);
    } catch {
      /* keep the shell usable even if this optional surface fails */
    }
  }

  useEffect(() => {
    seenMcpEventId.current = recentEvents.reduce((max, event) => Math.max(max, event.id), 0);
    void refreshInstalledPages();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const fresh = recentEvents.filter(
      (event) =>
        event.id > seenMcpEventId.current && event.name.startsWith('v1.mcp_server.')
    );
    if (fresh.length === 0) return;
    seenMcpEventId.current = recentEvents.reduce(
      (max, event) => Math.max(max, event.id),
      seenMcpEventId.current
    );
    void refreshInstalledPages();
  }, [recentEvents]);

  useEffect(() => {
    if (route.kind !== 'installed') return;
    if (installedPages.some((page) => page.id === route.id)) return;
    navigate({ page: 'tools', section: 'installed-pages' });
  }, [installedPages, route]);

  useEffect(() => {
    try {
      localStorage.setItem('synapse:mobile-nav-collapsed', navCollapsed ? '1' : '0');
    } catch {
      /* storage unavailable -- non-fatal */
    }
  }, [navCollapsed]);

  function navigate(intent: NavigationIntent): void {
    if (intent.page === 'home') {
      setRoute({ kind: 'core', page: 'home' });
      return;
    }
    if (intent.page === 'ai-factory') {
      setRoute({ kind: 'core', page: 'ai-factory' });
      return;
    }
    if (intent.page === 'settings') {
      setRoute({ kind: 'core', page: 'settings' });
      return;
    }
    if (intent.page === 'whatsnew') {
      setRoute({ kind: 'core', page: 'whatsnew' });
      return;
    }
    if (intent.page === 'apps') {
      setAppsSection(intent.section ?? 'projects');
      setRoute({ kind: 'core', page: 'apps' });
      return;
    }
    if (intent.page === 'tools') {
      setToolsSection(intent.section ?? 'tools');
      if (intent.toolsTab) setToolsTab(intent.toolsTab);
      if (intent.marketplaceSection) setMarketplaceSection(intent.marketplaceSection);
      if (intent.focusToolId) {
        setToolsFocusId(intent.focusToolId);
        setToolsIntentNonce(Date.now());
      }
      setRoute({ kind: 'core', page: 'tools' });
      return;
    }
    if (intent.page === 'ai-coding') {
      setAiCodingSection(intent.section ?? 'sessions');
      setRoute({ kind: 'core', page: 'ai-coding' });
      return;
    }
    if (intent.page === 'installed') {
      setRoute({ kind: 'installed', id: intent.installedPageId });
    }
  }

  function navigateRoute(nextRoute: AppRoute): void {
    if (nextRoute.kind === 'core') {
      setRoute(nextRoute);
      return;
    }
    setRoute(nextRoute);
  }

  useEffect(() => {
    function isTypingTarget(target: EventTarget | null): boolean {
      if (!(target instanceof HTMLElement)) return false;
      const tag = target.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA') return true;
      if (target.isContentEditable) return true;
      return false;
    }
    function onKey(event: KeyboardEvent): void {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        setPaletteOpen((open) => !open);
        return;
      }
      if (
        event.key === '?' &&
        !event.ctrlKey &&
        !event.metaKey &&
        !event.altKey &&
        !isTypingTarget(event.target)
      ) {
        event.preventDefault();
        setShortcutsOpen((open) => !open);
      }
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  useEffect(() => {
    function onOpenSession(event: Event): void {
      const detail = (event as CustomEvent<{ sessionId?: string }>).detail;
      if (typeof detail?.sessionId !== 'string' || !detail.sessionId) return;
      setPendingSession(detail.sessionId);
      navigate({ page: 'ai-coding', section: 'sessions' });
    }
    window.addEventListener('synapse:open-session', onOpenSession);
    return () => window.removeEventListener('synapse:open-session', onOpenSession);
  }, []);

  useEffect(() => {
    function onNavigate(event: Event): void {
      const detail = (event as CustomEvent<NavigationIntent>).detail;
      if (!detail || typeof detail !== 'object' || !('page' in detail)) return;
      navigate(detail);
    }
    window.addEventListener('synapse:navigate', onNavigate);
    return () => window.removeEventListener('synapse:navigate', onNavigate);
  }, []);

  const activeLabel = routeLabel(route, installedPages);
  const ActiveNavIcon = routeIcon(route, installedPages);
  const mobileItems = MOBILE_NAV_ORDER.map((id) => coreNavItem(id));
  const toolsIntent = useMemo(
    () => ({
      section: toolsSection,
      tab: toolsTab,
      focusId: toolsFocusId,
      marketplaceSection,
      nonce: toolsIntentNonce,
    }),
    [marketplaceSection, toolsFocusId, toolsIntentNonce, toolsSection, toolsTab]
  );

  return (
    <div className='flex h-screen w-screen overflow-hidden bg-background text-foreground'>
      {!mobileRoute && (
        <Sidebar
          active={route}
          installedPages={installedPages}
          onNavigate={navigateRoute}
          onOpenPalette={() => setPaletteOpen(true)}
        />
      )}

      <div className='flex min-w-0 flex-1 flex-col'>
        {mobileRoute && (
          <header className='border-b border-border bg-card/95 backdrop-blur'>
            <div className='mx-auto flex max-w-[1400px] items-center justify-between gap-3 px-4 pb-3 pt-4'>
              <div className='flex min-w-0 items-center gap-3'>
                <div className='flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-[#0b0e1c] shadow-md ring-1 ring-white/15'>
                  <svg viewBox='0 0 256 256' className='h-7 w-7' role='img' aria-label='Synapse'>
                    <circle cx='128' cy='128' r='128' fill='#0b0e1c' />
                    <circle cx='128' cy='128' r='90' fill='none' stroke='#7c3aed' strokeWidth='28' />
                    <circle cx='128' cy='128' r='34' fill='#eef2fb' />
                    <g fill='#22d3a6'>
                      <circle cx='128' cy='38' r='13' />
                      <circle cx='206' cy='83' r='13' />
                      <circle cx='206' cy='173' r='13' />
                      <circle cx='128' cy='218' r='13' />
                      <circle cx='50' cy='173' r='13' />
                      <circle cx='50' cy='83' r='13' />
                    </g>
                  </svg>
                </div>
                <div className='min-w-0'>
                  <p className='text-[11px] font-semibold uppercase tracking-[0.22em] text-primary/90'>
                    Synapse Mobile
                  </p>
                  <h1 className='truncate text-lg font-semibold tracking-tight'>{activeLabel}</h1>
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
            {route.kind === 'core' && route.page === 'home' && (
              <HomePage onNavigate={navigate} />
            )}
            {route.kind === 'core' && route.page === 'apps' && (
              <AppsPage initialSection={appsSection} />
            )}
            {route.kind === 'core' && route.page === 'tools' && (
              <ToolsPage
                intent={toolsIntent}
                installedPages={installedPages}
                onOpenInstalledPage={(id) =>
                  navigate({ page: 'installed', installedPageId: id })
                }
              />
            )}
            {route.kind === 'core' && route.page === 'ai-coding' && (
              <AiCodingPage
                initialSection={aiCodingSection}
                pendingSessionId={pendingSession}
                onConsumedPendingSession={() => setPendingSession(null)}
              />
            )}
            {route.kind === 'core' && route.page === 'ai-factory' && <AiFactoryPage />}
            {route.kind === 'core' && route.page === 'whatsnew' && <WhatsnewPage />}
            {route.kind === 'core' && route.page === 'settings' && (
              <SettingsPage
                mobileRoute={mobileRoute}
                onForgetDevice={onForgetDevice}
                onOpenProfile={() => setProfileOpen(true)}
                onOpenSidebarSettings={() => setSidebarSettingsOpen(true)}
                onOpenWhatsNew={() => navigate({ page: 'whatsnew' })}
              />
            )}
            {route.kind === 'installed' && route.id === 'web-scraper' && <WebScraperPage />}
          </div>
        </main>

        {mobileRoute && (
          <nav className='border-t border-border bg-card/95 backdrop-blur'>
            <div className='mx-auto max-w-[1400px] px-3 pb-[calc(0.55rem+env(safe-area-inset-bottom))] pt-1'>
              <button
                type='button'
                onClick={() => setNavCollapsed((value) => !value)}
                aria-label={navCollapsed ? 'Show tabs' : 'Hide tabs'}
                aria-expanded={!navCollapsed}
                className='mx-auto flex w-20 items-center justify-center py-2'
              >
                <span className='h-1.5 w-10 rounded-full bg-muted-foreground/40' />
              </button>
              {navCollapsed ? (
                <button
                  type='button'
                  onClick={() => setNavCollapsed(false)}
                  className='flex w-full items-center justify-center gap-2 rounded-2xl border border-primary/35 bg-accent px-3 py-2.5 text-sm font-medium text-foreground'
                >
                  <ActiveNavIcon className='h-4 w-4 text-primary' aria-hidden='true' />
                  <span>{activeLabel}</span>
                  <ChevronUp className='h-4 w-4 text-muted-foreground' aria-hidden='true' />
                </button>
              ) : (
                <div className='grid grid-cols-3 gap-2 motion-safe:animate-in motion-safe:slide-in-from-bottom-2'>
                  {mobileItems.map((item) => {
                    const Icon = item.icon;
                    const active =
                      route.kind === 'core' && route.page === item.id;
                    return (
                      <button
                        key={item.id}
                        type='button'
                        onClick={() => {
                          navigateRoute({ kind: 'core', page: item.id });
                          setNavCollapsed(true);
                        }}
                        className={cn(
                          'flex min-h-[64px] w-full flex-col items-center justify-center gap-1 rounded-2xl border px-3 py-2 text-[11px] font-medium transition-colors',
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
              )}
            </div>
          </nav>
        )}
      </div>

      <CommandPalette
        open={paletteOpen}
        onClose={() => setPaletteOpen(false)}
        onNavigate={navigate}
        onOpenProfile={() => setProfileOpen(true)}
      />
      <ProfileHub
        open={profileOpen}
        onClose={() => setProfileOpen(false)}
        mobileRoute={mobileRoute}
      />
      <SidebarSettings
        open={sidebarSettingsOpen}
        onClose={() => setSidebarSettingsOpen(false)}
        installedPages={installedPages}
      />
      <ShortcutsHelp open={shortcutsOpen} onClose={() => setShortcutsOpen(false)} />
      <CaptureButton />
    </div>
  );
}
