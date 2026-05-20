// Left icon rail -- the primary navigation surface (Milestone F).
//
// Fixed-width vertical rail inspired by the Microsoft Store layout: a brand
// mark on top, one icon+label button per destination, a live connection dot
// at the bottom. Active page is owned by App.tsx and passed down.

import { Search, Wifi, WifiOff } from 'lucide-react';

import { cn } from '@shared/utils';
import { useDaemon } from '@shared/daemon-context';
import { NAV_ITEMS, type PageId } from '@shared/nav';

export interface SidebarProps {
  active: PageId;
  onNavigate: (page: PageId) => void;
  onOpenPalette?: () => void;
}

export function Sidebar({ active, onNavigate, onOpenPalette }: SidebarProps): JSX.Element {
  const { connState } = useDaemon();
  const online = connState === 'open';
  const isMac = typeof navigator !== 'undefined' && /mac/i.test(navigator.platform);
  const shortcutKey = isMac ? '⌘K' : 'Ctrl+K';

  return (
    <nav
      aria-label='Primary'
      className='flex h-full w-[84px] shrink-0 flex-col items-center gap-1 border-r border-border bg-card py-4'
    >
      {/* Brand mark */}
      <div className='mb-3 flex flex-col items-center gap-1'>
        <div className='flex h-10 w-10 items-center justify-center rounded-lg bg-primary text-lg font-bold text-primary-foreground'>
          S
        </div>
      </div>

      {/* Destinations */}
      <div className='flex flex-1 flex-col items-stretch gap-1 self-stretch px-2'>
        {NAV_ITEMS.map((item) => {
          const Icon = item.icon;
          const isActive = item.id === active;
          return (
            <button
              key={item.id}
              type='button'
              title={item.description}
              aria-current={isActive ? 'page' : undefined}
              onClick={() => onNavigate(item.id)}
              className={cn(
                'group flex flex-col items-center gap-1 rounded-md py-2 text-[11px] font-medium transition-colors',
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
              {item.label}
            </button>
          );
        })}
      </div>

      {/* Command palette shortcut hint */}
      {onOpenPalette && (
        <button
          type='button'
          onClick={onOpenPalette}
          title='Open the command palette'
          className='mt-2 flex flex-col items-center gap-0.5 rounded-md px-1 py-1.5 text-[10px] text-muted-foreground transition-colors hover:bg-accent/50 hover:text-foreground'
        >
          <Search className='h-4 w-4' aria-hidden='true' />
          <span className='font-mono'>{shortcutKey}</span>
        </button>
      )}

      {/* Connection indicator */}
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
