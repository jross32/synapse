// Theme panel (Contract #14 · v0.1.18 · expanded v0.1.36) -- Settings.
//
// Light / Dark / System chooser plus named colour themes (Hacker green,
// Surfer blue). Choice is persisted in localStorage + re-applied on
// next launch. In 'system' mode Synapse follows the OS between
// Light and Dark only -- named themes are explicit picks.

import { useState } from 'react';
import { Check, Monitor, Moon, Palette, Sun } from 'lucide-react';

import {
  THEME_OPTIONS,
  applyTheme,
  getStoredTheme,
  setStoredTheme,
  type Theme,
} from '@shared/theme';
import { cn } from '@shared/utils';
import { Card } from './ui/card';

const ICONS: Partial<Record<Theme, typeof Sun>> = {
  light: Sun,
  dark: Moon,
  system: Monitor,
  hacker: Palette,
  surfer: Palette,
};

export function ThemePanel(): JSX.Element {
  const [theme, setTheme] = useState<Theme>(() => getStoredTheme());

  function pick(next: Theme): void {
    setTheme(next);
    setStoredTheme(next);
    applyTheme(next);
  }

  return (
    <Card className='flex flex-col gap-4 p-6'>
      <div>
        <h2 className='text-lg font-semibold'>Theme</h2>
        <p className='mt-1 text-sm text-muted-foreground'>
          Dark by default. Light + System follow standard conventions.
          Named themes (Hacker, Surfer) swap the whole palette for a
          different vibe.
        </p>
      </div>
      <ul
        role='radiogroup'
        aria-label='Theme'
        className='grid grid-cols-1 gap-2 sm:grid-cols-2'
      >
        {THEME_OPTIONS.map((opt) => {
          const Icon = ICONS[opt.id] ?? Palette;
          const selected = theme === opt.id;
          return (
            <li key={opt.id}>
              <button
                type='button'
                role='radio'
                aria-checked={selected}
                onClick={() => pick(opt.id)}
                className={cn(
                  'flex w-full items-center gap-3 rounded-md border px-3 py-2 text-left transition-colors',
                  selected
                    ? 'border-primary bg-secondary/60 ring-1 ring-primary'
                    : 'border-border bg-secondary/30 hover:border-primary/60 hover:bg-secondary/50'
                )}
              >
                {opt.swatch ? (
                  <span
                    aria-hidden='true'
                    className='h-6 w-6 shrink-0 rounded-full border border-border'
                    style={{ backgroundColor: `hsl(${opt.swatch})` }}
                  />
                ) : (
                  <Icon className='h-5 w-5 shrink-0 text-muted-foreground' aria-hidden='true' />
                )}
                <div className='min-w-0 grow'>
                  <div className='flex items-center gap-1.5 text-sm font-medium'>
                    {opt.label}
                    {selected && (
                      <Check
                        className='h-3.5 w-3.5 text-primary'
                        aria-hidden='true'
                      />
                    )}
                  </div>
                  <p className='text-xs text-muted-foreground'>
                    {opt.description}
                  </p>
                </div>
              </button>
            </li>
          );
        })}
      </ul>
    </Card>
  );
}
