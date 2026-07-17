import { useEffect, useState } from 'react';
import type { LucideIcon } from 'lucide-react';
import {
  ArrowRight,
  Bot,
  CheckCircle2,
  Database,
  Download,
  ExternalLink,
  Filter,
  Globe2,
  Hammer,
  Laptop,
  Layers,
  Loader2,
  PackageOpen,
  RefreshCw,
  Search,
  ShieldCheck,
  Sparkles,
  Star,
  Trash2,
  Workflow,
  Wrench,
} from 'lucide-react';

import type { MarketplaceResponse } from '@shared/generated-types';
import {
  buildDiscoverCatalog,
  categoryMeta,
  collectDiscoverTags,
  countDiscoverCategories,
  DEFAULT_DISCOVER_FILTERS,
  DISCOVER_CATEGORIES,
  discoverItemLabel,
  filterDiscoverItems,
  prettyTag,
  readDiscoverRecents,
  rememberDiscoverItem,
  type DiscoverCategoryId,
  type DiscoverFilters,
  type DiscoverItem,
  type DiscoverQuickActionItem,
  type DiscoverToolItem,
} from '@shared/discover-catalog';
import {
  fetchMarketplace,
  installTool,
  uninstallTool,
} from '@shared/marketplace-client';
import { useDaemon } from '@shared/daemon-context';
import { launchQuickAction, listQuickActions, type QuickAction } from '@shared/quick-actions-client';
import { openExternal } from '@shared/electron-bridge';
import type { CatalogPreferenceItem, CatalogPreferenceState } from '@shared/generated-types';
import { getCatalogState, setFavorite } from '@shared/profile-client';
import { cn } from '@shared/utils';
import { Badge } from './ui/badge';
import { Button } from './ui/button';
import { Card } from './ui/card';
import { Input } from './ui/input';
import { Modal } from './ui/modal';

type DiscoverCollection = 'all' | 'continue' | 'featured';

const SHELF_CARD_LIMIT = 4;

const CATEGORY_ICONS: Record<DiscoverCategoryId, LucideIcon> = {
  'ai-assistants': Bot,
  workflows: Workflow,
  editors: Laptop,
  remote: Globe2,
  'dev-tools': Hammer,
  system: Wrench,
  data: Database,
  more: Layers,
};

type DiscoverPresentationItem = DiscoverItem & {
  profileState: CatalogPreferenceItem | null;
};

interface MarketplaceBrowserProps {
  onManageInstalledTool?: (toolId: string) => void;
  focusToolId?: string | null;
  focusNonce?: number;
}

