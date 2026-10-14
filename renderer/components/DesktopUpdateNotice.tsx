import { useEffect, useState } from 'react';
import { Download, RefreshCw, X } from 'lucide-react';
import { checkDesktopUpdate, installDesktopUpdate, type DesktopUpdateInfo } from '../lib/electron-bridge';

/** Nonblocking notification. Never promise daemon continuity until the installer guarantees it. */
export function DesktopUpdateNotice(): JSX.Element | null {
  const [update, setUpdate] = useState<DesktopUpdateInfo | null>(null);
  const [hiddenVersion, setHiddenVersion] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  useEffect(() => {
    let active = true;
    const check = () => {
      void checkDesktopUpdate().then((result) => {
        if (active && result) setUpdate(result);
      }).catch(() => undefined);
    };
    check();
    const timer = window.setInterval(check, 6 * 60 * 60 * 1000);
    return () => { active = false; window.clearInterval(timer); };
  }, []);
  if (!update || update.status !== 'available' || !update.version || update.version === hiddenVersion) return null;
  return (
    <aside role='status' aria-label='Synapse update available' className='flex flex-wrap items-center gap-3 border-b border-cyan-500/25 bg-cyan-950/40 px-5 py-3 text-sm text-foreground'>
      <RefreshCw className='h-4 w-4 shrink-0 text-cyan-300' aria-hidden='true' />
      <div className='min-w-[220px] flex-1'>
        <strong>Synapse v{update.version} is available</strong>
        <p className='text-xs text-muted-foreground'>The installer will be verified before opening. Your running services will not be stopped by this notification; the installer will explain any restart requirements.</p>
        {message && <p className='mt-1 text-xs' role='alert'>{message}</p>}
      </div>
      <button type='button' disabled={busy} onClick={() => {
        setBusy(true); setMessage(null);
        void installDesktopUpdate().then((result) => {
          setMessage(result.ok ? 'Verified installer opened. Complete the installation in Windows when ready.' : result.error ?? 'Unable to start update.');
        }).catch((error) => setMessage(String(error))).finally(() => setBusy(false));
      }} className='inline-flex items-center gap-2 rounded-lg bg-cyan-500 px-3 py-2 font-semibold text-slate-950 hover:bg-cyan-400 disabled:opacity-50'>
        <Download className='h-4 w-4' aria-hidden='true' />{busy ? 'Verifying update...' : 'Download & Update'}
      </button>
      <button type='button' aria-label='Remind me later' onClick={() => setHiddenVersion(update.version ?? null)} className='rounded-lg p-2 hover:bg-white/10'><X className='h-4 w-4' /></button>
    </aside>
  );
}
