// Synapse app shell (Milestone F) -- icon-rail sidebar + the active page.
//
// The whole tree sits under <DaemonProvider> so every page shares one
// daemon connection. "Routing" is just an activePage enum -- no URL router.

import { useState } from 'react';

import { DaemonProvider } from '@shared/daemon-context';
import { DEFAULT_PAGE, type PageId } from '@shared/nav';
import { Sidebar } from './components/Sidebar';
import { HomePage } from './pages/Home';
import { AppsPage } from './pages/Apps';
import { ToolsPage } from './pages/Tools';
import { ProcessesPage } from './pages/Processes';
import { SettingsPage } from './pages/Settings';

export default function App(): JSX.Element {
  return (
    <DaemonProvider>
      <Shell />
    </DaemonProvider>
  );
}

function Shell(): JSX.Element {
  const [page, setPage] = useState<PageId>(DEFAULT_PAGE);

  return (
    <div className='flex h-screen w-screen overflow-hidden bg-background text-foreground'>
      <Sidebar active={page} onNavigate={setPage} />
      <main className='flex-1 overflow-y-auto'>
        <div className='mx-auto max-w-[1400px] p-8'>
          {page === 'home' && <HomePage onNavigate={setPage} />}
          {page === 'apps' && <AppsPage />}
          {page === 'tools' && <ToolsPage />}
          {page === 'processes' && <ProcessesPage />}
          {page === 'settings' && <SettingsPage />}
        </div>
      </main>
    </div>
  );
}
