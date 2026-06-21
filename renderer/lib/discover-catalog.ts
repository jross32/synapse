import type { MarketplaceResponse, RegistryEntry } from './generated-types';
import type { QuickAction } from './quick-actions-client';

export type DiscoverCategoryId =
  | 'ai-assistants'
  | 'workflows'
  | 'editors'
  | 'remote'
  | 'dev-tools'
  | 'system'
  | 'data'
  | 'more';

export interface DiscoverCategoryMeta {
  id: DiscoverCategoryId;
  label: string;
  description: string;
}

export const DISCOVER_CATEGORIES: DiscoverCategoryMeta[] = [
  {
    id: 'ai-assistants',
    label: 'AI Assistants',
    description: 'Launch coding copilots and AI coding sessions.',
  },
  {
    id: 'workflows',
    label: 'Workflows',
    description: 'One-click tasks that open a guided workflow.',
  },
  {
    id: 'editors',
    label: 'Editors',
    description: 'Jump straight into your preferred editor.',
  },
  {
    id: 'remote',
    label: 'Remote',
    description: 'Reach Synapse and your apps beyond the local machine.',
  },
  {
    id: 'dev-tools',
    label: 'Dev Tools',
    description: 'Git, debugging, and build-adjacent helpers.',
  },
  {
    id: 'system',
    label: 'System',
    description: 'Useful local OS actions and built-in utilities.',
  },
  {
    id: 'data',
    label: 'Data',
    description: 'Logs, documentation, and project introspection tools.',
  },
  {
    id: 'more',
    label: 'More',
    description: 'Anything uncategorized or from a future registry.',
  },
];

export type DiscoverKindFilter = 'all' | 'tools' | 'quick-actions';
export type DiscoverTrustFilter = 'all' | 'verified' | 'community';
export type DiscoverStateFilter = 'all' | 'installed' | 'not-installed';

export interface DiscoverFilters {
  query: string;
  kind: DiscoverKindFilter;
  trust: DiscoverTrustFilter;
  state: DiscoverStateFilter;
  category: 'all' | DiscoverCategoryId;
  tag: 'all' | string;
}

export const DEFAULT_DISCOVER_FILTERS: DiscoverFilters = {
  query: '',
  kind: 'all',
  trust: 'all',
  state: 'all',
  category: 'all',
  tag: 'all',
};

interface DiscoverItemBase {
  key: string;
  id: string;
  name: string;
  description: string;
  category: DiscoverCategoryId;
  tags: string[];
  featured: boolean;
  sortRank: number;
  verified: boolean;
  searchText: string;
}

export interface DiscoverToolItem extends DiscoverItemBase {
  kind: 'tool';
  publisher: string;
  version: string;
  tier: string;
  homepage: string | null;
  installed: boolean;
  manifestAvailable: boolean;
  entry: RegistryEntry;
}

export interface DiscoverQuickActionItem extends DiscoverItemBase {
  kind: 'quick-action';
  icon: string | null;
  defaultArgv: string[];
  action: QuickAction;
}

export type DiscoverItem = DiscoverToolItem | DiscoverQuickActionItem;

const CATEGORY_ALIASES: Record<string, DiscoverCategoryId> = {
  'ai-assistants': 'ai-assistants',
  'ai-coder': 'ai-assistants',
  workflows: 'workflows',
  editors: 'editors',
  remote: 'remote',
  network: 'remote',
  'dev-tools': 'dev-tools',
  system: 'system',
  tools: 'system',
  data: 'data',
};

const RECENTS_KEY = 'synapse.tools.discover-recents';
const MAX_RECENTS = 20;

interface StoredRecent {
  key: string;
  usedAt: number;
}

export function normalizeCategory(raw: string | null | undefined): DiscoverCategoryId {
  if (!raw) return 'more';
  return CATEGORY_ALIASES[raw.trim().toLowerCase()] ?? 'more';
}

export function categoryMeta(category: DiscoverCategoryId): DiscoverCategoryMeta {
  return (
    DISCOVER_CATEGORIES.find((item) => item.id === category) ??
    DISCOVER_CATEGORIES[DISCOVER_CATEGORIES.length - 1]
  );
}

