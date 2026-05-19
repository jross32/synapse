// Paired devices panel (Milestone H · v0.1.11) -- Settings page.
//
// Generate a pairing code for a phone to redeem, and review / revoke the
// devices already paired. The mobile Web UI that consumes these codes lands
// in v0.1.12; this is the desktop half of the flow.

import { useEffect, useRef, useState } from 'react';
import { Loader2, Smartphone, Trash2 } from 'lucide-react';

import type { PairedDevice, PairingCode } from '@shared/pairing-client';
import {
  issuePairingCode,
  listPairedDevices,
  revokePairedDevice,
} from '@shared/pairing-client';
import { formatLocal } from '@shared/format-time';
import { Badge } from './ui/badge';
import { Button } from './ui/button';
import { Card } from './ui/card';

function secondsLeft(expiresAt: string): number {
  return Math.max(0, Math.round((new Date(expiresAt).getTime() - Date.now()) / 1000));
}

export function PairedDevicesPanel(): JSX.Element {
  const [devices, setDevices] = useState<PairedDevice[] | null>(null);
  const [code, setCode] = useState<PairingCode | null>(null);
  const [remaining, setRemaining] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const tick = useRef<ReturnType<typeof setInterval> | null>(null);

  function refresh(): void {
    listPairedDevices()
      .then(setDevices)
      .catch((err: Error) => setError(err.message || 'Failed to load devices'));
  }

  useEffect(() => {
    refresh();
    return () => {
      if (tick.current) clearInterval(tick.current);
    };
  }, []);

  // Count the live code down; drop it when it expires.
  useEffect(() => {
    if (!code) return;
    setRemaining(secondsLeft(code.expires_at));
    const id = setInterval(() => {
      const left = secondsLeft(code.expires_at);
      setRemaining(left);
      if (left <= 0) setCode(null);
    }, 1000);
    tick.current = id;
    return () => clearInterval(id);
  }, [code]);

  async function handleGenerate(): Promise<void> {
    setBusy(true);
    setError(null);
    try {
      setCode(await issuePairingCode());
    } catch (err) {
      setError(`Couldn't generate a code: ${(err as Error).message}`);
    } finally {
      setBusy(false);
    }
  }

  async function handleRevoke(device: PairedDevice): Promise<void> {
    setError(null);
    try {
      await revokePairedDevice(device.id);
      setDevices((prev) => (prev ? prev.filter((d) => d.id !== device.id) : prev));
    } catch (err) {
      setError(`Couldn't revoke ${device.name}: ${(err as Error).message}`);
    }
  }

  return (
    <Card className='flex flex-col gap-4 p-6'>
      <div>
        <h2 className='text-lg font-semibold'>Paired devices</h2>
        <p className='mt-1 text-sm text-muted-foreground'>
          Pair a phone to control Synapse remotely. Generate a code here, then enter it on
          the device — it stays paired until you revoke it. Codes expire after 10 minutes.
        </p>
      </div>

      {code ? (
        <div className='flex flex-col items-center gap-1 rounded-md border border-border bg-secondary/50 p-4'>
          <span className='text-xs font-medium text-muted-foreground'>Pairing code</span>
          <span className='font-mono text-3xl font-semibold tracking-[0.3em]'>{code.code}</span>
          <span className='text-xs text-muted-foreground'>
            Expires in {Math.floor(remaining / 60)}:{String(remaining % 60).padStart(2, '0')}
          </span>
        </div>
      ) : (
        <Button variant='outline' className='w-fit' disabled={busy} onClick={() => void handleGenerate()}>
          {busy ? <Loader2 className='h-4 w-4 animate-spin' /> : <Smartphone className='h-4 w-4' />}
          Pair a device
        </Button>
      )}

      {error && (
        <p role='alert' className='text-sm text-destructive'>
          {error}
        </p>
      )}

      {devices && devices.length > 0 && (
        <ul className='flex flex-col gap-2'>
          {devices.map((d) => (
            <li
              key={d.id}
              className='flex items-center justify-between gap-3 rounded-md border border-border bg-secondary/40 p-3'
            >
              <div className='flex min-w-0 items-center gap-2'>
                <Smartphone className='h-4 w-4 shrink-0 text-muted-foreground' />
                <div className='min-w-0'>
                  <div className='truncate text-sm font-medium'>{d.name}</div>
                  <div className='text-xs text-muted-foreground'>
                    {d.last_seen_at
                      ? `Last seen ${formatLocal(d.last_seen_at, 'short')}`
                      : 'Never connected'}
                  </div>
                </div>
              </div>
              <Button
                variant='ghost'
                size='sm'
                className='shrink-0 text-muted-foreground'
                onClick={() => void handleRevoke(d)}
              >
                <Trash2 className='h-3.5 w-3.5' /> Revoke
              </Button>
            </li>
          ))}
        </ul>
      )}

      {devices && devices.length === 0 && (
        <Badge variant='secondary' className='w-fit'>
          No devices paired yet
        </Badge>
      )}
    </Card>
  );
}
