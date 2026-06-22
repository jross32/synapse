// Navigation model for the Synapse shell. The app is a single Electron
// window, so "routing" is just an active-page enum -- no URL router needed.

import {
  Activity,
  House,
  LayoutGrid,
  Settings,
  Sparkles,
  Wrench,
  type LucideIcon,
} from 'lucide-react';

export type PageId = 'home' | 'apps' | 'tools' | 'sessions' | 'processes' | 'settings';

export interface NavItem {
  id: PageId;
  label: string;
  icon: LucideIcon;
  description: string;
  /** Locked items can't be hidden or reordered (Home + Settings).
   *  v0.1.36 A6 -- editable sidebar. */
  locked?: boolean;
}

export const NAV_ITEMS: NavItem[] = [
  { id: 'home', label: 'Home', icon: House, description: 'Featured projects + tools, recent activity', locked: true },
  { id: 'apps', label: 'Apps', icon: LayoutGrid, description: 'Launch + manage your projects' },
  { id: 'tools', label: 'Tools', icon: Wrench, description: 'Synapse tools, agents + workflows' },
  { id: 'sessions', label: 'Sessions', icon: Sparkles, description: 'AI coders + live terminal sessions' },
  { id: 'processes', label: 'Processes', icon: Activity, description: 'Everything running right now' },
  { id: 'settings', label: 'Settings', icon: Settings, description: 'Daemon, theme + about', locked: true },
];

export const DEFAULT_PAGE: PageId = 'home';

/**
 * Persisted user customization for the sidebar (v0.1.36 A6).
 * - `order`: the page ids in user-preferred order (locked ones still
 *   bubble to top/bottom).
 * - `hidden`: set of ids the user has hidden (locked ones can't be).
 */
export interface SidebarLayout {
  order: PageId[];
  hidden: PageId[];
}

const STORAGE_KEY = 'synapse.sidebar.layout';

export function loadSidebarLayout(): SidebarLayout {
  if (typeof window === 'undefined') return { order: NAV_ITEMS.map((n) => n.id), hidden: [] };
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return { order: NAV_ITEMS.map((n) => n.id), hidden: [] };
    const parsed = JSON.parse(raw) as Partial<SidebarLayout>;
    const knownIds = new Set(NAV_ITEMS.map((n) => n.id));
    const order = Array.isArray(parsed.order)
      ? (parsed.order.filter((id) => knownIds.has(id)) as PageId[])
      : [];
    // Append any new NAV items not yet seen, so a future-added tab is
    // visible by default without the user reset-to-default.
    for (const item of NAV_ITEMS) {
      if (!order.includes(item.id)) order.push(item.id);
    }
    const hidden = Array.isArray(parsed.hidden)
      ? (parsed.hidden.filter((id) => knownIds.has(id)) as PageId[])
      : [];
    return { order, hidden };
  } catch {
    return { order: NAV_ITEMS.map((n) => n.id), hidden: [] };
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
  if (options?.emit !== false) {
    window.dispatchEvent(
      new CustomEvent('synapse:portable-preferences', {
        detail: { sidebar_layout: layout },
      })
    );
  }
}

/**
 * Apply the layout to NAV_ITEMS. Locked items are pinned: Home stays
 * at the top, Settings stays at the bottom, regardless of user order.
 * Hidden items are dropped.
 */
export function applySidebarLayout(layout: SidebarLayout): NavItem[] {
  const byId = new Map(NAV_ITEMS.map((n) => [n.id, n]));
  const lockedTop = NAV_ITEMS.filter((n) => n.locked && n.id === 'home');
  const lockedBottom = NAV_ITEMS.filter((n) => n.locked && n.id === 'settings');
  const lockedIds = new Set([...lockedTop, ...lockedBottom].map((n) => n.id));
  const hidden = new Set(layout.hidden);
  const middle: NavItem[] = [];
  for (const id of layout.order) {
    if (lockedIds.has(id)) continue;
    if (hidden.has(id)) continue;
    const item = byId.get(id);
    if (item) middle.push(item);
  }
  return [...lockedTop, ...middle, ...lockedBottom];
}
