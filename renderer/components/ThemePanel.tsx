// Theme panel (Contract #14 · v0.1.18) -- Settings page.
//
// Light / Dark / System chooser. Choice is persisted in localStorage and
// re-applied on next launch. In 'system' mode Synapse follows the OS.

import { useState } from 'react';
import { Monitor, Moon, Sun } from 'lucide-react';

import { applyTheme, getStoredTheme, setStoredTheme, type Theme } from '@shared/theme';
import { cn } from '@shared/utils';
import { Card } from './ui/card';

const OPTIONS: Array<{ id: Theme; label: string; icon: typeof Sun }> = [
  { id: 'light', label: 'Light', icon: Sun },
  { id: 'dark', label: 'Dark', icon: Moon },
  { id: 'system', label: 'System', icon: Monitor },
];

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
          Synapse is dark by default. Switch to light, or follow your OS.
        </p>
      </div>
      <div
        role='radiogroup'
        aria-label='Theme'
        className='inline-flex w-fit gap-1 rounded-lg border border-border bg-secondary/30 p-1'
      >
        {OPTIONS.map((opt) => {
          const Icon = opt.icon;
          const selected = theme === opt.id;
          return (
            <button
              key={opt.id}
              type='button'
              role='radio'
              aria-checked={selected}
              onClick={() => pick(opt.id)}
              className={cn(
                'flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors',
                selected
                  ? 'bg-card text-foreground shadow-sm'
                  : 'text-muted-foreground hover:text-foreground'
              )}
            >
              <Icon className='h-4 w-4' />
              {opt.label}
            </button>
          );
        })}
      </div>
    </Card>
  );
}
