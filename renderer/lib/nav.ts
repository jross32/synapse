// Navigation model for the Synapse shell.
//
// Desktop uses grouped hubs plus optional installed pages. Mobile keeps the
// same route model, but only renders the six fixed hubs in the bottom nav.

import {
  BrainCircuit,
  FolderKanban,
  Globe,
  House,
  Rocket,
  Settings,
  Sparkles,
  Wrench,
  type LucideIcon,
} from 'lucide-react';

export type CorePageId =
  | 'home'
  | 'apps'
  | 'tools'
  | 'ai-coding'
  | 'ai-factory'
  | 'settings';

export type RoutePageId = CorePageId | 'whatsnew';

export type AppRoute =
  | { kind: 'core'; page: RoutePageId }
  | { kind: 'installed'; id: string };

export type AppsSection = 'projects' | 'running';
export type ToolsSection = 'tools' | 'marketplace' | 'mcp' | 'installed-pages';
export type ToolsTab = 'installed' | 'discover';
export type MarketplaceSection = 'tools' | 'bundles' | 'models' | 'workers' | 'squads';
export type AiCodingSection = 'sessions' | 'assistant' | 'review';

export type NavigationIntent =
  | { page: 'home' | 'ai-factory' | 'settings' | 'whatsnew' }
  | { page: 'apps'; section?: AppsSection }
  | {
      page: 'tools';
      section?: ToolsSection;
      toolsTab?: ToolsTab;
      focusToolId?: string;
      marketplaceSection?: MarketplaceSection;
    }
  | { page: 'ai-coding'; section?: AiCodingSection }
  | { page: 'installed'; installedPageId: string };

export interface CoreNavItem {
  id: CorePageId;
  label: string;
  icon: LucideIcon;
  description: string;
  section: 'main' | 'ai' | 'system';
  locked?: boolean;
}

export interface InstalledPageNav {
  id: string;
  label: string;
  description: string;
  icon?: string | null;
}

export interface SidebarSectionItem {
  route: AppRoute;
  label: string;
  description: string;
  icon: LucideIcon;
  locked?: boolean;
}

export interface SidebarSection {
  id: 'main' | 'ai' | 'system' | 'installed';
  label: string;
  items: SidebarSectionItem[];
}

export const CORE_NAV_ITEMS: CoreNavItem[] = [
  {
    id: 'home',
    label: 'Home',
    icon: House,
    description: 'Featured projects, activity, and shortcuts',
    section: 'main',
    locked: true,
  },
  {
    id: 'apps',
    label: 'Apps',
    icon: FolderKanban,
    description: 'Projects and everything running right now',
    section: 'main',
  },
  {
    id: 'tools',
    label: 'My Tools',
    icon: Wrench,
    description: 'Installed tools, marketplace, MCP servers, and installed pages',
    section: 'main',
  },
  {
    id: 'ai-coding',
    label: 'AI Coding',
    icon: Sparkles,
    description: 'Sessions, assistant, and review inbox',
    section: 'ai',
  },
  {
    id: 'ai-factory',
    label: 'AI Factory',
    icon: BrainCircuit,
    description: 'Reusable AI systems, workers, and cases',
    section: 'ai',
  },
  {
    id: 'settings',
    label: 'Settings',
    icon: Settings,
    description: 'Profile, navigation, diagnostics, and system settings',
    section: 'system',
    locked: true,
  },
];

export const CORE_NAV_IDS = CORE_NAV_ITEMS.map((item) => item.id);
export const MOBILE_NAV_ORDER: CorePageId[] = [
  'home',
  'apps',
  'tools',
  'ai-coding',
  'ai-factory',
  'settings',
];
export const DEFAULT_ROUTE: AppRoute = { kind: 'core', page: 'home' };

export interface SidebarLayout {
  main_order: Array<'apps' | 'tools'>;
  ai_order: Array<'ai-coding' | 'ai-factory'>;
  hidden_core: Array<'apps' | 'tools' | 'ai-coding' | 'ai-factory'>;
  installed_page_order: string[];
  visible_installed_pages: string[];
}

type LegacyPageId =
  | 'home'
  | 'apps'
  | 'tools'
  | 'sessions'
  | 'assistant'
  | 'review'
  | 'ai-factory'
  | 'marketplace'
  | 'processes'
  | 'whatsnew'
  | 'settings';

interface LegacySidebarLayout {
  order?: LegacyPageId[];
  hidden?: LegacyPageId[];
}