export function MarketplaceBrowser({
  onManageInstalledTool,
  focusToolId = null,
  focusNonce = 0,
}: MarketplaceBrowserProps = {}): JSX.Element {
  const { recentEvents } = useDaemon();
  const [marketplace, setMarketplace] = useState<MarketplaceResponse | null>(null);
  const [quickActions, setQuickActions] = useState<QuickAction[]>([]);
  const [catalogState, setCatalogState] = useState<CatalogPreferenceState | null>(null);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [filters, setFilters] = useState<DiscoverFilters>(DEFAULT_DISCOVER_FILTERS);
  const [collection, setCollection] = useState<DiscoverCollection>('all');
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [recentKeys, setRecentKeys] = useState<string[]>(() =>
    typeof window === 'undefined' ? [] : readDiscoverRecents()
  );

  async function load(refresh = false): Promise<void> {
    setBusy(true);
    setError(null);
    const [marketplaceResult, quickActionsResult] = await Promise.allSettled([
      fetchMarketplace(refresh),
      listQuickActions(),
    ]);
    const profileResult = await Promise.allSettled([getCatalogState()]);
    const issues: string[] = [];

    if (marketplaceResult.status === 'fulfilled') {
      setMarketplace(marketplaceResult.value);
    } else {
      issues.push(`Marketplace: ${marketplaceResult.reason instanceof Error ? marketplaceResult.reason.message : 'Failed to load.'}`);
    }

    if (quickActionsResult.status === 'fulfilled') {
      setQuickActions(quickActionsResult.value);
    } else {
      issues.push(`Quick actions: ${quickActionsResult.reason instanceof Error ? quickActionsResult.reason.message : 'Failed to load.'}`);
    }

    if (profileResult[0].status === 'fulfilled') {
      setCatalogState(profileResult[0].value);
    } else {
      issues.push(`Profile catalog: ${profileResult[0].reason instanceof Error ? profileResult[0].reason.message : 'Failed to load.'}`);
    }

    setReady(true);
    setBusy(false);
    if (issues.length > 0) setError(issues.join(' '));
  }

  useEffect(() => {
    void load();
  }, []);

  useEffect(() => {
    const fresh = recentEvents.some(
      (event) =>
        event.name === 'v1.profile.updated' ||
        event.name === 'v1.profile.sync.updated' ||
        event.name === 'v1.service_connection.updated'
    );
    if (!fresh) return;
    void getCatalogState().then(setCatalogState).catch(() => undefined);
  }, [recentEvents]);

  const catalogBase = buildDiscoverCatalog(marketplace, quickActions);
  const profileByKey = new Map((catalogState?.items ?? []).map((item) => [item.item_key, item]));
  const catalog: DiscoverPresentationItem[] = catalogBase.map((item) => ({
    ...item,
    profileState: profileByKey.get(item.key) ?? null,
  }));
  const allTags = collectDiscoverTags(catalog);
  const continueUsingItems = buildContinueUsingItems(catalog, recentKeys);
  const featuredItems = catalog.filter((item) => item.featured);
  const collectionItems = applyCollection(catalog, collection, continueUsingItems);
  const filteredItems = filterDiscoverItems(collectionItems, filters);
  const categoryScopedItems = filterDiscoverItems(collectionItems, {
    ...filters,
    category: 'all',
  });
  const categoryCounts = countDiscoverCategories(categoryScopedItems);
  const isLanding = isDefaultFilters(filters) && collection === 'all';
  const totalTools = catalog.filter((item) => item.kind === 'tool').length;
  const totalQuickActions = catalog.length - totalTools;
  const activeFilterCount = countActiveFilters(filters, collection);

  useEffect(() => {
    if (!focusToolId || focusNonce === 0 || catalog.length === 0) return;
    const target = catalog.find((item) => item.kind === 'tool' && item.id === focusToolId);
    if (!target) return;
    setCollection('all');
    setFilters({
      ...DEFAULT_DISCOVER_FILTERS,
      kind: 'tools',
      query: target.name,
    });
    window.setTimeout(() => {
      document
        .querySelector<HTMLElement>(`[data-discover-id="${focusToolId}"]`)
        ?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }, 120);
  }, [catalog, focusNonce, focusToolId]);

  async function handleInstall(item: DiscoverToolItem): Promise<void> {
    setBusyId(item.key);
    setError(null);
    try {
      const res = await installTool(item.id);
      setRecentKeys(rememberDiscoverItem(item.key));
      setMarketplace((prev) =>
        prev
          ? {
              ...prev,
              installed_ids: Array.from(new Set([...prev.installed_ids, res.installed])).sort(),
            }
          : prev
      );
      setCatalogState(await getCatalogState());
    } catch (err) {
      setError(`Install failed: ${(err as Error).message}`);
    } finally {
      setBusyId(null);
    }
  }

  async function handleUninstall(item: DiscoverToolItem): Promise<void> {
    if (!window.confirm(`Uninstall '${item.id}'? Its manifest will be removed from tools/.`)) return;
    setBusyId(item.key);
    setError(null);
    try {
      await uninstallTool(item.id);
      setMarketplace((prev) =>
        prev
          ? { ...prev, installed_ids: prev.installed_ids.filter((id) => id !== item.id) }
          : prev
      );
      setCatalogState(await getCatalogState());
    } catch (err) {
      setError(`Uninstall failed: ${(err as Error).message}`);
    } finally {
      setBusyId(null);
    }
  }

  async function handleLaunchQuickAction(item: DiscoverQuickActionItem): Promise<void> {
    setBusyId(item.key);
    setError(null);
    try {
      const launched = await launchQuickAction(item.id);
      setRecentKeys(rememberDiscoverItem(item.key));
      window.dispatchEvent(
        new CustomEvent('synapse:open-session', {
          detail: { sessionId: launched.session_id },
        })
      );
      setCatalogState(await getCatalogState());
    } catch (err) {
      setError(`Quick-action launch failed: ${(err as Error).message}`);
    } finally {
      setBusyId(null);
    }
  }

  function handleManageInstalled(item: DiscoverToolItem): void {
    setRecentKeys(rememberDiscoverItem(item.key));
    onManageInstalledTool?.(item.id);
  }

  function handleOpenHomepage(item: DiscoverToolItem): void {
    if (!item.homepage) return;
    setRecentKeys(rememberDiscoverItem(item.key));
    void openExternal(item.homepage);
  }

  function chooseCategory(category: 'all' | DiscoverCategoryId): void {
    setCollection('all');
    setFilters((prev) => ({ ...prev, category }));
  }

  function updateFilters(next: Partial<DiscoverFilters>): void {
    setCollection('all');
    setFilters((prev) => ({ ...prev, ...next }));
  }

  function showCollection(next: DiscoverCollection): void {
    setCollection(next);
    setFilters((prev) => ({ ...prev, query: '', category: 'all', tag: 'all' }));
  }

  function resetDiscover(): void {
    setCollection('all');
    setFilters(DEFAULT_DISCOVER_FILTERS);
  }

  async function handleToggleFavorite(item: DiscoverPresentationItem): Promise<void> {
    setBusyId(item.key);
    setError(null);
    try {
      await setFavorite(item.kind === 'tool' ? 'tool' : 'quick-action', item.id, !item.profileState?.favorite);
      setCatalogState(await getCatalogState());
    } catch (err) {
      setError(`Favorite update failed: ${(err as Error).message}`);
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className='flex flex-col gap-5'>
      <Card className='overflow-hidden border-border/70 bg-gradient-to-br from-card via-card to-card/80 p-0'>
        <div className='flex flex-col gap-4 p-5 sm:p-6'>
          <div className='flex flex-wrap items-start justify-between gap-4'>
            <div className='max-w-3xl space-y-2'>
              <div className='flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.18em] text-primary/85'>
                <Sparkles className='h-3.5 w-3.5' />
                Discover
              </div>
              <div>
                <h2 className='text-2xl font-semibold tracking-tight'>A cleaner marketplace for Synapse tools and workflows</h2>
                <p className='mt-1 max-w-2xl text-sm text-muted-foreground'>
                  Browse installable tools and AI quick actions the way a real storefront should work:
                  curated shelves first, fast filters when you want them, and the same information architecture
                  on desktop and phone.
                </p>
              </div>
            </div>
            <div className='flex flex-wrap items-center gap-2'>
              <CountBadge label='Tools' value={totalTools} />
              <CountBadge label='Quick actions' value={totalQuickActions} />
              <Button variant='outline' size='sm' onClick={() => void load(true)} disabled={busy}>
                {busy ? <Loader2 className='h-4 w-4 animate-spin' /> : <RefreshCw className='h-4 w-4' />}
                Refresh
              </Button>
            </div>
          </div>

          <div className='flex flex-col gap-3 border-t border-border/60 pt-4'>
            <div className='flex flex-col gap-3 lg:flex-row lg:items-center'>
              <label className='relative flex-1'>
                <Search className='pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground' />
                <Input
                  value={filters.query}
                  onChange={(e) => updateFilters({ query: e.target.value })}
                  placeholder='Search tools, quick actions, publishers, tags, or commands...'
                  className='h-11 rounded-2xl border-border/70 bg-background/70 pl-9'
                  aria-label='Search discover catalog'
                />
              </label>
              <div className='flex flex-wrap items-center gap-2'>
                <Button
                  type='button'
                  variant='outline'
                  className='h-11 rounded-2xl border-border/70 px-4'
                  onClick={() => setFiltersOpen(true)}
                >
                  <Filter className='h-4 w-4' />
                  Filters
                  {activeFilterCount > 0 && (
                    <span className='rounded-full bg-primary/15 px-2 py-0.5 text-[11px] font-semibold text-primary'>
                      {activeFilterCount}
                    </span>
                  )}
                </Button>
                {!isLanding && (
                  <Button type='button' variant='ghost' className='h-11 rounded-2xl px-4' onClick={resetDiscover}>
                    Reset
                  </Button>
                )}
              </div>
            </div>

            <div className='flex gap-2 overflow-x-auto pb-1 lg:hidden'>
              <CategoryChip
                label='All'
                active={filters.category === 'all' && collection === 'all'}
                count={catalog.length}
                onClick={resetDiscover}
              />
              {DISCOVER_CATEGORIES.filter((category) => categoryCounts[category.id] > 0).map((category) => (
                <CategoryChip
                  key={category.id}
                  label={category.label}
                  active={filters.category === category.id}
                  count={categoryCounts[category.id]}
                  onClick={() => chooseCategory(category.id)}
                />
              ))}
            </div>

            {activeFilterCount > 0 && (
              <div className='flex flex-wrap items-center gap-2 text-xs text-muted-foreground'>
                <span className='font-medium text-foreground'>Active:</span>
                {filters.kind !== 'all' && <InlineFilterPill label={filters.kind === 'tools' ? 'Tools only' : 'Quick actions only'} />}
                {filters.trust !== 'all' && <InlineFilterPill label={filters.trust === 'verified' ? 'Verified only' : 'Community only'} />}
                {filters.state !== 'all' && <InlineFilterPill label={filters.state === 'installed' ? 'Installed only' : 'Not installed'} />}
                {filters.category !== 'all' && <InlineFilterPill label={categoryMeta(filters.category).label} />}
                {filters.tag !== 'all' && <InlineFilterPill label={`Tag: ${prettyTag(filters.tag)}`} />}
                {collection === 'featured' && <InlineFilterPill label='Featured' />}
                {collection === 'continue' && <InlineFilterPill label='Continue using' />}
              </div>
            )}
          </div>
        </div>
      </Card>

      {error && (
        <p role='alert' className='text-sm text-destructive'>
          {error}
        </p>
      )}

      {!ready && (
        <Card className='flex items-center justify-center gap-2 p-12 text-sm text-muted-foreground'>
          <Loader2 className='h-4 w-4 animate-spin' /> Loading discover catalog...
        </Card>
      )}

      {ready && catalog.length === 0 && (
        <Card className='flex flex-col items-center gap-3 border-dashed p-12 text-center'>
          <PackageOpen className='h-8 w-8 text-muted-foreground' />
          <p className='max-w-xl text-sm text-muted-foreground'>
            No marketplace entries or quick actions are available right now. Point
            <code className='mx-1 font-mono'>SYNAPSE_TOOL_REGISTRY_URL</code>
            at a registry, or drop tools into <code className='font-mono'>tools/</code> and templates into
            <code className='mx-1 font-mono'>templates/quick-actions/</code>.
          </p>
        </Card>
      )}

      {ready && catalog.length > 0 && (
        <div className='grid gap-6 lg:grid-cols-[240px_minmax(0,1fr)]'>
          <aside className='hidden self-start lg:block'>
            <div className='sticky top-6 grid max-h-[calc(100vh-3rem)] grid-rows-[minmax(0,1fr)_auto_auto] gap-4'>
              <Card className='flex min-h-0 flex-col p-4'>
                <div className='mb-3'>
                  <p className='text-sm font-semibold'>Browse by category</p>
                  <p className='mt-1 text-xs text-muted-foreground'>
                    Counts respect your current search and filters.
                  </p>
                </div>
                <div className='min-h-0 space-y-1.5 overflow-y-auto pr-1'>
                  <CategoryRailButton
                    label='All'
                    description='Full catalog'
                    count={catalog.length}
                    active={filters.category === 'all' && collection === 'all'}
                    onClick={resetDiscover}
                  />
                  {DISCOVER_CATEGORIES.filter((category) => categoryCounts[category.id] > 0).map((category) => (
                    <CategoryRailButton
                      key={category.id}
                      label={category.label}
                      description={category.description}
                      count={categoryCounts[category.id]}
                      active={filters.category === category.id}
                      onClick={() => chooseCategory(category.id)}
                    />
                  ))}
                </div>
              </Card>

              <Card className='p-4'>
                <div className='mb-3'>
                  <p className='text-sm font-semibold'>Collections</p>
                  <p className='mt-1 text-xs text-muted-foreground'>
                    Fast ways to jump into your most useful shelves.
                  </p>
                </div>
                <div className='space-y-1.5'>
                  <CategoryRailButton
                    label='Continue using'
                    description='Recent tools and launchers'
                    count={continueUsingItems.length}
                    active={collection === 'continue'}
                    onClick={() => showCollection('continue')}
                  />
                  <CategoryRailButton
                    label='Featured'
                    description='Curated picks worth surfacing first'
                    count={featuredItems.length}
                    active={collection === 'featured'}
                    onClick={() => showCollection('featured')}
                  />
                </div>
              </Card>

              <Card className='p-4 text-xs text-muted-foreground'>
                <p className='font-semibold text-foreground'>Registry source</p>
                <p className='mt-2 break-words'>
                  {marketplace?.source
                    ? marketplace.source.kind === 'url'
                      ? marketplace.source.location
                      : 'Bundled sample registry'
                    : 'Loading source...'}
                </p>
              </Card>
            </div>
          </aside>

          <div className='min-w-0 space-y-6'>
            {isLanding ? (
              <>
                {continueUsingItems.length > 0 && (
                  <DiscoverShelf
                    title='Continue using'
                    description='Installed tools and recently launched workflows stay close.'
                    items={continueUsingItems.slice(0, SHELF_CARD_LIMIT)}
                    onViewAll={() => showCollection('continue')}
                    busyId={busyId}
                    onInstall={handleInstall}
                    onUninstall={handleUninstall}
                    onManageInstalled={handleManageInstalled}
                    onLaunchQuickAction={handleLaunchQuickAction}
                    onOpenHomepage={handleOpenHomepage}
                    onTagClick={(tag) => updateFilters({ tag })}
                    onToggleFavorite={handleToggleFavorite}
                  />
                )}

                {featuredItems.length > 0 && (
                  <DiscoverShelf
                    title='Featured'
                    description='A curated front page instead of an endless grid.'
                    items={featuredItems.slice(0, SHELF_CARD_LIMIT)}
                    onViewAll={() => showCollection('featured')}
                    busyId={busyId}
                    onInstall={handleInstall}
                    onUninstall={handleUninstall}
                    onManageInstalled={handleManageInstalled}
                    onLaunchQuickAction={handleLaunchQuickAction}
                    onOpenHomepage={handleOpenHomepage}
                    onTagClick={(tag) => updateFilters({ tag })}
                    onToggleFavorite={handleToggleFavorite}
                  />
                )}

                {DISCOVER_CATEGORIES.filter((category) => {
                  if (category.id === 'more') return categoryCounts.more > 0;
                  return categoryCounts[category.id] > 0;
                }).map((category) => {
                  const sectionItems = catalog.filter((item) => item.category === category.id).slice(0, SHELF_CARD_LIMIT);
                  if (sectionItems.length === 0) return null;
                  return (
                    <DiscoverShelf
                      key={category.id}
                      title={category.label}
                      description={category.description}
                      items={sectionItems}
                      onViewAll={() => chooseCategory(category.id)}
                      busyId={busyId}
                      onInstall={handleInstall}
                      onUninstall={handleUninstall}
                      onManageInstalled={handleManageInstalled}
                      onLaunchQuickAction={handleLaunchQuickAction}
                      onOpenHomepage={handleOpenHomepage}
                      onTagClick={(tag) => updateFilters({ tag })}
                      onToggleFavorite={handleToggleFavorite}
                    />
                  );
                })}
              </>
            ) : (
              <Card className='space-y-5 p-5 sm:p-6'>
                <div className='flex flex-wrap items-start justify-between gap-3'>
                  <div>
                    <h3 className='text-xl font-semibold'>
                      {resultHeading(filters, collection)}
                    </h3>
                    <p className='mt-1 text-sm text-muted-foreground'>
                      {filteredItems.length} {filteredItems.length === 1 ? 'result' : 'results'} across tools and quick actions.
                    </p>
                  </div>
                  <Badge variant='outline' className='rounded-full border-border/70 px-3 py-1 text-[11px] uppercase tracking-[0.14em]'>
                    {activeFilterCount > 0 ? `${activeFilterCount} filters active` : 'All results'}
                  </Badge>
                </div>

                {filteredItems.length === 0 ? (
                  <div className='flex flex-col items-center gap-3 rounded-2xl border border-dashed border-border/70 bg-secondary/20 px-6 py-12 text-center'>
                    <PackageOpen className='h-8 w-8 text-muted-foreground' />
                    <div>
                      <p className='text-base font-semibold'>No matches yet</p>
                      <p className='mt-1 max-w-xl text-sm text-muted-foreground'>
                        Try clearing a filter, broadening your search, or switching back to the storefront shelves.
                      </p>
                    </div>
                    <Button variant='outline' onClick={resetDiscover}>
                      Reset discover view
                    </Button>
                  </div>
                ) : (
                  <div className='grid grid-cols-[repeat(auto-fill,minmax(min(100%,320px),1fr))] gap-4'>
                    {filteredItems.map((item) => (
                      <DiscoverCard
                        key={item.key}
                        item={item}
                        busy={busyId === item.key}
                        onInstall={handleInstall}
                        onUninstall={handleUninstall}
                        onManageInstalled={handleManageInstalled}
                        onLaunchQuickAction={handleLaunchQuickAction}
                        onOpenHomepage={handleOpenHomepage}
                        onTagClick={(tag) => updateFilters({ tag })}
                        onToggleFavorite={handleToggleFavorite}
                      />
                    ))}
                  </div>
                )}
              </Card>
            )}
          </div>
        </div>
      )}

      <Modal
          open={filtersOpen}
        onClose={() => setFiltersOpen(false)}
        labelledBy='discover-filters-title'
        className='h-[100dvh] max-h-[100dvh] max-w-none rounded-none border-x-0 border-b-0 p-5 sm:h-auto sm:max-h-[90vh] sm:max-w-lg sm:rounded-2xl sm:border'
      >
        <div className='flex items-start justify-between gap-3'>
          <div>
            <h3 id='discover-filters-title' className='text-lg font-semibold'>
              Discover filters
            </h3>
            <p className='mt-1 text-sm text-muted-foreground'>
              Refine the catalog without losing the storefront feel.
            </p>
          </div>
          <Button type='button' variant='ghost' size='sm' onClick={resetDiscover}>
            Reset
          </Button>
        </div>

        <div className='grid gap-4 sm:grid-cols-2'>
          <FilterField
            label='Kind'
            value={filters.kind}
            onChange={(value) => updateFilters({ kind: value as DiscoverFilters['kind'] })}
            options={[
              ['all', 'All'],
              ['tools', 'Tools'],
              ['quick-actions', 'Quick actions'],
            ]}
          />
          <FilterField
            label='Trust'
            value={filters.trust}
            onChange={(value) => updateFilters({ trust: value as DiscoverFilters['trust'] })}
            options={[
              ['all', 'All'],
              ['verified', 'Verified'],
              ['community', 'Community'],
            ]}
          />
          <FilterField
            label='Install state'
            value={filters.state}
            onChange={(value) => updateFilters({ state: value as DiscoverFilters['state'] })}
            options={[
              ['all', 'All'],
              ['installed', 'Installed'],
              ['not-installed', 'Not installed'],
            ]}
          />
          <FilterField
            label='Category'
            value={filters.category}
              onChange={(value) => chooseCategory(value as DiscoverFilters['category'])}
              options={[
                ['all', 'All categories'],
                ...DISCOVER_CATEGORIES.map(
                  (category) => [category.id, category.label] as [string, string]
                ),
              ]}
            />
          <div className='sm:col-span-2'>
            <FilterField
              label='Tag'
              value={filters.tag}
              onChange={(value) => updateFilters({ tag: value as DiscoverFilters['tag'] })}
              options={[
                ['all', 'All tags'],
                ...allTags.map((tag) => [tag, prettyTag(tag)] as [string, string]),
              ]}
            />
          </div>
        </div>

        <div className='flex justify-end'>
          <Button type='button' onClick={() => setFiltersOpen(false)}>
            Done
          </Button>
        </div>
      </Modal>
    </div>
  );
}

interface DiscoverShelfProps {
  title: string;
  description: string;
  items: DiscoverPresentationItem[];
  onViewAll: () => void;
  busyId: string | null;
  onInstall: (item: DiscoverToolItem) => void;
  onUninstall: (item: DiscoverToolItem) => void;
  onManageInstalled: (item: DiscoverToolItem) => void;
  onLaunchQuickAction: (item: DiscoverQuickActionItem) => void;
  onOpenHomepage: (item: DiscoverToolItem) => void;
  onTagClick: (tag: string) => void;
  onToggleFavorite: (item: DiscoverPresentationItem) => void;
}

function DiscoverShelf({
  title,
  description,
  items,
  onViewAll,
  busyId,
  onInstall,
  onUninstall,
  onManageInstalled,
  onLaunchQuickAction,
  onOpenHomepage,
  onTagClick,
  onToggleFavorite,
}: DiscoverShelfProps): JSX.Element {
  return (
    <section className='space-y-4'>
      <div className='flex flex-wrap items-end justify-between gap-3'>
        <div>
          <h3 className='text-xl font-semibold tracking-tight'>{title}</h3>
          <p className='mt-1 text-sm text-muted-foreground'>{description}</p>
        </div>
        <Button type='button' variant='ghost' className='rounded-full px-0 text-sm' onClick={onViewAll}>
          View all
          <ArrowRight className='h-4 w-4' />
        </Button>
      </div>
      <div className='grid grid-cols-[repeat(auto-fill,minmax(min(100%,300px),1fr))] gap-4'>
        {items.map((item) => (
          <DiscoverCard
            key={item.key}
            item={item}
            busy={busyId === item.key}
            onInstall={onInstall}
            onUninstall={onUninstall}
            onManageInstalled={onManageInstalled}
            onLaunchQuickAction={onLaunchQuickAction}
            onOpenHomepage={onOpenHomepage}
            onTagClick={onTagClick}
            onToggleFavorite={onToggleFavorite}
          />
        ))}
      </div>
    </section>
  );
}

interface DiscoverCardProps {
  item: DiscoverPresentationItem;
  busy: boolean;
  onInstall: (item: DiscoverToolItem) => void;
  onUninstall: (item: DiscoverToolItem) => void;
  onManageInstalled: (item: DiscoverToolItem) => void;
  onLaunchQuickAction: (item: DiscoverQuickActionItem) => void;
  onOpenHomepage: (item: DiscoverToolItem) => void;
  onTagClick: (tag: string) => void;
  onToggleFavorite: (item: DiscoverPresentationItem) => void;
}

function DiscoverCard({
  item,
  busy,
  onInstall,
  onUninstall,
  onManageInstalled,
  onLaunchQuickAction,
  onOpenHomepage,
  onTagClick,
  onToggleFavorite,
}: DiscoverCardProps): JSX.Element {
  const Icon = CATEGORY_ICONS[item.category];

  return (
    <Card
      data-discover-id={item.id}
      className='flex h-full flex-col gap-4 overflow-hidden rounded-3xl border-border/70 bg-gradient-to-br from-card via-card to-secondary/20 p-5'
    >
      <div className='flex items-start justify-between gap-3'>
        <div className='flex min-w-0 items-start gap-3'>
          <div className='mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-primary/12 text-primary'>
            <Icon className='h-4.5 w-4.5' aria-hidden='true' />
          </div>
          <div className='min-w-0'>
            <div className='flex flex-wrap items-center gap-2'>
              <h4 className='truncate text-base font-semibold'>{item.name}</h4>
              {item.featured && (
                <Badge className='rounded-full bg-primary/15 px-2 py-0.5 text-[10px] font-semibold text-primary'>
                  Featured
                </Badge>
              )}
            </div>
            <p className='mt-1 text-xs text-muted-foreground'>
              {discoverItemLabel(item)} · {categoryMeta(item.category).label}
              {item.kind === 'tool' && <> · v{item.version}</>}
            </p>
          </div>
        </div>
        <div className='flex shrink-0 flex-col items-end gap-1.5'>
          <button
            type='button'
            onClick={() => void onToggleFavorite(item)}
            disabled={busy}
            className={cn(
              'rounded-full border px-2 py-1 text-[10px] font-medium transition-colors disabled:opacity-60',
              item.profileState?.favorite
                ? 'border-yellow-400/40 bg-yellow-400/10 text-yellow-200'
                : 'border-border/70 bg-background/60 text-muted-foreground hover:text-foreground'
            )}
            aria-label={item.profileState?.favorite ? `Unfavorite ${item.name}` : `Favorite ${item.name}`}
            title={item.profileState?.favorite ? 'Favorited' : 'Favorite'}
          >
            {busy ? (
              <Loader2 className='h-3 w-3 animate-spin' />
            ) : (
              <Star className={cn('h-3 w-3', item.profileState?.favorite && 'fill-current')} />
            )}
          </button>
          {item.kind === 'tool' && (
            <span
              className={cn(
                'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium',
                item.tier === 'declarative'
                  ? 'bg-sky-500/15 text-sky-300'
                  : 'bg-violet-500/20 text-violet-200'
              )}
            >
              <Layers className='h-2.5 w-2.5' />
              {item.tier === 'declarative' ? 'Declarative' : 'Handler'}
            </span>
          )}
          <span
            className={cn(
              'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium',
              item.verified
                ? 'bg-emerald-500/15 text-emerald-300'
                : 'bg-secondary text-secondary-foreground'
            )}
          >
            {item.verified ? <ShieldCheck className='h-2.5 w-2.5' /> : <Layers className='h-2.5 w-2.5' />}
            {item.verified ? 'Verified' : 'Community'}
          </span>
        </div>
      </div>

      {item.kind === 'tool' ? (
        <p className='font-mono text-[11px] text-muted-foreground'>{item.publisher}</p>
      ) : (
        <p className='font-mono text-[11px] text-muted-foreground'>
          {(item.defaultArgv && item.defaultArgv.length > 0 ? item.defaultArgv.join(' ') : 'claude')}
        </p>
      )}

      <p className='line-clamp-3 text-sm text-muted-foreground'>{item.description}</p>

      {(item.profileState?.favorite || item.profileState?.used_before || item.profileState?.previously_installed) && (
        <div className='flex flex-wrap gap-1.5 text-[10px]'>
          {item.profileState?.favorite && <InlineMetaPill label='Favorite' />}
          {item.profileState?.used_before && <InlineMetaPill label='Used before' />}
          {item.profileState?.previously_installed && !item.profileState.installed_here && (
            <InlineMetaPill label='Previously installed' />
          )}
        </div>
      )}

      {item.tags.length > 0 && (
        <div className='flex flex-wrap gap-1.5'>
          {item.tags.slice(0, 4).map((tag) => (
            <button
              key={tag}
              type='button'
              onClick={() => onTagClick(tag)}
              className='rounded-full border border-border/70 bg-background/60 px-2 py-0.5 text-[10px] font-medium text-muted-foreground transition-colors hover:border-primary/35 hover:text-foreground'
            >
              {prettyTag(tag)}
            </button>
          ))}
        </div>
      )}

      <div className='mt-auto space-y-3'>
        <div className='flex items-center justify-between gap-2 text-xs'>
          {item.kind === 'tool' ? (
            item.installed ? (
              <span className='inline-flex items-center gap-1.5 font-medium text-status-launched'>
                <CheckCircle2 className='h-3.5 w-3.5' />
                Installed
              </span>
            ) : (
              <Badge variant='outline' className='rounded-full border-border/70 text-[10px]'>
                Not installed
              </Badge>
            )
          ) : (
            <span className='inline-flex items-center gap-1.5 font-medium text-primary'>
              <Sparkles className='h-3.5 w-3.5' />
              Ready to launch
            </span>
          )}
          {item.kind === 'tool' && item.homepage && (
            <button
              type='button'
              onClick={() => onOpenHomepage(item)}
              className='inline-flex items-center gap-1 text-muted-foreground transition-colors hover:text-foreground'
            >
              <ExternalLink className='h-3.5 w-3.5' />
              Homepage
            </button>
          )}
        </div>

        {item.kind === 'tool' ? (
          item.installed ? (
            <div className='flex flex-wrap gap-2'>
              <Button
                type='button'
                variant='secondary'
                className='flex-1 rounded-2xl'
                onClick={() => onManageInstalled(item)}
              >
                Manage
              </Button>
              <Button
                type='button'
                variant='ghost'
                className='rounded-2xl text-destructive hover:bg-destructive/10'
                onClick={() => onUninstall(item)}
                disabled={busy}
              >
                {busy ? <Loader2 className='h-4 w-4 animate-spin' /> : <Trash2 className='h-4 w-4' />}
                Uninstall
              </Button>
            </div>
          ) : (
            <Button
              type='button'
              className='w-full rounded-2xl'
              onClick={() => onInstall(item)}
              disabled={!item.manifestAvailable || busy}
            >
              {busy ? <Loader2 className='h-4 w-4 animate-spin' /> : <Download className='h-4 w-4' />}
              Install
            </Button>
          )
        ) : (
          <Button
            type='button'
            className='w-full rounded-2xl'
            onClick={() => onLaunchQuickAction(item)}
            disabled={busy}
          >
            {busy ? <Loader2 className='h-4 w-4 animate-spin' /> : <Sparkles className='h-4 w-4' />}
            Open quick action
          </Button>
        )}
      </div>
    </Card>
  );
}

interface FilterFieldProps {
  label: string;
  value: string;
  options: Array<[string, string]>;
  onChange: (value: string) => void;
}

function FilterField({ label, value, options, onChange }: FilterFieldProps): JSX.Element {
  return (
    <label className='flex flex-col gap-1.5 text-sm'>
      <span className='font-medium'>{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className='h-10 rounded-xl border border-input bg-background px-3 text-sm shadow-sm outline-none transition-colors focus-visible:ring-1 focus-visible:ring-ring'
      >
        {options.map(([optionValue, optionLabel]) => (
          <option key={optionValue} value={optionValue}>
            {optionLabel}
          </option>
        ))}
      </select>
    </label>
  );
}

interface CountBadgeProps {
  label: string;
  value: number;
}

function CountBadge({ label, value }: CountBadgeProps): JSX.Element {
  return (
    <Badge variant='outline' className='rounded-full border-border/70 px-3 py-1 text-[11px] uppercase tracking-[0.14em]'>
      {value} {label}
    </Badge>
  );
}

interface CategoryRailButtonProps {
  label: string;
  description: string;
  count: number;
  active: boolean;
  onClick: () => void;
}

function CategoryRailButton({
  label,
  description,
  count,
  active,
  onClick,
}: CategoryRailButtonProps): JSX.Element {
  return (
    <button
      type='button'
      onClick={onClick}
      className={cn(
        'flex w-full items-start justify-between gap-3 rounded-2xl border px-3 py-3 text-left transition-colors',
        active
          ? 'border-primary/35 bg-primary/10'
          : 'border-transparent bg-secondary/30 hover:border-border/70 hover:bg-secondary/50'
      )}
    >
      <div className='min-w-0'>
        <p className='text-sm font-medium'>{label}</p>
        <p className='mt-1 text-xs text-muted-foreground'>{description}</p>
      </div>
      <span className='rounded-full bg-background/80 px-2 py-0.5 text-[11px] font-semibold text-muted-foreground'>
        {count}
      </span>
    </button>
  );
}

interface CategoryChipProps {
  label: string;
  count: number;
  active: boolean;
  onClick: () => void;
}

function CategoryChip({ label, count, active, onClick }: CategoryChipProps): JSX.Element {
  return (
    <button
      type='button'
      onClick={onClick}
      className={cn(
        'inline-flex shrink-0 items-center gap-2 rounded-full border px-3 py-2 text-xs font-medium transition-colors',
        active
          ? 'border-primary/35 bg-primary/10 text-foreground'
          : 'border-border/70 bg-background/70 text-muted-foreground hover:text-foreground'
      )}
    >
      <span>{label}</span>
      <span className='rounded-full bg-background/80 px-1.5 py-0.5 text-[10px] font-semibold'>
        {count}
      </span>
    </button>
  );
}

interface InlineFilterPillProps {
  label: string;
}

function InlineFilterPill({ label }: InlineFilterPillProps): JSX.Element {
  return (
    <span className='rounded-full border border-border/70 bg-background/70 px-2.5 py-1 text-[11px]'>
      {label}
    </span>
  );
}

function InlineMetaPill({ label }: { label: string }): JSX.Element {
  return (
    <span className='rounded-full border border-border/70 bg-background/60 px-2 py-0.5 text-[10px] font-medium text-muted-foreground'>
      {label}
    </span>
  );
}

function applyCollection(
  items: DiscoverPresentationItem[],
  collection: DiscoverCollection,
  continueUsingItems: DiscoverPresentationItem[]
): DiscoverPresentationItem[] {
  if (collection === 'continue') return continueUsingItems;
  if (collection === 'featured') return items.filter((item) => item.featured);
  return items;
}

function buildContinueUsingItems(items: DiscoverPresentationItem[], recentKeys: string[]): DiscoverPresentationItem[] {
  const byKey = new Map(items.map((item) => [item.key, item]));
  const recentItems = recentKeys
    .map((key) => byKey.get(key))
    .filter((item): item is DiscoverPresentationItem => item !== undefined);
  const used = new Set(recentItems.map((item) => item.key));
  const installedTools = items.filter(
    (item): item is DiscoverPresentationItem => item.kind === 'tool' && item.installed && !used.has(item.key)
  );
  const quickActions = items.filter(
    (item): item is DiscoverPresentationItem => item.kind === 'quick-action' && !used.has(item.key)
  );
  return [...recentItems, ...installedTools, ...quickActions].slice(0, 12);
}

function isDefaultFilters(filters: DiscoverFilters): boolean {
  return (
    filters.query === DEFAULT_DISCOVER_FILTERS.query &&
    filters.kind === DEFAULT_DISCOVER_FILTERS.kind &&
    filters.trust === DEFAULT_DISCOVER_FILTERS.trust &&
    filters.state === DEFAULT_DISCOVER_FILTERS.state &&
    filters.category === DEFAULT_DISCOVER_FILTERS.category &&
    filters.tag === DEFAULT_DISCOVER_FILTERS.tag
  );
}

function countActiveFilters(filters: DiscoverFilters, collection: DiscoverCollection): number {
  let count = 0;
  if (filters.query.trim()) count += 1;
  if (filters.kind !== 'all') count += 1;
  if (filters.trust !== 'all') count += 1;
  if (filters.state !== 'all') count += 1;
  if (filters.category !== 'all') count += 1;
  if (filters.tag !== 'all') count += 1;
  if (collection !== 'all') count += 1;
  return count;
}

function resultHeading(filters: DiscoverFilters, collection: DiscoverCollection): string {
  if (collection === 'continue') return 'Continue using';
  if (collection === 'featured') return 'Featured picks';
  if (filters.category !== 'all') return categoryMeta(filters.category).label;
  if (filters.kind === 'tools') return 'Tool results';
  if (filters.kind === 'quick-actions') return 'Quick-action results';
  if (filters.query.trim()) return `Search: "${filters.query.trim()}"`;
  return 'Filtered results';
}
