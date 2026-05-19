// Startup panel (Milestone I · v0.1.13) -- Settings page.
//
// Toggles whether Synapse registers itself as a Windows login item. Only
// works inside the Electron app (the daemon + tray live there); in a plain
// browser the control is shown disabled with an explanation.

import { useEffect, useState } from 'react';
import { Power } from 'lucide-react';

import { canManageAutostart, getAutostart, setAutostart } from '@shared/electron-bridge';
import { cn } from '@shared/utils';
import { Card } from './ui/card';

export function StartupPanel(): JSX.Element {
  const available = canManageAutostart();
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!available) return;
    void getAutostart().then((v) => setEnabled(v ?? false));
  }, [available]);

  async function toggle(): Promise<void> {
    if (busy || enabled === null) return;
    setBusy(true);
    const next = !enabled;
    try {
      const result = await setAutostart(next);
      setEnabled(result ?? next);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className='flex flex-col gap-4 p-6'>
      <div>
        <h2 className='text-lg font-semibold'>Startup</h2>
        <p className='mt-1 text-sm text-muted-foreground'>
          Launch Synapse automatically when you sign in to Windows — the tray icon appears
          and the daemon is ready before you even open the window.
        </p>
      </div>

      <div className='flex items-center justify-between gap-4'>
        <div className='flex items-center gap-2 text-sm'>
          <Power className='h-4 w-4 text-muted-foreground' />
          Start Synapse when Windows starts
        </div>
        {available ? (
          <button
            type='button'
            role='switch'
            aria-checked={enabled === true}
            disabled={busy || enabled === null}
            onClick={() => void toggle()}
            className={cn(
              'relative h-6 w-11 shrink-0 rounded-full transition-colors disabled:opacity-50',
              enabled ? 'bg-primary' : 'bg-secondary'
            )}
          >
            <span
              className={cn(
                'absolute top-0.5 h-5 w-5 rounded-full bg-background transition-transform',
                enabled ? 'translate-x-[22px]' : 'translate-x-0.5'
              )}
            />
          </button>
        ) : (
          <span className='text-xs text-muted-foreground'>Desktop app only</span>
        )}
      </div>
    </Card>
  );
}