const STORAGE_KEY = 'synapse.sidebar.layout';
const MAIN_DEFAULT: SidebarLayout['main_order'] = ['apps', 'tools'];
const AI_DEFAULT: SidebarLayout['ai_order'] = ['ai-coding', 'ai-factory'];
const HIDEABLE_CORE = new Set<SidebarLayout['hidden_core'][number]>([
  'apps',
  'tools',
  'ai-coding',
  'ai-factory',
]);

export function defaultSidebarLayout(): SidebarLayout {
  return {
    main_order: [...MAIN_DEFAULT],
    ai_order: [...AI_DEFAULT],
    hidden_core: [],
    installed_page_order: [],
    visible_installed_pages: [],
  };
}

function dedupe<T extends string>(values: readonly T[]): T[] {
  const seen = new Set<T>();
  const out: T[] = [];
  for (const value of values) {
    if (seen.has(value)) continue;
    seen.add(value);
    out.push(value);
  }
  return out;
}

function completeOrder<T extends string>(values: readonly T[], defaults: readonly T[]): T[] {
  const next = dedupe(values.filter((value) => defaults.includes(value)));
  for (const value of defaults) {
    if (!next.includes(value)) next.push(value);
  }
  return next;
}

function migrateLegacyLayout(
  legacy: LegacySidebarLayout,
  installedPageIds: readonly string[]
): SidebarLayout {
  const order = Array.isArray(legacy.order) ? legacy.order : [];
  const hidden = Array.isArray(legacy.hidden) ? legacy.hidden : [];
  const aiCodingIndex = order.findIndex(
    (id) => id === 'sessions' || id === 'assistant' || id === 'review'
  );
  const aiFactoryIndex = order.indexOf('ai-factory');
  const ai_order =
    aiFactoryIndex !== -1 &&
    (aiCodingIndex === -1 || aiFactoryIndex < aiCodingIndex)
      ? (['ai-factory', 'ai-coding'] as SidebarLayout['ai_order'])
      : [...AI_DEFAULT];
  return normalizeSidebarLayout(
    {
      main_order: completeOrder(
        order.filter((id): id is 'apps' | 'tools' => id === 'apps' || id === 'tools'),
        MAIN_DEFAULT
      ) as SidebarLayout['main_order'],
      ai_order,
      hidden_core: hidden.filter(
        (id): id is 'apps' | 'tools' | 'ai-factory' =>
          id === 'apps' || id === 'tools' || id === 'ai-factory'
      ) as SidebarLayout['hidden_core'],
      installed_page_order: [],
      visible_installed_pages: [],
    },
    installedPageIds
  );
}

export function normalizeSidebarLayout(
  layout: Partial<SidebarLayout> | null | undefined,
  installedPageIds: readonly string[] = []
): SidebarLayout {
  const defaults = defaultSidebarLayout();
  const installedSet = new Set(installedPageIds);
  return {
    main_order: completeOrder(
      Array.isArray(layout?.main_order) ? layout.main_order : defaults.main_order,
      MAIN_DEFAULT
    ) as SidebarLayout['main_order'],
    ai_order: completeOrder(
      Array.isArray(layout?.ai_order) ? layout.ai_order : defaults.ai_order,
      AI_DEFAULT
    ) as SidebarLayout['ai_order'],
    hidden_core: dedupe(
      Array.isArray(layout?.hidden_core)
        ? layout.hidden_core.filter(
            (id): id is SidebarLayout['hidden_core'][number] => HIDEABLE_CORE.has(id)
          )
        : defaults.hidden_core
    ),
    installed_page_order: dedupe(
      Array.isArray(layout?.installed_page_order)
        ? layout.installed_page_order.filter((id): id is string => installedSet.has(id))
        : []
    ),
    visible_installed_pages: dedupe(
      Array.isArray(layout?.visible_installed_pages)
        ? layout.visible_installed_pages.filter((id): id is string => installedSet.has(id))
        : []
    ),
  };
}

export function loadSidebarLayout(installedPageIds: readonly string[] = []): SidebarLayout {
  if (typeof window === 'undefined') return normalizeSidebarLayout(null, installedPageIds);
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return normalizeSidebarLayout(null, installedPageIds);
    const parsed = JSON.parse(raw) as Partial<SidebarLayout> & LegacySidebarLayout;
    if (Array.isArray(parsed.order) || Array.isArray(parsed.hidden)) {
      return migrateLegacyLayout(parsed, installedPageIds);
    }
    return normalizeSidebarLayout(parsed, installedPageIds);
  } catch {
    return normalizeSidebarLayout(null, installedPageIds);
  }
}

