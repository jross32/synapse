import { useEffect, useMemo, useRef, useState } from 'react';
import QRCode from 'qrcode';
import {
  AlertTriangle,
  CheckCircle2,
  Cloud,
  Copy,
  ExternalLink,
  Link2,
  Loader2,
  QrCode,
  RefreshCw,
  ShieldCheck,
  Smartphone,
  Trash2,
  Wifi,
  WifiOff,
} from 'lucide-react';

import { useDaemon } from '@shared/daemon-context';
import { formatLocal } from '@shared/format-time';
import {
  createHandoffClaim,
  issuePairingCode,
  revokePairedDevice,
} from '@shared/pairing-client';
import {
  getRemoteAccessStatus,
  type RemoteAccessDevice,
  type RemoteAccessStatus,
} from '@shared/remote-access-client';
import { canRestart, openExternal, restartApp } from '@shared/electron-bridge';
import { runToolAction } from '@shared/tools-client';
import {
  patchNetworkBindLan,
} from '@shared/system-client';
import { Badge } from './ui/badge';
import { Button } from './ui/button';
import { Card } from './ui/card';
import { Modal } from './ui/modal';

type ReconnectTarget = 'lan' | 'wan';

interface ReconnectPreview {
  device: RemoteAccessDevice;
  target: ReconnectTarget;
  url: string;
  expiresAt: string;
  qrDataUrl: string | null;
}