export function prettyTag(tag: string): string {
  return tag
    .split(/[-_]/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
}

export function discoverItemLabel(item: DiscoverItem): string {
  return item.kind === 'tool' ? 'Tool' : 'Quick action';
}

export function buildDiscoverCatalog(
  marketplace: MarketplaceResponse | null,
  quickActions: QuickAction[]
): DiscoverItem[] {
  const installed = new Set(marketplace?.installed_ids ?? []);
  const tools: DiscoverToolItem[] = (marketplace?.registry.tools ?? []).map((entry) => {
    const category = normalizeCategory(entry.category);
    const tags = normalizeTags(entry.tags);
    const searchText = [
      entry.id,
      entry.name,
      entry.description,
      entry.publisher,
      entry.version,
      entry.tier,
      categoryMeta(category).label,
      ...tags,
    ]
      .join(' ')
      .toLowerCase();

    return {
      key: `tool:${entry.id}`,
      kind: 'tool',
      id: entry.id,
      name: entry.name,
      description: entry.description,
      category,
      tags,
      featured: entry.featured === true,
      sortRank: typeof entry.sort_rank === 'number' ? entry.sort_rank : 999,
      verified: entry.verified,
      searchText,
      publisher: entry.publisher,
      version: entry.version,
      tier: entry.tier,
      homepage: entry.homepage,
      installed: installed.has(entry.id),
      manifestAvailable: !!entry.manifest_inline || !!entry.manifest_url,
      entry,
    };
  });

  const actions: DiscoverQuickActionItem[] = quickActions.map((action, index) => {
    const category = normalizeCategory(action.category);
    const tags = normalizeTags(action.tags);
    const searchText = [
      action.id,
      action.name,
      action.description,
      categoryMeta(category).label,
      ...(action.default_argv ?? []),
      ...tags,
    ]
      .join(' ')
      .toLowerCase();

    return {
      key: `quick-action:${action.id}`,
      kind: 'quick-action',
      id: action.id,
      name: action.name,
      description: action.description,
      category,
      tags,
      featured: false,
      sortRank: 300 + index,
      verified: true,
      searchText,
      icon: action.icon,
      defaultArgv: action.default_argv,
      action,
    };
  });

  return [...tools, ...actions].sort(compareDiscoverItems);
}

export function filterDiscoverItems<T extends DiscoverItem>(
  items: T[],
  filters: DiscoverFilters
): T[] {
  const query = filters.query.trim().toLowerCase();
  return items.filter((item) => {
    if (filters.kind === 'tools' && item.kind !== 'tool') return false;
    if (filters.kind === 'quick-actions' && item.kind !== 'quick-action') return false;
    if (filters.trust === 'verified' && !item.verified) return false;
    if (filters.trust === 'community' && item.verified) return false;
    if (filters.state !== 'all') {
      if (item.kind !== 'tool') return false;
      if (filters.state === 'installed' && !item.installed) return false;
      if (filters.state === 'not-installed' && item.installed) return false;
    }
    if (filters.category !== 'all' && item.category !== filters.category) return false;
    if (filters.tag !== 'all' && !item.tags.includes(filters.tag)) return false;
    if (query && !item.searchText.includes(query)) return false;
    return true;
  });
}

export function collectDiscoverTags(items: DiscoverItem[]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const item of items) {
    for (const tag of item.tags) {
      if (seen.has(tag)) continue;
      seen.add(tag);
      out.push(tag);
    }
  }
  return out.sort((a, b) => a.localeCompare(b));
}

export function countDiscoverCategories(items: DiscoverItem[]): Record<DiscoverCategoryId, number> {
  const counts = Object.fromEntries(
    DISCOVER_CATEGORIES.map((category) => [category.id, 0])
  ) as Record<DiscoverCategoryId, number>;
  for (const item of items) {
    counts[item.category] += 1;
  }
  return counts;
}

export function readDiscoverRecents(): string[] {
  try {
    const raw = window.localStorage.getItem(RECENTS_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return [];
    const valid = parsed
      .filter(
        (entry): entry is StoredRecent =>
          typeof entry === 'object' &&
          entry !== null &&
          typeof (entry as { key?: unknown }).key === 'string' &&
          typeof (entry as { usedAt?: unknown }).usedAt === 'number'
      )
      .sort((a, b) => b.usedAt - a.usedAt);
    return dedupeKeys(valid.map((entry) => entry.key)).slice(0, MAX_RECENTS);
  } catch {
    return [];
  }
}

export function rememberDiscoverItem(itemKey: string): string[] {
  const now = Date.now();
  const current = readStoredRecents().filter((entry) => entry.key !== itemKey);
  const next = [{ key: itemKey, usedAt: now }, ...current].slice(0, MAX_RECENTS);
  try {
    window.localStorage.setItem(RECENTS_KEY, JSON.stringify(next));
  } catch {
    return dedupeKeys(next.map((entry) => entry.key));
  }
  return next.map((entry) => entry.key);
}

function compareDiscoverItems(left: DiscoverItem, right: DiscoverItem): number {
  if (left.featured !== right.featured) return left.featured ? -1 : 1;
  if (left.sortRank !== right.sortRank) return left.sortRank - right.sortRank;
  if (left.kind !== right.kind) return left.kind === 'tool' ? -1 : 1;
  return left.name.localeCompare(right.name);
}

function normalizeTags(raw: string[] | undefined): string[] {
  if (!raw) return [];
  const seen = new Set<string>();
  const out: string[] = [];
  for (const tag of raw) {
    const normalized = tag.trim().toLowerCase();
    if (!normalized || seen.has(normalized)) continue;
    seen.add(normalized);
    out.push(normalized);
  }
  return out;
}

function readStoredRecents(): StoredRecent[] {
  try {
    const raw = window.localStorage.getItem(RECENTS_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (entry): entry is StoredRecent =>
        typeof entry === 'object' &&
        entry !== null &&
        typeof (entry as { key?: unknown }).key === 'string' &&
        typeof (entry as { usedAt?: unknown }).usedAt === 'number'
    );
  } catch {
    return [];
  }
}

function dedupeKeys(keys: string[]): string[] {
  return Array.from(new Set(keys));
}
