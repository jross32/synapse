// Theme controller (Contract #14 · v0.1.18 · expanded v0.1.36).
//
// Synapse is dark by default. The user can opt into named colour
// themes (dark, light, hacker, surfer) or follow the OS ("system"
// = light/dark only). Choice is remembered in localStorage and
// applied by toggling `html.theme-<name>` classes -- styles.css owns
// the actual palette.

export type Theme = 'light' | 'dark' | 'system' | 'hacker' | 'surfer';

export interface ThemeOption {
  id: Theme;
  label: string;
  description: string;
  /** Optional swatch colour for the picker, expressed as an HSL string. */
  swatch?: string;
}

export const THEME_OPTIONS: ThemeOption[] = [
  {
    id: 'dark',
    label: 'Dark (Synapse purple)',
    description: 'Default. Deep blue surfaces, purple accents.',
    swatch: '263 83% 58%',
  },
  {
    id: 'light',
    label: 'Light',
    description: 'Inverted palette for bright rooms.',
    swatch: '210 40% 92%',
  },
  {
    id: 'system',
    label: 'Match system',
    description: 'Follows the OS preference between Dark and Light.',
  },
  {
    id: 'hacker',
    label: 'Hacker green',
    description: 'Near-black surfaces with neon green accents.',
    swatch: '142 80% 50%',
  },
  {
    id: 'surfer',
    label: 'Surfer blue',
    description: 'Bright ocean blues over a deep navy.',
    swatch: '198 90% 60%',
  },
];

const STORAGE_KEY = 'synapse.theme';
const LIGHT_QUERY = '(prefers-color-scheme: light)';
const KNOWN: ReadonlySet<Theme> = new Set([
  'light',
  'dark',
  'system',
  'hacker',
  'surfer',
]);

export function getStoredTheme(): Theme {
  try {
    const value = window.localStorage.getItem(STORAGE_KEY);
    if (value && KNOWN.has(value as Theme)) return value as Theme;
  } catch {
    // localStorage disabled / SSR -- fall through to default.
  }
  return 'dark';
}

export function setStoredTheme(
  theme: Theme,
  options?: { emit?: boolean }
): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, theme);
  } catch {
    /* ignore */
  }
  if (options?.emit !== false && typeof window !== 'undefined') {
    window.dispatchEvent(
      new CustomEvent('synapse:portable-preferences', {
        detail: { theme },
      })
    );
  }
}

function osPrefersLight(): boolean {
  return typeof window !== 'undefined' && window.matchMedia(LIGHT_QUERY).matches;
}

/**
 * Resolve "system" to the effective concrete theme (light or dark).
 * Used by applyTheme; exported so other surfaces can read the live
 * answer.
 */
export function resolveEffectiveTheme(
  theme: Theme
): Exclude<Theme, 'system'> {
  if (theme === 'system') return osPrefersLight() ? 'light' : 'dark';
  return theme;
}

/** Apply the chosen theme to the document. Re-running is idempotent. */
export function applyTheme(theme: Theme): void {
  if (typeof document === 'undefined') return;
  const effective = resolveEffectiveTheme(theme);
  const root = document.documentElement;
  // Remove every theme-* class first; flip the legacy 'light' class
  // off too so we don't end up with two conflicting palettes.
  root.classList.remove(
    'light',
    'theme-light',
    'theme-dark',
    'theme-hacker',
    'theme-surfer'
  );
  if (effective === 'dark') {
    // Default palette = no class needed; add 'theme-dark' so CSS
    // using `html.theme-dark` selectors keeps working symmetrically.
    root.classList.add('theme-dark');
  } else {
    root.classList.add(`theme-${effective}`);
  }
  // Legacy class for the body color-scheme switch in styles.css.
  if (effective === 'light') root.classList.add('light');
}

/** Subscribe to OS theme changes; only useful in 'system' mode.
 *  Returns a teardown function. */
export function watchOsTheme(handler: () => void): () => void {
  if (typeof window === 'undefined') return () => undefined;
  const mq = window.matchMedia(LIGHT_QUERY);
  mq.addEventListener('change', handler);
  return () => mq.removeEventListener('change', handler);
}
