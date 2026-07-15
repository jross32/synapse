import { useEffect, useMemo, useRef, useState } from 'react';
import {
  BookOpen,
  ExternalLink,
  Loader2,
  Server,
  Store,
  Wrench,
} from 'lucide-react';

import type {
  CatalogPreferenceItem,
  CatalogPreferenceState,
  ToolEntry,
} from '@shared/generated-types';
import type { InstalledPageView } from '@shared/installed-pages-client';
import {
  loadSidebarLayout,
  saveSidebarLayout,
  type MarketplaceSection,
  type ToolsSection,
  type ToolsTab,
} from '@shared/nav';
import { listTools } from '@shared/tools-client';
import { useDaemon } from '@shared/daemon-context';
import { getCatalogState } from '@shared/profile-client';
import { cn } from '@shared/utils';
import { Card } from '../components/ui/card';
import { MarketplaceBrowser } from '../components/MarketplaceBrowser';
import { McpServerBrowser } from '../components/McpServerBrowser';
import { PageHeader } from '../components/PageHeader';
import { ToolCard } from '../components/ToolCard';
import { MarketplacePage, type MarketplacePageSection } from './Marketplace';

type ToolsHubSection = ToolsSection;

export interface ToolsPageProps {
  intent?: {
    section?: ToolsHubSection;
    tab?: ToolsTab;
    focusId?: string;
    marketplaceSection?: MarketplaceSection;
    nonce: number;
  } | null;
  installedPages: InstalledPageView[];
  onOpenInstalledPage?: (id: string) => void;
}

