const STORAGE_KEY = 'synapse.sessions.qa-collapsed';

export function getStoredSessionsQuickActionsCollapsed(): boolean {
  if (typeof window === 'undefined') return true;
  const raw = window.localStorage.getItem(STORAGE_KEY);
  return raw === null ? true : raw === '1';
}

export function setStoredSessionsQuickActionsCollapsed(
  collapsed: boolean,
  options?: { emit?: boolean }
): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(STORAGE_KEY, collapsed ? '1' : '0');
  } catch {
    /* ignore */
  }
  if (options?.emit !== false) {
    window.dispatchEvent(
      new CustomEvent('synapse:portable-preferences', {
        detail: { sessions_quick_actions_collapsed: collapsed },
      })
    );
  }
}

