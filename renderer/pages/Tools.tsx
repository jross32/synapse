// Tools page (Milestone F · v0.1.9) -- the Synapse plugin surface.
//
// Renders one manifest-driven ToolCard per tool the daemon loaded from
// `tools/<id>/manifest.json`. No tool-specific code here: a new tool is a
// folder + a manifest, never a renderer change.

import { useEffect, useRef, useState } from 'react';
import { Loader2, Store, Wrench } from 'lucide-react';

import type { CatalogPreferenceItem, CatalogPreferenceState, ToolEntry } from '@shared/generated-types';
import { listTools } from '@shared/tools-client';
import { useDaemon } from '@shared/daemon-context';
import { getCatalogState } from '@shared/profile-client';
import { cn } from '@shared/utils';
import { Card } from '../components/ui/card';
import { MarketplaceBrowser } from '../components/MarketplaceBrowser';
import { PageHeader } from '../components/PageHeader';
import { ToolCard } from '../components/ToolCard';

type ToolsTab = 'installed' | 'discover';

export interface ToolsPageProps {
  intent?: {
    tab?: ToolsTab;
    focusId?: string;
    nonce: number;
  } | null;
}

export function ToolsPage({ intent }: ToolsPageProps): JSX.Element {
  const { recentEvents } = useDaemon();
  const [tab, setTab] = useState<ToolsTab>('installed');
  const [tools, setTools] = useState<ToolEntry[] | null>(null);
  const [catalogState, setCatalogState] = useState<CatalogPreferenceState | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Highest WS event id already accounted for -- so we only refetch on
  // genuinely new tool events, not the backlog present at mount.
  const seenEventId = useRef(0);

  function refresh(): void {
    setError(null);
    void Promise.allSettled([listTools(), getCatalogState()]).then(([toolsRes, catalogRes]) => {
      if (toolsRes.status === 'fulfilled') {
        setTools(toolsRes.value);
      } else {
        setError(toolsRes.reason instanceof Error ? toolsRes.reason.message : 'Failed to load tools');
      }
      if (catalogRes.status === 'fulfilled') {
        setCatalogState(catalogRes.value);
      }
    });
  }

  useEffect(() => {
    seenEventId.current = recentEvents.reduce((m, e) => Math.max(m, e.id), 0);
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // A tunnel can drop on its own; the daemon broadcasts v1.tool.* events.
  // Refetch when one lands so the card never shows stale state.
  useEffect(() => {
    const fresh = recentEvents.filter(
      (e) => e.id > seenEventId.current && e.name.startsWith('v1.tool.')
    );
    if (fresh.length === 0) return;
    seenEventId.current = recentEvents.reduce((m, e) => Math.max(m, e.id), seenEventId.current);
    refresh();
  }, [recentEvents]);

  useEffect(() => {
    const fresh = recentEvents.some(
      (e) =>
        e.name === 'v1.profile.updated' ||
        e.name === 'v1.profile.sync.updated' ||
        e.name === 'v1.service_connection.updated'
    );
    if (!fresh) return;
    void getCatalogState().then(setCatalogState).catch(() => undefined);
  }, [recentEvents]);

  function handleChanged(updated: ToolEntry): void {
    setTools((prev) =>
      prev ? prev.map((t) => (t.manifest.id === updated.manifest.id ? updated : t)) : prev
    );
  }

  useEffect(() => {
    if (!intent) return;
    if (intent.tab) setTab(intent.tab);
  }, [intent]);

  const toolPreferences = new Map(
    (catalogState?.items ?? [])
      .filter((item) => item.kind === 'tool')
      .map((item) => [item.item_id, item])
  );
  const sortedTools = [...(tools ?? [])].sort((left, right) =>
    compareToolEntries(left, right, toolPreferences)
  );

  return (
    <div className='flex flex-col gap-6'>
      <PageHeader
        title='Tools'
        subtitle='Synapses — modular tools backed by manifest plugins. Drop a folder in, get a card.'
      />

      {/* Installed / Discover tab toggle. Installed remains the operational
          surface; Discover becomes the storefront for tools + quick actions. */}
      <div
        role='tablist'
        aria-label='Tools view'
        className='inline-flex w-fit gap-1 rounded-lg border border-border bg-secondary/30 p-1'
      >
        <TabButton
          active={tab === 'installed'}
          onClick={() => setTab('installed')}
          icon={Wrench}
          label='Installed'
          count={tools?.length}
        />
        <TabButton
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
              <Loader2 className='h-4 w-4 animate-spin' /> Loading tools…
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
                <code className='font-mono'>tools/</code> directly — hot reload picks
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

interface TabButtonProps {
  active: boolean;
  onClick: () => void;
  icon: typeof Wrench;
  label: string;
  count?: number;
}

function TabButton({ active, onClick, icon: Icon, label, count }: TabButtonProps): JSX.Element {
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
      {count !== undefined && (
        <span
          className={cn(
            'rounded-full px-1.5 text-[10px] font-semibold tabular-nums',
            active ? 'bg-secondary text-foreground' : 'bg-background/60'
          )}
        >
          {count}
        </span>
      )}
    </button>
  );
}
