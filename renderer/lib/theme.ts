// Theme controller (Contract #14 · v0.1.18).
//
// Synapse is dark by default. The user can opt into a light theme or follow
// the OS via Settings → Theme. Choice is remembered in localStorage and
// applied by toggling `html.light` -- styles.css owns the actual palette.

export type Theme = 'light' | 'dark' | 'system';

const STORAGE_KEY = 'synapse.theme';
const LIGHT_QUERY = '(prefers-color-scheme: light)';

export function getStoredTheme(): Theme {
  try {
    const value = window.localStorage.getItem(STORAGE_KEY);
    if (value === 'light' || value === 'dark' || value === 'system') return value;
  } catch {
    // localStorage disabled / SSR — fall through to default.
  }
  return 'dark';
}

export function setStoredTheme(theme: Theme): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, theme);
  } catch {
    /* ignore */
  }
}

function osPrefersLight(): boolean {
  return typeof window !== 'undefined' && window.matchMedia(LIGHT_QUERY).matches;
}

/** Apply the chosen theme to the document. Re-running is idempotent. */
export function applyTheme(theme: Theme): void {
  if (typeof document === 'undefined') return;
  const isLight = theme === 'light' || (theme === 'system' && osPrefersLight());
  document.documentElement.classList.toggle('light', isLight);
}

/** Subscribe to OS theme changes; the listener is only useful in 'system' mode.
 *  Returns a teardown function. */
export function watchOsTheme(handler: () => void): () => void {
  if (typeof window === 'undefined') return () => undefined;
  const mq = window.matchMedia(LIGHT_QUERY);
  mq.addEventListener('change', handler);
  return () => mq.removeEventListener('change', handler);
}