export function ToolsPage({
  intent,
  installedPages,
  onOpenInstalledPage,
}: ToolsPageProps): JSX.Element {
  const { recentEvents } = useDaemon();
  const [section, setSection] = useState<ToolsHubSection>('tools');
  const [tab, setTab] = useState<ToolsTab>('installed');
  const [marketplaceSection, setMarketplaceSection] =
    useState<MarketplacePageSection>('tools');
  const [tools, setTools] = useState<ToolEntry[] | null>(null);
  const [catalogState, setCatalogState] = useState<CatalogPreferenceState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [layoutVersion, setLayoutVersion] = useState(0);
  const seenEventId = useRef(0);
  const seenMcpEventId = useRef(0);

  function refresh(): void {
    setError(null);
    void Promise.allSettled([listTools(), getCatalogState()]).then(([toolsRes, catalogRes]) => {
      if (toolsRes.status === 'fulfilled') {
        setTools(toolsRes.value);
      } else {
        setError(
          toolsRes.reason instanceof Error ? toolsRes.reason.message : 'Failed to load tools'
        );
      }
      if (catalogRes.status === 'fulfilled') {
        setCatalogState(catalogRes.value);
      }
    });
  }

  useEffect(() => {
    seenEventId.current = recentEvents.reduce((m, e) => Math.max(m, e.id), 0);
    seenMcpEventId.current = seenEventId.current;
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const fresh = recentEvents.filter(
      (e) => e.id > seenEventId.current && e.name.startsWith('v1.tool.')
    );
    if (fresh.length === 0) return;
    seenEventId.current = recentEvents.reduce(
      (m, e) => Math.max(m, e.id),
      seenEventId.current
    );
    refresh();
  }, [recentEvents]);

  useEffect(() => {
    const shouldRefreshCatalog = recentEvents.some(
      (e) =>
        e.name === 'v1.profile.updated' ||
        e.name === 'v1.profile.sync.updated' ||
        e.name === 'v1.service_connection.updated'
    );
    if (!shouldRefreshCatalog) return;
    void getCatalogState().then(setCatalogState).catch(() => undefined);
  }, [recentEvents]);

  useEffect(() => {
    const fresh = recentEvents.filter(
      (e) => e.id > seenMcpEventId.current && e.name.startsWith('v1.mcp_server.')
    );
    if (fresh.length === 0) return;
    seenMcpEventId.current = recentEvents.reduce(
      (m, e) => Math.max(m, e.id),
      seenMcpEventId.current
    );
    setLayoutVersion((value) => value + 1);
  }, [recentEvents]);

  useEffect(() => {
    function refreshLayout(): void {
      setLayoutVersion((value) => value + 1);
    }
    window.addEventListener(
      'synapse:sidebar-layout-changed',
      refreshLayout as EventListener
    );
    return () =>
      window.removeEventListener(
        'synapse:sidebar-layout-changed',
        refreshLayout as EventListener
      );
  }, []);

  useEffect(() => {
    if (!intent) return;
    if (intent.section) setSection(intent.section);
    if (intent.tab) setTab(intent.tab);
    if (intent.marketplaceSection) {
      setMarketplaceSection(intent.marketplaceSection as MarketplacePageSection);
    }
  }, [intent]);

  function handleChanged(updated: ToolEntry): void {
    setTools((prev) =>
      prev ? prev.map((tool) => (tool.manifest.id === updated.manifest.id ? updated : tool)) : prev
    );
  }

  const toolPreferences = new Map(
    (catalogState?.items ?? [])
      .filter((item) => item.kind === 'tool')
      .map((item) => [item.item_id, item])
  );
  const sortedTools = [...(tools ?? [])].sort((left, right) =>
    compareToolEntries(left, right, toolPreferences)
  );
  const installedPageIds = installedPages.map((page) => page.id);
  const sidebarLayout = useMemo(
    () => loadSidebarLayout(installedPageIds),
    [installedPageIds, layoutVersion]
  );

  function toggleInstalledPage(id: string): void {
    const current = loadSidebarLayout(installedPageIds);
    const visible = new Set(current.visible_installed_pages);
    const order = [...current.installed_page_order];
    if (visible.has(id)) visible.delete(id);
    else {
      visible.add(id);
      if (!order.includes(id)) order.push(id);
    }
    saveSidebarLayout({
      ...current,
      installed_page_order: order,
      visible_installed_pages: [...visible],
    });
  }

  return (
    <div className='flex flex-col gap-6'>
      <PageHeader
        title='My Tools'
        subtitle='Your tools, installable marketplace surfaces, MCP servers, and dedicated installed pages.'
      />

      <div
        role='tablist'
        aria-label='My Tools sections'
        className='flex flex-wrap gap-1 rounded-lg border border-border bg-secondary/30 p-1'
      >
        <TopTab
          active={section === 'tools'}
          onClick={() => setSection('tools')}
          icon={Wrench}
          label='Tools'
        />
        <TopTab
          active={section === 'marketplace'}
          onClick={() => setSection('marketplace')}
          icon={Store}
          label='Marketplace'
        />
        <TopTab
          active={section === 'mcp'}
          onClick={() => setSection('mcp')}
          icon={Server}
          label='MCP Servers'
        />
        <TopTab
          active={section === 'installed-pages'}
          onClick={() => setSection('installed-pages')}
          icon={BookOpen}
          label='Installed Pages'
        />
      </div>

      {section === 'tools' && (
        <>
          <div
            role='tablist'
            aria-label='Tools view'
            className='flex flex-wrap gap-1 rounded-lg border border-border bg-secondary/30 p-1'
          >
            <TopTab
              active={tab === 'installed'}
              onClick={() => setTab('installed')}
              icon={Wrench}
              label='Installed'
            />
            <TopTab
              active={tab === 'discover'}
              onClick={() => setTab('discover')}
              icon={Store}
              label='Discover'
            />
          </div>

          {tab === 'installed' && (
            <>
              {error && (
                <p role='alert' className='text-sm text-destructive'>
                  {error}
                </p>
              )}

              {tools === null && !error && (
                <Card className='flex items-center justify-center gap-2 p-12 text-sm text-muted-foreground'>
                  <Loader2 className='h-4 w-4 animate-spin' /> Loading tools...
                </Card>
              )}

              {tools !== null && tools.length === 0 && (
                <Card className='flex flex-col items-center gap-3 border-dashed p-12 text-center'>
                  <div className='flex h-12 w-12 items-center justify-center rounded-lg bg-secondary'>
                    <Wrench className='h-6 w-6 text-primary' />
                  </div>
                  <h3 className='text-lg font-semibold'>No tools loaded</h3>
                  <p className='max-w-md text-sm text-muted-foreground'>
                    Browse the catalogue, or drop a manifest into{' '}
                    <code className='font-mono'>tools/</code> directly. Hot reload picks
                    it up live.
                  </p>
                </Card>
              )}

              {tools !== null && tools.length > 0 && (
                <div className='grid grid-cols-[repeat(auto-fill,minmax(min(100%,340px),1fr))] gap-6'>
                  {sortedTools.map((entry) => (
                    <ToolCard
                      key={entry.manifest.id}
                      entry={entry}
                      onChanged={handleChanged}
                      catalogState={toolPreferences.get(entry.manifest.id) ?? null}
                    />
                  ))}
                </div>
              )}
            </>
          )}

          {tab === 'discover' && (
            <MarketplaceBrowser
              onManageInstalledTool={() => setTab('installed')}
              focusToolId={intent?.focusId ?? null}
              focusNonce={intent?.nonce ?? 0}
            />
          )}
        </>
      )}

      {section === 'marketplace' && (
        <MarketplacePage
          headerless
          initialSection={marketplaceSection}
          allowedSections={['tools', 'bundles', 'models', 'workers', 'squads']}
        />
      )}

      {section === 'mcp' && <McpServerBrowser />}

      {section === 'installed-pages' && (
        <InstalledPagesPanel
          pages={installedPages}
          visibleIds={new Set(sidebarLayout.visible_installed_pages)}
          onToggle={toggleInstalledPage}
          onOpenPage={onOpenInstalledPage}
        />
      )}
    </div>
  );
}

