import type { ProfilePreferences } from './generated-types';
import { readDiscoverRecents, replaceDiscoverRecents } from './discover-catalog';
import { loadSidebarLayout, saveSidebarLayout } from './nav';
import {
  getStoredSessionsQuickActionsCollapsed,
  setStoredSessionsQuickActionsCollapsed,
} from './session-prefs';
import { applyTheme, getStoredTheme, setStoredTheme, type Theme } from './theme';

export function readLocalPortablePreferences(): Partial<ProfilePreferences> {
  return {
    theme: getStoredTheme(),
    sidebar_layout: loadSidebarLayout() as unknown as Record<string, unknown>,
    sessions_quick_actions_collapsed: getStoredSessionsQuickActionsCollapsed(),
    discover_recent_keys: readDiscoverRecents(),
  };
}

export function isProfilePreferencesEmpty(
  preferences: Partial<ProfilePreferences> | null | undefined
): boolean {
  if (!preferences) return true;
  const hasTheme = typeof preferences.theme === 'string' && preferences.theme.length > 0;
  const hasSidebar =
    preferences.sidebar_layout !== null &&
    preferences.sidebar_layout !== undefined &&
    Object.keys(preferences.sidebar_layout).length > 0;
  const hasSessions = typeof preferences.sessions_quick_actions_collapsed === 'boolean';
  const hasRecents = Array.isArray(preferences.discover_recent_keys) && preferences.discover_recent_keys.length > 0;
  return !(hasTheme || hasSidebar || hasSessions || hasRecents);
}

export function applyPortablePreferences(preferences: Partial<ProfilePreferences>): void {
  if (preferences.theme) {
    setStoredTheme(preferences.theme as Theme, { emit: false });
    applyTheme(preferences.theme as Theme);
  }
  if (preferences.sidebar_layout) {
    saveSidebarLayout(preferences.sidebar_layout as never, { emit: false });
  }
  if (typeof preferences.sessions_quick_actions_collapsed === 'boolean') {
    setStoredSessionsQuickActionsCollapsed(preferences.sessions_quick_actions_collapsed, {
      emit: false,
    });
  }
  if (Array.isArray(preferences.discover_recent_keys)) {
    replaceDiscoverRecents(preferences.discover_recent_keys, { emit: false });
  }
}