export function saveSidebarLayout(
  layout: SidebarLayout,
  options?: { emit?: boolean }
): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(layout));
  } catch {
    /* private-mode quota -- ignore */
  }
  window.dispatchEvent(
    new CustomEvent('synapse:sidebar-layout-changed', {
      detail: { sidebar_layout: layout },
    })
  );
  if (options?.emit !== false) {
    window.dispatchEvent(
      new CustomEvent('synapse:portable-preferences', {
        detail: { sidebar_layout: layout },
      })
    );
  }
}

export function coreNavItem(id: CorePageId): CoreNavItem {
  return CORE_NAV_ITEMS.find((item) => item.id === id) ?? CORE_NAV_ITEMS[0];
}

export function iconForInstalledPage(page: InstalledPageNav): LucideIcon {
  switch (page.icon) {
    case 'globe':
      return Globe;
    default:
      return Wrench;
  }
}

function installedPageOrder(
  layout: SidebarLayout,
  installedPages: readonly InstalledPageNav[]
): InstalledPageNav[] {
  const byId = new Map(installedPages.map((page) => [page.id, page]));
  const orderedIds = dedupe([
    ...layout.installed_page_order,
    ...installedPages.map((page) => page.id),
  ]);
  const ordered: InstalledPageNav[] = [];
  for (const id of orderedIds) {
    const page = byId.get(id);
    if (page) ordered.push(page);
  }
  return ordered;
}

export function buildDesktopSidebarSections(
  layout: SidebarLayout,
  installedPages: readonly InstalledPageNav[]
): SidebarSection[] {
  const hidden = new Set(layout.hidden_core);
  const installedVisible = new Set(layout.visible_installed_pages);
  const mainItems: SidebarSectionItem[] = [
    {
      route: { kind: 'core', page: 'home' },
      label: coreNavItem('home').label,
      description: coreNavItem('home').description,
      icon: coreNavItem('home').icon,
      locked: true,
    },
  ];
  for (const id of layout.main_order) {
    if (hidden.has(id)) continue;
    const item = coreNavItem(id);
    mainItems.push({
      route: { kind: 'core', page: id },
      label: item.label,
      description: item.description,
      icon: item.icon,
    });
  }

  const aiItems: SidebarSectionItem[] = [];
  for (const id of layout.ai_order) {
    if (hidden.has(id)) continue;
    const item = coreNavItem(id);
    aiItems.push({
      route: { kind: 'core', page: id },
      label: item.label,
      description: item.description,
      icon: item.icon,
    });
  }

  const systemItems: SidebarSectionItem[] = [
    {
      route: { kind: 'core', page: 'settings' },
      label: coreNavItem('settings').label,
      description: coreNavItem('settings').description,
      icon: coreNavItem('settings').icon,
      locked: true,
    },
  ];

  const installedItems = installedPageOrder(layout, installedPages)
    .filter((page) => installedVisible.has(page.id))
    .map<SidebarSectionItem>((page) => ({
      route: { kind: 'installed', id: page.id },
      label: page.label,
      description: page.description,
      icon: iconForInstalledPage(page),
    }));

  const sections: SidebarSection[] = [
    { id: 'main', label: 'Main', items: mainItems },
    { id: 'ai', label: 'AI', items: aiItems },
    { id: 'system', label: 'System', items: systemItems },
    { id: 'installed', label: 'Installed', items: installedItems },
  ];
  return sections.filter((section) => section.items.length > 0);
}

export function routeMatches(route: AppRoute, other: AppRoute): boolean {
  if (route.kind !== other.kind) return false;
  if (route.kind === 'core' && other.kind === 'core') {
    return route.page === other.page;
  }
  return route.kind === 'installed' && other.kind === 'installed' && route.id === other.id;
}

export function routeLabel(
  route: AppRoute,
  installedPages: readonly InstalledPageNav[]
): string {
  if (route.kind === 'core') {
    if (route.page === 'whatsnew') return "What's New";
    return coreNavItem(route.page).label;
  }
  return installedPages.find((page) => page.id === route.id)?.label ?? 'Installed Page';
}

export function routeIcon(
  route: AppRoute,
  installedPages: readonly InstalledPageNav[]
): LucideIcon {
  if (route.kind === 'core') {
    if (route.page === 'whatsnew') return Rocket;
    return coreNavItem(route.page).icon;
  }
  return iconForInstalledPage(
    installedPages.find((page) => page.id === route.id) ?? {
      id: route.id,
      label: route.id,
      description: '',
      icon: 'globe',
    }
  );
}
