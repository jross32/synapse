import { useEffect, useMemo, useState } from 'react';
import { Search, Wifi, WifiOff } from 'lucide-react';

import type { InstalledPageView } from '@shared/installed-pages-client';
import { useDaemon } from '@shared/daemon-context';
import {
  buildDesktopSidebarSections,
  loadSidebarLayout,
  routeMatches,
  type AppRoute,
} from '@shared/nav';
import { cn } from '@shared/utils';

export interface SidebarProps {
  active: AppRoute;
  installedPages: InstalledPageView[];
  onNavigate: (route: AppRoute) => void;
  onOpenPalette?: () => void;
}

export function Sidebar({
  active,
  installedPages,
  onNavigate,
  onOpenPalette,
}: SidebarProps): JSX.Element {
  const { connState } = useDaemon();
  const online = connState === 'open';
  const isMac = typeof navigator !== 'undefined' && /mac/i.test(navigator.platform);
  const shortcutKey = isMac ? '⌘K' : 'Ctrl+K';

  const installedIds = useMemo(
    () => installedPages.map((page) => page.id),
    [installedPages]
  );
  const [layoutVersion, setLayoutVersion] = useState(0);

  useEffect(() => {
    function refresh(): void {
      setLayoutVersion((version) => version + 1);
    }
    function onStorage(e: StorageEvent): void {
      if (e.key === 'synapse.sidebar.layout') refresh();
    }
    window.addEventListener('storage', onStorage);
    window.addEventListener('synapse:sidebar-layout-changed', refresh as EventListener);
    return () => {
      window.removeEventListener('storage', onStorage);
      window.removeEventListener('synapse:sidebar-layout-changed', refresh as EventListener);
    };
  }, []);

  const sections = useMemo(() => {
    const layout = loadSidebarLayout(installedIds);
    return buildDesktopSidebarSections(layout, installedPages);
  }, [installedIds, installedPages, layoutVersion]);

  return (
    <nav
      aria-label='Primary'
      className='flex h-full w-[104px] shrink-0 flex-col border-r border-border bg-card px-2 py-4'
    >
      <div className='mb-4 flex items-center justify-center'>
        <div className='rounded-full bg-[#0b0e1c] shadow-md ring-1 ring-white/15'>
          <svg viewBox='0 0 256 256' className='h-10 w-10' role='img' aria-label='Synapse'>
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
      </div>

      <div className='flex flex-1 flex-col gap-4 overflow-y-auto'>
        {sections.map((section) => (
          <div key={section.id} className='flex flex-col gap-1'>
            <p className='px-2 text-[10px] font-semibold uppercase tracking-[0.22em] text-muted-foreground'>
              {section.label}
            </p>
            <div className='flex flex-col gap-1'>
              {section.items.map((item) => {
                const Icon = item.icon;
                const isActive = routeMatches(item.route, active);
                return (
                  <button
                    key={item.route.kind === 'core' ? item.route.page : item.route.id}
                    type='button'
                    title={item.description}
                    aria-current={isActive ? 'page' : undefined}
                    onClick={() => onNavigate(item.route)}
                    className={cn(
                      'group flex flex-col items-center gap-1 rounded-xl px-2 py-2 text-[11px] font-medium transition-colors',
                      'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                      isActive
                        ? 'bg-accent text-foreground'
                        : 'text-muted-foreground hover:bg-accent/50 hover:text-foreground'
                    )}
                  >
                    <Icon
                      className={cn('h-5 w-5', isActive ? 'text-primary' : 'text-current')}
                      aria-hidden='true'
                    />
                    <span className='text-center leading-tight'>{item.label}</span>
                  </button>
                );
              })}
            </div>
          </div>
        ))}
      </div>

      {onOpenPalette && (
        <button
          type='button'
          onClick={onOpenPalette}
          title={`Open the command palette (${shortcutKey})`}
          className='mt-3 flex flex-col items-center gap-0.5 rounded-xl px-2 py-2 text-[10px] text-muted-foreground transition-colors hover:bg-accent/50 hover:text-foreground'
        >
          <Search className='h-4 w-4' aria-hidden='true' />
          <span className='font-mono'>{shortcutKey}</span>
        </button>
      )}

      <div
        title={online ? 'Connected to daemon' : `Daemon: ${connState}`}
        className='mt-2 flex flex-col items-center gap-1 text-[10px] text-muted-foreground'
      >
        {online ? (
          <Wifi className='h-4 w-4 text-status-launched' aria-hidden='true' />
        ) : (
          <WifiOff className='h-4 w-4 text-status-error' aria-hidden='true' />
        )}
        <span className='sr-only'>Daemon {connState}</span>
      </div>
    </nav>
  );
}
