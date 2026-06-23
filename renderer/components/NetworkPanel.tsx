// Network bind panel (v0.1.35 · Settings).
//
// Surfaces the daemon's current listen interface, the LAN IPs the
// mobile UI can be reached on, and the persisted bind_lan preference.
// Toggling the preference writes to the boot-config file; the daemon
// has to restart for the new bind to take effect (uvicorn doesn't
// rebind live).
//
// For off-LAN access we point the user at Cloudtap rather than
// trying to ship a second tunneling story.

import { useEffect, useState } from 'react';
import {
  AlertTriangle,
  Cloud,
  Copy,
  ExternalLink,
  Loader2,
  RefreshCw,
  Trash2,
  Wifi,
  WifiOff,
} from 'lucide-react';

import { SynapseApiError } from '@shared/api-client';
import { canRestart, restartApp } from '@shared/electron-bridge';
import { getTool, runToolAction } from '@shared/tools-client';
import { openExternal } from '@shared/electron-bridge';
import type { ToolEntry } from '@shared/generated-types';
import {
  getNetworkStatus,
  patchNetworkBindLan,
  type NetworkStatus,
} from '../lib/system-client';
import { cn } from '@shared/utils';
import { Button } from './ui/button';
import { Card } from './ui/card';

export function NetworkPanel(): JSX.Element {
  const [status, setStatus] = useState<NetworkStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [unsupported, setUnsupported] = useState(false);
  const [busy, setBusy] = useState(false);
  const [justCopied, setJustCopied] = useState<string | null>(null);
  // WAN via Cloudtap (v0.1.36). We look up the cloudtap tool's state
  // on mount + on every change to find the tunnel whose port == the
  // daemon's bound port. The tool is the source of truth; we just
  // surface a focused button up here so users don't have to navigate
  // to Tools → Cloudtap.
  const [cloudtap, setCloudtap] = useState<ToolEntry | null>(null);
  const [tunnelBusy, setTunnelBusy] = useState(false);
  const [tunnelError, setTunnelError] = useState<string | null>(null);

  async function refreshCloudtap(): Promise<void> {
    try {
      setCloudtap(await getTool('cloudtap'));
    } catch {
      // Pre-v0.1.9 daemon won't have cloudtap loaded; quietly null out.
      setCloudtap(null);
    }
  }

  useEffect(() => {
    void refreshCloudtap();
  }, []);

  // The active tunnel for the daemon port (if any).
  const daemonPort = status?.bound_port ?? 7878;
  const daemonTunnel = cloudtap?.state.items.find(
    (item) => (item.result.local_port as number | undefined) === daemonPort
  );
  const daemonTunnelUrl =
    typeof daemonTunnel?.result.public_url === 'string'
      ? (daemonTunnel.result.public_url as string)
      : null;
  const daemonTunnelMobileUrl =
    daemonTunnelUrl ? `${daemonTunnelUrl.replace(/\/+$/, '')}/mobile` : null;

  async function openTunnel(): Promise<void> {
    setTunnelBusy(true);
    setTunnelError(null);
    try {
      const next = await runToolAction('cloudtap', 'tunnel', {
        port: status?.bound_port ?? 7878,
      });
      setCloudtap(next);
    } catch (err) {
      setTunnelError((err as Error).message || 'Could not open tunnel.');
    } finally {
      setTunnelBusy(false);
    }
  }

  async function closeTunnel(itemId: string): Promise<void> {
    setTunnelBusy(true);
    setTunnelError(null);
    try {
      const next = await runToolAction('cloudtap', 'close', {}, itemId);
      setCloudtap(next);
    } catch (err) {
      setTunnelError((err as Error).message || 'Could not close tunnel.');
    } finally {
      setTunnelBusy(false);
    }
  }

  async function refreshTunnel(itemId: string): Promise<void> {
    // Close + reopen so the user gets a fresh URL if the previous
    // session expired or got blocked.
    setTunnelBusy(true);
    setTunnelError(null);
    try {
      await runToolAction('cloudtap', 'close', {}, itemId);
      const next = await runToolAction('cloudtap', 'tunnel', {
        port: status?.bound_port ?? 7878,
      });
      setCloudtap(next);
    } catch (err) {
      setTunnelError((err as Error).message || 'Could not refresh tunnel.');
    } finally {
      setTunnelBusy(false);
    }
  }

  async function refresh(): Promise<void> {
    setError(null);
    setUnsupported(false);
    try {
      setStatus(await getNetworkStatus());
    } catch (err) {
      // A 404 means we're talking to a pre-v0.1.35 daemon that doesn't
      // ship the /system/network route. Show a friendly upgrade hint
      // instead of the raw envelope message.
      if (err instanceof SynapseApiError && err.status === 404) {
        setUnsupported(true);
      } else {
        setError((err as Error).message || 'Failed to load network status');
      }
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  async function toggle(bindLan: boolean): Promise<void> {
    setBusy(true);
    setError(null);
    try {
      await patchNetworkBindLan(bindLan);
      await refresh();
    } catch (err) {
      setError((err as Error).message || 'Failed to update');
    } finally {
      setBusy(false);
    }
  }

  async function copy(text: string): Promise<void> {
    try {
      await navigator.clipboard.writeText(text);
      setJustCopied(text);
      setTimeout(() => setJustCopied(null), 1500);
    } catch {
      /* clipboard blocked -- ignore */
    }
  }

  const isLan = status?.bound_host === '0.0.0.0';

  return (
    <Card className='flex flex-col gap-4 p-6'>
      <div className='flex items-start justify-between gap-3'>
        <div>
          <h2 className='text-lg font-semibold'>Network &amp; phone access</h2>
          <p className='mt-1 text-sm text-muted-foreground'>
            Same-Wi-Fi pairing + a one-click guide for opening Synapse from
            outside your network.
          </p>
        </div>
        {status &&
          (isLan ? (
            <span
              className='inline-flex items-center gap-1.5 rounded-full bg-status-launched/15 px-2.5 py-0.5 font-mono text-xs text-status-launched'
              title='Bound to 0.0.0.0 -- LAN devices can reach the daemon.'
            >
              <Wifi className='h-3.5 w-3.5' aria-hidden='true' />
              LAN open
            </span>
          ) : (
            <span
              className='inline-flex items-center gap-1.5 rounded-full bg-secondary px-2.5 py-0.5 font-mono text-xs text-muted-foreground'
              title='Bound to 127.0.0.1 -- this computer only.'
            >
              <WifiOff className='h-3.5 w-3.5' aria-hidden='true' />
              Loopback only
            </span>
          ))}
      </div>

      {error && (
        <p role='alert' className='text-sm text-destructive'>
          {error}
        </p>
      )}

      {unsupported && (
        <div className='flex items-start gap-2 rounded border border-amber-500/40 bg-amber-500/10 p-3 text-xs text-amber-200'>
          <AlertTriangle className='mt-0.5 h-3.5 w-3.5 shrink-0' aria-hidden='true' />
          <div>
            <p className='font-semibold'>Daemon too old</p>
            <p>
              This panel needs daemon <code className='font-mono'>v0.1.35</code>{' '}
              or newer. Restart Synapse — the bundled daemon will upgrade
              automatically. Until then the existing <code className='font-mono'>--bind-lan</code>{' '}
              CLI flag still works.
            </p>
          </div>
        </div>
      )}

      {!status && !error && !unsupported && (
        <div className='flex items-center gap-2 py-2 text-sm text-muted-foreground'>
          <Loader2 className='h-4 w-4 animate-spin' /> Loading…
        </div>
      )}

      {status && (
        <>
          {/* LAN exposure toggle */}
          <div className='flex flex-col gap-2 rounded-md border border-border bg-secondary/30 p-3'>
            <div className='flex items-center justify-between gap-3'>
              <div>
                <p className='text-sm font-medium'>Allow LAN access</p>
                <p className='text-xs text-muted-foreground'>
                  When on, the daemon binds <code className='font-mono'>0.0.0.0</code>
                  {' '}so other devices on this Wi-Fi can reach it. Off (default):
                  loopback only.
                </p>
              </div>
              <button
                type='button'
                role='switch'
                aria-checked={status.bind_lan_persisted}
                disabled={busy}
                onClick={() => void toggle(!status.bind_lan_persisted)}
                className={cn(
                  'relative h-6 w-11 shrink-0 rounded-full transition-colors disabled:opacity-50',
                  status.bind_lan_persisted ? 'bg-primary' : 'bg-secondary'
                )}
              >
                <span
                  className={cn(
                    'absolute top-1 h-4 w-4 rounded-full bg-card transition-all',
                    status.bind_lan_persisted ? 'left-6' : 'left-1'
                  )}
                />
              </button>
            </div>
            {status.restart_required && (
              <div className='flex items-start justify-between gap-2 rounded border border-amber-500/40 bg-amber-500/10 px-2 py-1.5 text-xs text-amber-200'>
                <div className='flex items-start gap-2'>
                  <AlertTriangle className='mt-0.5 h-3.5 w-3.5 shrink-0' aria-hidden='true' />
                  <span>
                    Restart required to apply.{' '}
                    {canRestart()
                      ? 'Click Restart now or use Tray → Restart Synapse.'
                      : 'Right-click the tray icon → Restart Synapse (or Exit Synapse and relaunch).'}
                  </span>
                </div>
                {canRestart() && (
                  <Button
                    variant='outline'
                    size='sm'
                    className='h-7 shrink-0 px-2 text-xs'
                    onClick={() => void restartApp()}
                    aria-label='Restart Synapse now'
                  >
                    Restart now
                  </Button>
                )}
              </div>
            )}
          </div>

          {/* Phone URLs */}
          <div className='flex flex-col gap-2'>
            <h3 className='text-sm font-semibold'>Open from a phone</h3>
            {isLan ? (
              status.mobile_urls.length > 0 ? (
                <ul className='flex flex-col gap-1.5'>
                  {status.mobile_urls.map((url) => (
                    <li
                      key={url}
                      className='flex items-center justify-between gap-2 rounded border border-border bg-secondary/30 px-3 py-1.5 font-mono text-xs'
                    >
                      <span className='truncate text-foreground'>{url}</span>
                      <Button
                        variant='ghost'
                        size='sm'
                        className='h-7 px-2 text-xs'
                        onClick={() => void copy(url)}
                        aria-label={`Copy ${url} to clipboard`}
                        title='Copy URL'
                      >
                        <Copy className='h-3 w-3' aria-hidden='true' />
                        {justCopied === url ? 'Copied' : 'Copy'}
                      </Button>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className='text-xs text-muted-foreground'>
                  LAN bind is on, but the daemon couldn't detect any LAN IPs.
                  Open Settings → Pair a device and enter the 6-digit code on
                  your phone after it reaches{' '}
                  <code className='font-mono'>http://&lt;your-LAN-IP&gt;:{status.bound_port}/mobile</code>.
                </p>
              )
            ) : (
              <p className='text-xs text-muted-foreground'>
                LAN bind is off. Toggle "Allow LAN access" above and restart
                the daemon. Then a phone on the same Wi-Fi opens one of the
                URLs we'll list here.
              </p>
            )}
          </div>

          {/* Off-LAN via Cloudtap (v0.1.36) */}
          <div className='flex flex-col gap-2 border-t border-border pt-3'>
            <div className='flex items-start justify-between gap-3'>
              <div>
                <h3 className='flex items-center gap-2 text-sm font-semibold'>
                  <Cloud className='h-3.5 w-3.5 text-primary' aria-hidden='true' />
                  Open from outside your network
                </h3>
                <p className='mt-0.5 text-xs text-muted-foreground'>
                  One click opens a public{' '}
                  <code className='font-mono'>*.trycloudflare.com</code> URL
                  forwarding to port{' '}
                  <code className='font-mono'>{status.bound_port}</code>. Works
                  from cellular / any network. Tunnel auto-expires in 24 h
                  unless you refresh it.
                </p>
              </div>
              {daemonTunnel ? (
                <span
                  className='inline-flex shrink-0 items-center gap-1.5 rounded-full bg-status-launched/15 px-2.5 py-0.5 font-mono text-xs text-status-launched'
                  title='Tunnel is active'
                >
                  <span className='h-1.5 w-1.5 animate-pulse rounded-full bg-status-launched' />
                  Active
                </span>
              ) : (
                <span className='inline-flex shrink-0 items-center gap-1.5 rounded-full bg-secondary px-2.5 py-0.5 font-mono text-xs text-muted-foreground'>
                  <span className='h-1.5 w-1.5 rounded-full bg-muted-foreground' />
                  Inactive
                </span>
              )}
            </div>
            {tunnelError && (
              <p role='alert' className='text-xs text-destructive'>
                {tunnelError}
              </p>
            )}
            {!cloudtap && (
              <div className='flex flex-col gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-xs text-amber-200'>
                <p>
                  <strong className='text-foreground'>Cloudtap isn't loaded.</strong>{' '}
                  It's the tunnel handler that opens the public URL. Install
                  it once and Synapse can route phones over WAN from this
                  panel directly.
                </p>
                <Button
                  variant='outline'
                  size='sm'
                  className='w-fit'
                  onClick={() => {
                    window.dispatchEvent(
                      new CustomEvent('synapse:navigate', {
                        detail: { page: 'tools', tab: 'browse', focusId: 'cloudtap' },
                      })
                    );
                  }}
                  aria-label='Go to Tools to install Cloudtap'
                >
                  <ExternalLink className='h-3.5 w-3.5' aria-hidden='true' />
                  Install Cloudtap in Tools
                </Button>
              </div>
            )}
            {cloudtap && !daemonTunnel && (
              <Button
                variant='outline'
                size='sm'
                className='w-fit'
                disabled={tunnelBusy}
                onClick={() => void openTunnel()}
              >
                {tunnelBusy ? (
                  <Loader2 className='h-4 w-4 animate-spin' aria-hidden='true' />
                ) : (
                  <Cloud className='h-4 w-4' aria-hidden='true' />
                )}
                Expose to WAN via Cloudtap
              </Button>
            )}
            {cloudtap && daemonTunnel && (
              <div className='flex flex-col gap-2 rounded-md border border-border bg-secondary/30 p-3'>
                <div className='flex items-center justify-between gap-2'>
                  <button
                    type='button'
                    onClick={() =>
                      daemonTunnelMobileUrl &&
                      void openExternal(daemonTunnelMobileUrl)
                    }
                    className='flex min-w-0 items-center gap-1.5 font-mono text-xs text-primary hover:underline'
                    title='Open in browser'
                  >
                    <ExternalLink className='h-3 w-3 shrink-0' aria-hidden='true' />
                    <span className='truncate'>
                      {daemonTunnelMobileUrl ?? 'opening…'}
                    </span>
                  </button>
                  <div className='flex shrink-0 items-center gap-1'>
                    {daemonTunnelMobileUrl && (
                      <Button
                        variant='ghost'
                        size='sm'
                        className='h-7 px-2 text-xs'
                        onClick={() => void copy(daemonTunnelMobileUrl)}
                        aria-label='Copy tunnel URL to clipboard'
                        title='Copy URL'
                      >
                        {justCopied === daemonTunnelMobileUrl ? (
                          <span className='text-xs'>Copied</span>
                        ) : (
                          <Copy className='h-3 w-3' aria-hidden='true' />
                        )}
                      </Button>
                    )}
                    <Button
                      variant='ghost'
                      size='sm'
                      className='h-7 px-2 text-xs'
                      onClick={() => void refreshTunnel(daemonTunnel.id)}
                      disabled={tunnelBusy}
                      aria-label='Refresh tunnel (close + reopen with a new URL)'
                      title='Close + reopen with a new URL'
                    >
                      <RefreshCw className='h-3 w-3' aria-hidden='true' />
                    </Button>
                    <Button
                      variant='ghost'
                      size='sm'
                      className='h-7 px-2 text-xs text-destructive hover:bg-destructive/10'
                      onClick={() => void closeTunnel(daemonTunnel.id)}
                      disabled={tunnelBusy}
                      aria-label='Close tunnel'
                      title='Close tunnel'
                    >
                      <Trash2 className='h-3 w-3' aria-hidden='true' />
                    </Button>
                  </div>
                </div>
                <p className='text-[11px] text-muted-foreground'>
                  <strong className='text-foreground'>Security:</strong> the
                  tunnel is read-only without a device token. Pair the phone
                  over LAN first, then tap <strong className='text-foreground'>Use on this phone</strong>{' '}
                  in the mobile Cloudtap card to carry that token into the
                  tunnel origin. You can also pair directly on the tunnel URL
                  with a fresh 6-digit code. Cloudflare quick tunnels live ~24 h;
                  use the refresh button for a fresh URL after that.
                </p>
              </div>
            )}
          </div>
        </>
      )}
    </Card>
  );
}