export function PhoneAccessPanel(): JSX.Element {
  const { recentEvents } = useDaemon();
  const [status, setStatus] = useState<RemoteAccessStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [tunnelBusy, setTunnelBusy] = useState(false);
  const [justCopied, setJustCopied] = useState<string | null>(null);
  const [banner, setBanner] = useState<string | null>(null);
  const [reconnectPreview, setReconnectPreview] = useState<ReconnectPreview | null>(null);
  const [nowTick, setNowTick] = useState(() => Date.now());
  const seenEventId = useRef(0);

  async function refresh(): Promise<void> {
    setError(null);
    try {
      const next = await getRemoteAccessStatus();
      setStatus(next);
    } catch (err) {
      setError((err as Error).message || 'Could not load phone access.');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    seenEventId.current = recentEvents.reduce((max, event) => Math.max(max, event.id), 0);
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const timer = window.setInterval(() => setNowTick(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!status?.wan.active) return;
    if (status.wan.verification.status === 'ready') return;
    const timer = window.setTimeout(() => {
      void refresh();
    }, 5000);
    return () => window.clearTimeout(timer);
  }, [status]);

  useEffect(() => {
    const fresh = recentEvents.filter(
      (event) =>
        event.id > seenEventId.current &&
        (event.name.startsWith('v1.device.') ||
          event.name.startsWith('v1.remote_access.') ||
          event.name.startsWith('v1.tool.'))
    );
    if (fresh.length === 0) return;
    seenEventId.current = recentEvents.reduce((max, event) => Math.max(max, event.id), seenEventId.current);
    const newest = fresh[0];
    const payload = (newest.payload ?? {}) as { device_name?: unknown };
    if (status && newest.name === 'v1.device.paired') {
      const deviceName =
        typeof payload.device_name === 'string' ? payload.device_name : 'device';
      setBanner(`Successfully paired into ${status.computer_name} using ${deviceName}.`);
      window.setTimeout(() => setBanner(null), 4500);
    }
    if (status && newest.name === 'v1.device.reconnected') {
      const deviceName =
        typeof payload.device_name === 'string' ? payload.device_name : 'device';
      setBanner(`Secure reconnect issued for ${deviceName} on ${status.computer_name}.`);
      window.setTimeout(() => setBanner(null), 4500);
    }
    void refresh();
  }, [recentEvents, status]);

  const preferredPairUrl = useMemo(() => {
    if (!status) return null;
    if (status.network.mobile_urls[0]) return status.network.mobile_urls[0];
    if (status.wan.public_url && status.wan.verification.status === 'ready') {
      return `${status.wan.public_url.replace(/\/+$/, '')}/mobile`;
    }
    return null;
  }, [status]);

  const pairCodeRemaining = useMemo(() => {
    if (!status?.pairing_code.expires_at) return null;
    const ms = new Date(status.pairing_code.expires_at).getTime() - nowTick;
    if (ms <= 0) return '0:00';
    const seconds = Math.floor(ms / 1000);
    return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
  }, [nowTick, status?.pairing_code.expires_at]);

  async function copy(text: string): Promise<void> {
    try {
      await navigator.clipboard.writeText(text);
      setJustCopied(text);
      window.setTimeout(() => setJustCopied(null), 1400);
    } catch {
      /* clipboard unavailable */
    }
  }

  async function generatePairCode(): Promise<void> {
    setBusy('pair-code');
    setError(null);
    try {
      await issuePairingCode();
      await refresh();
    } catch (err) {
      setError((err as Error).message || 'Could not generate a pairing code.');
    } finally {
      setBusy(null);
    }
  }

  async function toggleLan(bindLan: boolean): Promise<void> {
    setBusy('lan-toggle');
    setError(null);
    try {
      await patchNetworkBindLan(bindLan);
      await refresh();
    } catch (err) {
      setError((err as Error).message || 'Could not update LAN access.');
    } finally {
      setBusy(null);
    }
  }

  async function revokeDevice(device: RemoteAccessDevice): Promise<void> {
    setBusy(`revoke:${device.id}`);
    setError(null);
    try {
      await revokePairedDevice(device.id);
      await refresh();
    } catch (err) {
      setError((err as Error).message || `Could not revoke ${device.name}.`);
    } finally {
      setBusy(null);
    }
  }

  async function openTunnel(): Promise<void> {
    if (!status) return;
    setTunnelBusy(true);
    setError(null);
    try {
      await runToolAction('cloudtap', 'tunnel', { port: status.network.bound_port });
      await refresh();
    } catch (err) {
      setError((err as Error).message || 'Could not open the Cloudtap tunnel.');
    } finally {
      setTunnelBusy(false);
    }
  }

  async function refreshTunnel(): Promise<void> {
    if (!status?.wan.tunnel_id) return;
    setTunnelBusy(true);
    setError(null);
    try {
      await runToolAction('cloudtap', 'close', {}, status.wan.tunnel_id);
      await runToolAction('cloudtap', 'tunnel', { port: status.network.bound_port });
      await refresh();
    } catch (err) {
      setError((err as Error).message || 'Could not refresh the WAN tunnel.');
    } finally {
      setTunnelBusy(false);
    }
  }

  async function closeTunnel(): Promise<void> {
    if (!status?.wan.tunnel_id) return;
    setTunnelBusy(true);
    setError(null);
    try {
      await runToolAction('cloudtap', 'close', {}, status.wan.tunnel_id);
      await refresh();
    } catch (err) {
      setError((err as Error).message || 'Could not close the WAN tunnel.');
    } finally {
      setTunnelBusy(false);
    }
  }

  async function installCloudtap(): Promise<void> {
    window.dispatchEvent(
      new CustomEvent('synapse:navigate', {
        detail: { page: 'tools', tab: 'discover', focusId: 'cloudtap' },
      })
    );
  }

  async function createReconnectPreview(
    device: RemoteAccessDevice,
    target: ReconnectTarget
  ): Promise<void> {
    if (!status) return;
    const baseUrl =
      target === 'wan'
        ? status.wan.public_url
        : status.network.mobile_urls[0] ?? null;
    if (!baseUrl) {
      setError(
        target === 'wan'
          ? 'Open a verified WAN tunnel first.'
          : 'Turn on LAN access and restart Synapse first.'
      );
      return;
    }

    setBusy(`claim:${device.id}:${target}`);
    setError(null);
    try {
      const claim = await createHandoffClaim(device.id);
      const mobileBase =
        target === 'wan' ? `${baseUrl.replace(/\/+$/, '')}/mobile` : baseUrl;
      const url = `${mobileBase}?handoff=${Date.now()}#synapseClaim=${encodeURIComponent(claim.claim)}`;
      const qrDataUrl = await QRCode.toDataURL(url, {
        width: 220,
        margin: 1,
        color: { dark: '#0b0f17', light: '#ffffff' },
      });
      setReconnectPreview({
        device,
        target,
        url,
        expiresAt: claim.expires_at,
        qrDataUrl,
      });
    } catch (err) {
      setError((err as Error).message || 'Could not create a reconnect link.');
    } finally {
      setBusy(null);
    }
  }

  if (loading) {
    return (
      <Card className='flex items-center gap-2 p-6 text-sm text-muted-foreground'>
        <Loader2 className='h-4 w-4 animate-spin' /> Loading phone access...
      </Card>
    );
  }

  if (!status) {
    return (
      <Card className='space-y-3 p-6'>
        <h2 className='text-lg font-semibold'>Phone Access</h2>
        <p className='text-sm text-destructive'>{error ?? 'Phone access is unavailable right now.'}</p>
      </Card>
    );
  }

  const wanReady = status.wan.verification.status === 'ready';
  const lanOpen = status.network.bound_host === '0.0.0.0';

  return (
    <>
      <Card className='overflow-hidden border-border/70 p-0'>
        <div className='relative overflow-hidden bg-gradient-to-br from-card via-card to-secondary/30 p-6'>
          <div className='absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-primary via-sky-400 to-emerald-400' />
          <div className='flex flex-col gap-6'>
            <div className='flex flex-wrap items-start justify-between gap-4'>
              <div className='space-y-2'>
                <div className='flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.2em] text-primary/85'>
                  <Smartphone className='h-3.5 w-3.5' />
                  Phone Access
                </div>
                <div>
                  <h2 className='text-2xl font-semibold tracking-tight'>
                    Pair once, reconnect cleanly, and move from LAN to WAN without friction
                  </h2>
                  <p className='mt-1 max-w-3xl text-sm text-muted-foreground'>
                    Synapse now treats phone access like a first-class remote-control surface:
                    durable device trust, secure reconnect links, and live WAN verification for Cloudtap.
                  </p>
                </div>
              </div>
              <div className='flex flex-wrap items-center gap-2'>
                <StatusPill icon={lanOpen ? Wifi : WifiOff} label={lanOpen ? 'LAN open' : 'LAN off'} tone={lanOpen ? 'good' : 'muted'} />
                <StatusPill
                  icon={Cloud}
                  label={
                    !status.wan.available
                      ? 'Cloudtap missing'
                      : wanReady
                        ? 'WAN verified'
                        : status.wan.active
                          ? 'WAN needs attention'
                          : 'WAN inactive'
                  }
                  tone={!status.wan.available ? 'warn' : wanReady ? 'good' : status.wan.active ? 'warn' : 'muted'}
                />
                <StatusPill icon={ShieldCheck} label={`${status.paired_devices.length} paired`} tone='muted' />
              </div>
            </div>

            {banner && (
              <div className='rounded-2xl border border-emerald-500/35 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-200'>
                <div className='flex items-center gap-2 font-medium'>
                  <CheckCircle2 className='h-4 w-4' />
                  {banner}
                </div>
              </div>
            )}

            {error && (
              <div className='rounded-2xl border border-destructive/35 bg-destructive/10 px-4 py-3 text-sm text-destructive'>
                {error}
              </div>
            )}

            <div className='grid gap-4 xl:grid-cols-[1.1fr_0.9fr]'>
              <SectionCard
                title='Pair new device'
                subtitle='Generate a code, open the mobile shell, and watch the phone join in real time.'
                icon={QrCode}
              >
                {status.pairing_code.active ? (
                  <div className='grid gap-4 lg:grid-cols-[1fr_180px]'>
                    <div className='space-y-3'>
                      <div className='rounded-2xl border border-border/70 bg-background/55 p-4'>
                        <p className='text-xs font-semibold uppercase tracking-[0.18em] text-primary/85'>
                          Active pairing code
                        </p>
                        <p className='mt-2 font-mono text-4xl font-semibold tracking-[0.35em]'>
                          {status.pairing_code.code}
                        </p>
                        <p className='mt-2 text-sm text-muted-foreground'>
                          Expires in {pairCodeRemaining ?? '0:00'}
                        </p>
                      </div>
                      <div className='rounded-2xl border border-border/70 bg-secondary/30 p-4 text-sm text-muted-foreground'>
                        {preferredPairUrl ? (
                          <div className='space-y-2'>
                            <p>
                              Open this on the phone, then enter the code above. If LAN is available we prefer it;
                              otherwise the current WAN URL can still pair directly.
                            </p>
                            <div className='flex flex-wrap items-center gap-2'>
                              <code className='rounded-lg bg-background/60 px-2 py-1 font-mono text-[11px] text-foreground'>
                                {preferredPairUrl}
                              </code>
                              <Button
                                type='button'
                                variant='ghost'
                                size='sm'
                                className='h-7 px-2 text-xs'
                                onClick={() => void copy(preferredPairUrl)}
                              >
                                <Copy className='h-3 w-3' />
                                {justCopied === preferredPairUrl ? 'Copied' : 'Copy'}
                              </Button>
                            </div>
                          </div>
                        ) : (
                          <p>
                            Turn on LAN access and restart Synapse, or bring up a verified WAN tunnel, to give the
                            phone a scannable address.
                          </p>
                        )}
                      </div>
                    </div>
                    <PairQrPanel url={preferredPairUrl} />
                  </div>
                ) : (
                  <div className='flex flex-col gap-3 rounded-2xl border border-dashed border-border/70 bg-secondary/20 px-5 py-6 text-center'>
                    <p className='text-sm text-muted-foreground'>
                      No active code right now. Generate one when you&apos;re ready to trust a new phone.
                    </p>
                    <div className='flex flex-wrap justify-center gap-2'>
                      <Button
                        type='button'
                        className='rounded-2xl'
                        onClick={() => void generatePairCode()}
                        disabled={busy === 'pair-code'}
                      >
                        {busy === 'pair-code' ? (
                          <Loader2 className='h-4 w-4 animate-spin' />
                        ) : (
                          <QrCode className='h-4 w-4' />
                        )}
                        Generate 6-digit code
                      </Button>
                    </div>
                  </div>
                )}
              </SectionCard>

              <SectionCard
                title='LAN'
                subtitle='Make Synapse reachable on the same Wi-Fi, then use QR or tap-through links.'
                icon={lanOpen ? Wifi : WifiOff}
              >
                <div className='space-y-4'>
                  <div className='flex items-start justify-between gap-3 rounded-2xl border border-border/70 bg-background/55 p-4'>
                    <div>
                      <p className='text-sm font-medium text-foreground'>Allow LAN access</p>
                      <p className='mt-1 text-xs text-muted-foreground'>
                        When on, Synapse binds <code className='font-mono'>0.0.0.0:{status.network.bound_port}</code> so
                        phones on the same network can reach the mobile shell.
                      </p>
                    </div>
                    <button
                      type='button'
                      role='switch'
                      aria-checked={status.network.bind_lan_persisted}
                      disabled={busy === 'lan-toggle'}
                      onClick={() => void toggleLan(!status.network.bind_lan_persisted)}
                      className={[
                        'relative h-6 w-11 shrink-0 rounded-full transition-colors disabled:opacity-50',
                        status.network.bind_lan_persisted ? 'bg-primary' : 'bg-secondary',
                      ].join(' ')}
                    >
                      <span
                        className={[
                          'absolute top-1 h-4 w-4 rounded-full bg-card transition-all',
                          status.network.bind_lan_persisted ? 'left-6' : 'left-1',
                        ].join(' ')}
                      />
                    </button>
                  </div>

                  {status.network.restart_required && (
                    <div className='flex items-start justify-between gap-3 rounded-2xl border border-amber-500/35 bg-amber-500/10 px-4 py-3 text-sm text-amber-100'>
                      <div className='flex items-start gap-2'>
                        <AlertTriangle className='mt-0.5 h-4 w-4 shrink-0' />
                        <p>
                          Restart Synapse to apply the new bind setting and expose the phone URLs below.
                        </p>
                      </div>
                      {canRestart() && (
                        <Button variant='outline' size='sm' onClick={() => void restartApp()}>
                          Restart now
                        </Button>
                      )}
                    </div>
                  )}

                  {status.network.mobile_urls.length > 0 ? (
                    <div className='space-y-2'>
                      {status.network.mobile_urls.map((url) => (
                        <div
                          key={url}
                          className='flex items-center justify-between gap-2 rounded-2xl border border-border/70 bg-secondary/25 px-3 py-2'
                        >
                          <code className='truncate font-mono text-xs text-foreground'>{url}</code>
                          <Button
                            type='button'
                            variant='ghost'
                            size='sm'
                            className='h-7 px-2 text-xs'
                            onClick={() => void copy(url)}
                          >
                            <Copy className='h-3 w-3' />
                            {justCopied === url ? 'Copied' : 'Copy'}
                          </Button>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className='text-sm text-muted-foreground'>
                      No LAN URL is ready yet. With LAN off, only this computer can reach the daemon.
                    </p>
                  )}
                </div>
              </SectionCard>
            </div>

            <SectionCard
              title='Paired devices'
              subtitle='Trusted devices can reconnect without another 6-digit code unless you revoke them.'
              icon={ShieldCheck}
            >
              {status.paired_devices.length === 0 ? (
                <div className='rounded-2xl border border-dashed border-border/70 bg-secondary/20 px-5 py-6 text-center text-sm text-muted-foreground'>
                  No devices paired yet.
                </div>
              ) : (
                <div className='space-y-3'>
                  {status.paired_devices.map((device) => (
                    <div
                      key={device.id}
                      className='rounded-2xl border border-border/70 bg-background/55 p-4'
                    >
                      <div className='flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between'>
                        <div className='min-w-0'>
                          <div className='flex items-center gap-2'>
                            <Smartphone className='h-4 w-4 text-primary' />
                            <p className='truncate text-sm font-medium text-foreground'>{device.name}</p>
                          </div>
                          <p className='mt-1 text-xs text-muted-foreground'>
                            Last seen{' '}
                            {device.last_seen_at ? formatLocal(device.last_seen_at, 'short') : 'never'} · Paired{' '}
                            {formatLocal(device.created_at, 'short')}
                          </p>
                        </div>
                        <div className='flex flex-wrap gap-2'>
                          <Button
                            type='button'
                            variant='outline'
                            size='sm'
                            className='rounded-xl'
                            disabled={!status.network.mobile_urls[0] || busy === `claim:${device.id}:lan`}
                            onClick={() => void createReconnectPreview(device, 'lan')}
                          >
                            {busy === `claim:${device.id}:lan` ? (
                              <Loader2 className='h-3.5 w-3.5 animate-spin' />
                            ) : (
                              <Link2 className='h-3.5 w-3.5' />
                            )}
                            Reconnect on LAN
                          </Button>
                          <Button
                            type='button'
                            variant='outline'
                            size='sm'
                            className='rounded-xl'
                            disabled={!wanReady || busy === `claim:${device.id}:wan`}
                            onClick={() => void createReconnectPreview(device, 'wan')}
                          >
                            {busy === `claim:${device.id}:wan` ? (
                              <Loader2 className='h-3.5 w-3.5 animate-spin' />
                            ) : (
                              <Cloud className='h-3.5 w-3.5' />
                            )}
                            Reconnect on WAN
                          </Button>
                          <Button
                            type='button'
                            variant='ghost'
                            size='sm'
                            className='rounded-xl text-destructive hover:bg-destructive/10'
                            disabled={busy === `revoke:${device.id}`}
                            onClick={() => void revokeDevice(device)}
                          >
                            {busy === `revoke:${device.id}` ? (
                              <Loader2 className='h-3.5 w-3.5 animate-spin' />
                            ) : (
                              <Trash2 className='h-3.5 w-3.5' />
                            )}
                            Revoke
                          </Button>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </SectionCard>

            <SectionCard
              title='WAN via Cloudtap'
              subtitle='Expose the Synapse daemon port through Cloudflare, then verify both health and the mobile shell before calling it ready.'
              icon={Cloud}
            >
              {!status.wan.available ? (
                <div className='space-y-3 rounded-2xl border border-amber-500/35 bg-amber-500/10 p-4 text-sm text-amber-100'>
                  <p>
                    Cloudtap is not loaded in this Synapse build yet. Install it from Tools -&gt; Discover to make WAN phone access available here.
                  </p>
                  <Button type='button' variant='outline' size='sm' className='w-fit' onClick={() => void installCloudtap()}>
                    <ExternalLink className='h-3.5 w-3.5' />
                    Open Cloudtap in Tools
                  </Button>
                </div>
              ) : (
                <div className='space-y-4'>
                  <div className='rounded-2xl border border-border/70 bg-background/55 p-4'>
                    <div className='flex flex-wrap items-start justify-between gap-3'>
                      <div>
                        <p className='text-sm font-medium text-foreground'>Daemon port</p>
                        <p className='mt-1 text-xs text-muted-foreground'>
                          Cloudtap must expose <code className='font-mono'>{status.network.bound_port}</code> for the phone shell to stay attached to the actual Synapse daemon.
                        </p>
                      </div>
                      <Badge variant='outline' className='rounded-full border-border/70 px-3 py-1 text-[11px] uppercase tracking-[0.14em]'>
                        {status.wan.verification.status}
                      </Badge>
                    </div>

                    {status.wan.active && status.wan.public_url && (
                      <div className='mt-4 space-y-2'>
                        <div className='flex flex-wrap items-center gap-2'>
                          <button
                            type='button'
                            onClick={() => void openExternal(status.wan.public_url!)}
                            className='inline-flex min-w-0 items-center gap-1.5 font-mono text-sm text-primary hover:underline'
                          >
                            <ExternalLink className='h-3.5 w-3.5' />
                            <span className='truncate'>{status.wan.public_url}</span>
                          </button>
                          <Button
                            type='button'
                            variant='ghost'
                            size='sm'
                            className='h-7 px-2 text-xs'
                            onClick={() => void copy(status.wan.public_url!)}
                          >
                            <Copy className='h-3 w-3' />
                            {justCopied === status.wan.public_url ? 'Copied' : 'Copy'}
                          </Button>
                        </div>
                        <div className='grid gap-2 sm:grid-cols-2'>
                          <VerificationPill label='Health endpoint' ok={status.wan.verification.health_ok} />
                          <VerificationPill label='Mobile shell' ok={status.wan.verification.mobile_ok} />
                        </div>
                        {status.wan.verification.failure_message && (
                          <p className='text-sm text-amber-100'>
                            {status.wan.verification.failure_message}
                          </p>
                        )}
                      </div>
                    )}
                  </div>

                  <div className='flex flex-wrap gap-2'>
                    {!status.wan.active ? (
                      <Button type='button' variant='outline' onClick={() => void openTunnel()} disabled={tunnelBusy}>
                        {tunnelBusy ? <Loader2 className='h-4 w-4 animate-spin' /> : <Cloud className='h-4 w-4' />}
                        Expose to WAN via Cloudtap
                      </Button>
                    ) : (
                      <>
                        <Button type='button' variant='outline' onClick={() => void refreshTunnel()} disabled={tunnelBusy}>
                          {tunnelBusy ? <Loader2 className='h-4 w-4 animate-spin' /> : <RefreshCw className='h-4 w-4' />}
                          Refresh tunnel
                        </Button>
                        <Button type='button' variant='ghost' className='text-destructive hover:bg-destructive/10' onClick={() => void closeTunnel()} disabled={tunnelBusy}>
                          <Trash2 className='h-4 w-4' />
                          Close tunnel
                        </Button>
                      </>
                    )}
                  </div>
                </div>
              )}
            </SectionCard>

            <SectionCard
              title='Diagnostics'
              subtitle='Exact state so you can tell whether the phone path is blocked by bind settings, pairing, or WAN verification.'
              icon={AlertTriangle}
            >
              <div className='grid gap-3 md:grid-cols-2'>
                <DiagnosticLine label='Computer'>{status.computer_name}</DiagnosticLine>
                <DiagnosticLine label='Daemon bind'>
                  {status.network.bound_host}:{status.network.bound_port}
                </DiagnosticLine>
                <DiagnosticLine label='Loopback mobile URL'>{status.network.loopback_url}</DiagnosticLine>
                <DiagnosticLine label='LAN URLs'>
                  {status.network.mobile_urls.length > 0 ? status.network.mobile_urls.join(', ') : 'None'}
                </DiagnosticLine>
                <DiagnosticLine label='Pairing code'>
                  {status.pairing_code.active ? `Active until ${status.pairing_code.expires_at}` : 'Inactive'}
                </DiagnosticLine>
                <DiagnosticLine label='WAN status'>
                  {status.wan.verification.status}
                  {status.wan.verification.failure_code ? ` (${status.wan.verification.failure_code})` : ''}
                </DiagnosticLine>
              </div>
            </SectionCard>
          </div>
        </div>
      </Card>

      <Modal
        open={reconnectPreview !== null}
        onClose={() => setReconnectPreview(null)}
        labelledBy='reconnect-preview-title'
        className='max-w-xl rounded-3xl'
      >
        {reconnectPreview && (
          <div className='space-y-4'>
            <div>
              <h3 id='reconnect-preview-title' className='text-xl font-semibold tracking-tight'>
                Secure reconnect for {reconnectPreview.device.name}
              </h3>
              <p className='mt-1 text-sm text-muted-foreground'>
                This {reconnectPreview.target.toUpperCase()} link is single-use and expires at{' '}
                {formatLocal(reconnectPreview.expiresAt, 'long')}.
              </p>
            </div>

            <div className='grid gap-4 sm:grid-cols-[220px_1fr]'>
              <div className='flex items-center justify-center rounded-2xl border border-border/70 bg-white p-3'>
                {reconnectPreview.qrDataUrl ? (
                  <img
                    src={reconnectPreview.qrDataUrl}
                    alt={`Reconnect QR for ${reconnectPreview.device.name}`}
                    width={200}
                    height={200}
                    className='rounded-xl'
                  />
                ) : (
                  <Loader2 className='h-6 w-6 animate-spin text-primary' />
                )}
              </div>
              <div className='space-y-3'>
                <div className='rounded-2xl border border-border/70 bg-secondary/20 p-3'>
                  <p className='text-xs font-semibold uppercase tracking-[0.18em] text-primary/85'>
                    Reconnect link
                  </p>
                  <code className='mt-2 block break-all text-xs text-foreground'>
                    {reconnectPreview.url}
                  </code>
                </div>
                <div className='flex flex-wrap gap-2'>
                  <Button type='button' onClick={() => void copy(reconnectPreview.url)}>
                    <Copy className='h-4 w-4' />
                    {justCopied === reconnectPreview.url ? 'Copied' : 'Copy link'}
                  </Button>
                  <Button type='button' variant='outline' onClick={() => void openExternal(reconnectPreview.url)}>
                    <ExternalLink className='h-4 w-4' />
                    Open link
                  </Button>
                </div>
              </div>
            </div>
          </div>
        )}
      </Modal>
    </>
  );
}

function PairQrPanel({ url }: { url: string | null }): JSX.Element {
  const [qrDataUrl, setQrDataUrl] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    if (!url) {
      setQrDataUrl(null);
      return;
    }
    void QRCode.toDataURL(url, {
      width: 220,
      margin: 1,
      color: { dark: '#0b0f17', light: '#ffffff' },
    }).then((dataUrl) => {
      if (!cancelled) setQrDataUrl(dataUrl);
    });
    return () => {
      cancelled = true;
    };
  }, [url]);

  return (
    <div className='flex min-h-[180px] items-center justify-center rounded-2xl border border-border/70 bg-background/55 p-3'>
      {qrDataUrl ? (
        <img src={qrDataUrl} alt='Phone access QR code' width={160} height={160} className='rounded-xl bg-white p-1' />
      ) : (
        <div className='space-y-2 text-center text-xs text-muted-foreground'>
          <QrCode className='mx-auto h-5 w-5' />
          <p>QR appears when a phone URL is ready.</p>
        </div>
      )}
    </div>
  );
}

function SectionCard({
  title,
  subtitle,
  icon: Icon,
  children,
}: {
  title: string;
  subtitle: string;
  icon: typeof Smartphone;
  children: React.ReactNode;
}): JSX.Element {
  return (
    <div className='rounded-3xl border border-border/70 bg-card/70 p-5 shadow-sm'>
      <div className='mb-4 flex items-start gap-3'>
        <div className='flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-primary/12 text-primary'>
          <Icon className='h-4.5 w-4.5' />
        </div>
        <div>
          <h3 className='text-lg font-semibold tracking-tight'>{title}</h3>
          <p className='mt-1 text-sm text-muted-foreground'>{subtitle}</p>
        </div>
      </div>
      {children}
    </div>
  );
}

function VerificationPill({ label, ok }: { label: string; ok: boolean }): JSX.Element {
  return (
    <div
      className={[
        'rounded-2xl border px-3 py-2 text-sm',
        ok
          ? 'border-emerald-500/35 bg-emerald-500/10 text-emerald-200'
          : 'border-amber-500/35 bg-amber-500/10 text-amber-100',
      ].join(' ')}
    >
      <div className='flex items-center gap-2 font-medium'>
        {ok ? <CheckCircle2 className='h-4 w-4' /> : <AlertTriangle className='h-4 w-4' />}
        {label}
      </div>
    </div>
  );
}

function StatusPill({
  icon: Icon,
  label,
  tone,
}: {
  icon: typeof Smartphone;
  label: string;
  tone: 'good' | 'warn' | 'muted';
}): JSX.Element {
  const classes =
    tone === 'good'
      ? 'bg-emerald-500/15 text-emerald-300'
      : tone === 'warn'
        ? 'bg-amber-500/15 text-amber-100'
        : 'bg-secondary text-secondary-foreground';
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium ${classes}`}>
      <Icon className='h-3.5 w-3.5' />
      {label}
    </span>
  );
}

function DiagnosticLine({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}): JSX.Element {
  return (
    <div className='rounded-2xl border border-border/70 bg-background/45 px-3 py-3 text-sm'>
      <p className='text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground'>{label}</p>
      <p className='mt-2 break-words font-mono text-foreground'>{children}</p>
    </div>
  );
}