function compareToolEntries(
  left: ToolEntry,
  right: ToolEntry,
  preferences: Map<string, CatalogPreferenceItem>
): number {
  const leftPref = preferences.get(left.manifest.id);
  const rightPref = preferences.get(right.manifest.id);
  if (Boolean(leftPref?.favorite) !== Boolean(rightPref?.favorite)) {
    return leftPref?.favorite ? -1 : 1;
  }
  const leftStamp = leftPref?.last_used_at ?? leftPref?.updated_at ?? '';
  const rightStamp = rightPref?.last_used_at ?? rightPref?.updated_at ?? '';
  if (leftStamp !== rightStamp) return rightStamp.localeCompare(leftStamp);
  return left.manifest.name.localeCompare(right.manifest.name);
}

function TopTab({
  active,
  onClick,
  icon: Icon,
  label,
}: {
  active: boolean;
  onClick: () => void;
  icon: typeof Wrench;
  label: string;
}): JSX.Element {
  return (
    <button
      type='button'
      role='tab'
      aria-selected={active}
      onClick={onClick}
      className={cn(
        'flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors',
        active
          ? 'bg-card text-foreground shadow-sm'
          : 'text-muted-foreground hover:text-foreground'
      )}
    >
      <Icon className='h-4 w-4' />
      {label}
    </button>
  );
}

function InstalledPagesPanel({
  pages,
  visibleIds,
  onToggle,
  onOpenPage,
}: {
  pages: InstalledPageView[];
  visibleIds: Set<string>;
  onToggle: (id: string) => void;
  onOpenPage?: (id: string) => void;
}): JSX.Element {
  if (pages.length === 0) {
    return (
      <Card className='flex flex-col gap-3 border-dashed p-10 text-center'>
        <div className='mx-auto flex h-12 w-12 items-center justify-center rounded-lg bg-secondary'>
          <BookOpen className='h-6 w-6 text-primary' />
        </div>
        <h3 className='text-lg font-semibold'>No dedicated pages available yet</h3>
        <p className='mx-auto max-w-lg text-sm text-muted-foreground'>
          Eligible installed integrations show up here once Synapse can recognize
          them. The first curated page is Web Scraper.
        </p>
      </Card>
    );
  }

  return (
    <div className='grid grid-cols-1 gap-4 xl:grid-cols-2'>
      {pages.map((page) => {
        const shown = visibleIds.has(page.id);
        return (
          <Card key={page.id} className='flex flex-col gap-4 p-5'>
            <div className='flex items-start justify-between gap-3'>
              <div>
                <div className='flex items-center gap-2'>
                  <BookOpen className='h-4 w-4 text-primary' />
                  <h3 className='text-base font-semibold'>{page.label}</h3>
                  <StatusPill status={page.status} />
                </div>
                <p className='mt-1 text-sm text-muted-foreground'>{page.description}</p>
                {page.detail && (
                  <p className='mt-2 text-xs text-muted-foreground'>{page.detail}</p>
                )}
              </div>
            </div>

            <div className='flex flex-wrap gap-2'>
              <button
                type='button'
                onClick={() => onToggle(page.id)}
                className={cn(
                  'rounded-md border px-3 py-1.5 text-sm font-medium transition-colors',
                  shown
                    ? 'border-primary/40 text-primary'
                    : 'border-border text-muted-foreground hover:text-foreground'
                )}
              >
                {shown ? 'Shown in sidebar' : 'Show in sidebar'}
              </button>
              {onOpenPage && (
                <button
                  type='button'
                  onClick={() => onOpenPage(page.id)}
                  className='inline-flex items-center gap-1 rounded-md border border-border px-3 py-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground'
                >
                  <ExternalLink className='h-4 w-4' />
                  Open page
                </button>
              )}
            </div>
          </Card>
        );
      })}
    </div>
  );
}

function StatusPill({ status }: { status: InstalledPageView['status'] }): JSX.Element {
  const meta: Record<
    InstalledPageView['status'],
    { label: string; cls: string }
  > = {
    connected: {
      label: 'Connected',
      cls: 'bg-emerald-500/15 text-emerald-300',
    },
    available: {
      label: 'Available',
      cls: 'bg-sky-500/15 text-sky-200',
    },
    offline: {
      label: 'Offline',
      cls: 'bg-secondary/70 text-muted-foreground',
    },
    error: {
      label: 'Error',
      cls: 'bg-destructive/15 text-destructive',
    },
  };
  return (
    <span className={cn('rounded-full px-2 py-0.5 text-[11px] font-medium', meta[status].cls)}>
      {meta[status].label}
    </span>
  );
}
