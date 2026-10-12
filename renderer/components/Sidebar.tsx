import { useEffect, useMemo, useState } from 'react';
import { Search, Wifi, WifiOff } from 'lucide-react';
import { SynapseMark } from './SynapseMark';

import type { InstalledPageView } from '@shared/installed-pages-client';
import { useDaemon } from '@shared/daemon-context';
import {
  buildDesktopSidebarSections,
  loadSidebarLayout,
  routeMatches,
  type AppRoute,
} from '@shared/nav';
import { cn } from '@shared/utils';
import { useReviewCount } from '@shared/use-review-count';

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
  const reviewCount = useReviewCount();
  const isMac = typeof navigator !== 'undefined' && /mac/i.test(navigator.platform);
  const shortcutKey = isMac ? 'âŒ˜K' : 'Ctrl+K';

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
      className='synapse-sidebar flex h-full w-[210px] shrink-0 flex-col border-r border-border bg-card px-3 py-4'
    >
      <div className='synapse-sidebar-brand'><SynapseMark size={42} /><div><strong>SYNAPSE</strong><span>Your Mind. Amplified.</span></div></div>

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
                const showReviewBadge =
                  item.route.kind === 'core' && item.route.page === 'ai-coding' && reviewCount > 0;
                return (
                  <button
                    key={item.route.kind === 'core' ? item.route.page : item.route.id}
                    type='button'
                    title={
                      showReviewBadge
                        ? `${item.description} â€” ${reviewCount} need review`
                        : item.description
                    }
                    aria-current={isActive ? 'page' : undefined}
                    onClick={() => onNavigate(item.route)}
                    className={cn(
                      'group relative flex items-center gap-3 rounded-xl px-3 py-2.5 text-[12px] font-medium transition-colors',
                      'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                      isActive
                        ? 'bg-accent text-foreground'
                        : 'text-muted-foreground hover:bg-accent/50 hover:text-foreground'
                    )}
                  >
                    {showReviewBadge && (
                      <span
                        aria-label={`${reviewCount} item${reviewCount === 1 ? '' : 's'} need review`}
                        className='absolute right-1 top-1 min-w-[16px] rounded-full bg-primary px-1 text-center text-[9px] font-semibold leading-4 text-primary-foreground'
                      >
                        {reviewCount > 99 ? '99+' : reviewCount}
                      </span>
                    )}
                    <Icon
                      className={cn('h-5 w-5', isActive ? 'text-primary' : 'text-current')}
                      aria-hidden='true'
                    />
                    <span className='text-left leading-tight'>{item.label}</span>
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
