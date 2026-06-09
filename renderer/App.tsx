// Synapse app shell (Milestone F) -- icon-rail sidebar + the active page.
//
// The whole tree sits under <DaemonProvider> so every page shares one
// daemon connection. "Routing" is just an activePage enum -- no URL router.

import { useEffect, useState } from 'react';

import { DaemonProvider } from '@shared/daemon-context';
import { DEFAULT_PAGE, type PageId } from '@shared/nav';
import { applyTheme, getStoredTheme, watchOsTheme } from '@shared/theme';
import { Sidebar } from './components/Sidebar';
import { CommandPalette } from './components/CommandPalette';
import { HomePage } from './pages/Home';
import { AppsPage } from './pages/Apps';
import { ToolsPage } from './pages/Tools';
import { SessionsPage } from './pages/Sessions';
import { ProcessesPage } from './pages/Processes';
import { SettingsPage } from './pages/Settings';

export default function App(): JSX.Element {
  // Apply the stored theme as early as possible to avoid a flash of dark
  // when the user is on light. Also re-apply if the OS preference flips
  // while we're in 'system' mode (Contract #14).
  useEffect(() => {
    applyTheme(getStoredTheme());
    return watchOsTheme(() => {
      if (getStoredTheme() === 'system') applyTheme('system');
    });
  }, []);

  return (
    <DaemonProvider>
      <Shell />
    </DaemonProvider>
  );
}

function Shell(): JSX.Element {
  const [page, setPage] = useState<PageId>(DEFAULT_PAGE);
  const [paletteOpen, setPaletteOpen] = useState(false);

  // Global Ctrl+K / Cmd+K — the universal command palette (Contract #21).
  useEffect(() => {
    function onKey(e: KeyboardEvent): void {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setPaletteOpen((open) => !open);
      }
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  return (
    <div className='flex h-screen w-screen overflow-hidden bg-background text-foreground'>
      <Sidebar active={page} onNavigate={setPage} onOpenPalette={() => setPaletteOpen(true)} />
      <main className='flex-1 overflow-y-auto'>
        <div className='mx-auto max-w-[1400px] p-4 sm:p-6 lg:p-8'>
          {page === 'home' && <HomePage onNavigate={setPage} />}
          {page === 'apps' && <AppsPage />}
          {page === 'tools' && <ToolsPage />}
          {page === 'sessions' && <SessionsPage />}
          {page === 'processes' && <ProcessesPage />}
          {page === 'settings' && <SettingsPage />}
        </div>
      </main>
      <CommandPalette
        open={paletteOpen}
        onClose={() => setPaletteOpen(false)}
        onNavigate={(p) => setPage(p)}
      />
    </div>
  );
}
