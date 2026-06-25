// Left icon rail -- the primary navigation surface (Milestone F).
//
// Fixed-width vertical rail inspired by the Microsoft Store layout: a brand
// mark on top, one icon+label button per destination, a live connection dot
// at the bottom. Active page is owned by App.tsx and passed down.

import { useEffect, useState } from 'react';
import { Search, Settings as SettingsIcon, UserRound, Wifi, WifiOff } from 'lucide-react';

import { cn } from '@shared/utils';
import { useDaemon } from '@shared/daemon-context';
import {
  applySidebarLayout,
  loadSidebarLayout,
  type PageId,
} from '@shared/nav';
import { SidebarSettings } from './SidebarSettings';

export interface SidebarProps {
  active: PageId;
  onNavigate: (page: PageId) => void;
  onOpenPalette?: () => void;
  onOpenProfile?: () => void;
}

export function Sidebar({ active, onNavigate, onOpenPalette, onOpenProfile }: SidebarProps): JSX.Element {
  const { connState, profile } = useDaemon();
  const online = connState === 'open';
  const isMac = typeof navigator !== 'undefined' && /mac/i.test(navigator.platform);
  const shortcutKey = isMac ? '⌘K' : 'Ctrl+K';

  const [navItems, setNavItems] = useState(() => applySidebarLayout(loadSidebarLayout()));
  const [customizing, setCustomizing] = useState(false);
  // Re-read layout whenever the modal commits a change.
  function refreshNavItems(): void {
    setNavItems(applySidebarLayout(loadSidebarLayout()));
  }
  // Cross-tab sync: another window edits the layout -> propagate here.
  useEffect(() => {
    function onStorage(e: StorageEvent): void {
      if (e.key === 'synapse.sidebar.layout') refreshNavItems();
    }
    window.addEventListener('storage', onStorage);
    return () => window.removeEventListener('storage', onStorage);
  }, []);

  return (
    <nav
      aria-label='Primary'
      className='flex h-full w-[56px] shrink-0 flex-col items-center gap-1 border-r border-border bg-card py-4 sm:w-[84px]'
    >
      {/* Brand mark -- the Synapse disc (matches the app/taskbar icon), set on a
          subtle elevated badge so it stands out on the dark rail. */}
      <div className='mb-3 flex flex-col items-center gap-1'>
        <div className='rounded-full bg-[#0b0e1c] shadow-md ring-1 ring-white/15'>
          <svg viewBox='0 0 256 256' className='h-9 w-9 sm:h-10 sm:w-10' role='img' aria-label='Synapse'>
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

      {/* Destinations */}
      <div className='flex flex-1 flex-col items-stretch gap-1 self-stretch px-1.5 sm:px-2'>
        {navItems.map((item) => {
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
              {/* Hide the label on the collapsed rail; visible md+. */}
              <span className='sr-only sm:not-sr-only'>{item.label}</span>
            </button>
          );
        })}
      </div>

      {/* Command palette shortcut hint */}
      {onOpenPalette && (
        <button
          type='button'
          onClick={onOpenPalette}
          title={`Open the command palette (${shortcutKey})`}
          className='mt-2 flex flex-col items-center gap-0.5 rounded-md px-1 py-1.5 text-[10px] text-muted-foreground transition-colors hover:bg-accent/50 hover:text-foreground'
        >
          <Search className='h-4 w-4' aria-hidden='true' />
          <span className='sr-only font-mono sm:not-sr-only'>{shortcutKey}</span>
        </button>
      )}

      {onOpenProfile && (
        <button
          type='button'
          onClick={onOpenProfile}
          title={profile?.signed_in ? `Profile: ${profile.display_name || profile.email || 'Synapse account'}` : 'Open profile hub'}
          className='mt-1 flex flex-col items-center gap-0.5 rounded-md px-1 py-1.5 text-[10px] text-muted-foreground transition-colors hover:bg-accent/50 hover:text-foreground'
        >
          <div className='relative'>
            {profile?.avatar_url ? (
              <img
                src={profile.avatar_url}
                alt=''
                className='h-5 w-5 rounded-full object-cover'
              />
            ) : (
              <UserRound className='h-4 w-4' aria-hidden='true' />
            )}
            <span
              className={cn(
                'absolute -bottom-0.5 -right-0.5 h-2.5 w-2.5 rounded-full border border-card',
                profile?.sync_status === 'connected'
                  ? 'bg-emerald-400'
                  : profile?.signed_in
                    ? 'bg-sky-400'
                    : 'bg-muted'
              )}
            />
          </div>
          <span className='sr-only sm:not-sr-only'>Profile</span>
        </button>
      )}

      {/* Customize sidebar trigger (v0.1.36 A6) */}
      <button
        type='button'
        onClick={() => setCustomizing(true)}
        title='Customize sidebar (reorder + hide tabs)'
        aria-label='Customize sidebar'
        className='mt-1 flex flex-col items-center gap-0.5 rounded-md px-1 py-1.5 text-[10px] text-muted-foreground transition-colors hover:bg-accent/50 hover:text-foreground'
      >
        <SettingsIcon className='h-4 w-4' aria-hidden='true' />
        <span className='sr-only sm:not-sr-only'>Customize</span>
      </button>
      <SidebarSettings
        open={customizing}
        onClose={() => setCustomizing(false)}
        onChange={refreshNavItems}
      />

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
