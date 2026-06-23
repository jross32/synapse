import { useEffect, useMemo, useRef, useState } from 'react';
import {
  CheckCircle2,
  ChevronRight,
  KeyRound,
  Link2,
  Loader2,
  ShieldCheck,
  Smartphone,
  Sparkles,
} from 'lucide-react';

import {
  clearPendingPairClaim,
  currentBrowserBaseUrl,
  getPendingPairClaim,
  getStoredDeviceIdentity,
  isTunnelOrigin,
  rememberDeviceToken,
  type RuntimeAuthMode,
} from '@shared/browser-runtime';
import { formatLocal } from '@shared/format-time';
import {
  redeemHandoffClaim,
  redeemPairingCode,
  type PairResult,
} from '@shared/pairing-client';
import { Badge } from './ui/badge';
import { Button } from './ui/button';
import { Card } from './ui/card';
import { Input } from './ui/input';

type PairingScreenMode = Extract<
  RuntimeAuthMode,
  'pair-required' | 'reconnect-required' | 'claiming'
>;

interface MobilePairingScreenProps {
  mode: PairingScreenMode;
  onPaired: () => void;
  onRequireFullReset: () => void;
}

type FlowPhase = 'idle' | 'working' | 'success';

let reconnectClaimPromise: Promise<PairResult> | null = null;
let reconnectClaimValue: string | null = null;

export function MobilePairingScreen({
  mode,
  onPaired,
  onRequireFullReset,
}: MobilePairingScreenProps): JSX.Element {
  const codeRef = useRef<HTMLInputElement | null>(null);
  const device = useMemo(() => getStoredDeviceIdentity(), []);
  const [code, setCode] = useState('');
  const [deviceName, setDeviceName] = useState(device?.name ?? 'My phone');
  const [phase, setPhase] = useState<FlowPhase>(mode === 'claiming' ? 'working' : 'idle');
  const [statusLine, setStatusLine] = useState<string>(
    mode === 'claiming' ? 'Preparing your secure reconnect…' : 'Ready when you are.'
  );
  const [error, setError] = useState<string | null>(null);
  const [successCopy, setSuccessCopy] = useState<string | null>(null);

  useEffect(() => {
    if (mode === 'pair-required') {
      codeRef.current?.focus();
    }
  }, [mode]);

  useEffect(() => {
    if (mode !== 'claiming') return;
    const claim = getPendingPairClaim();
    if (!claim) {
      setPhase('idle');
      setError('This reconnect link is missing or already used in this tab.');
      return;
    }

    let cancelled = false;
    void (async () => {
      try {
        setError(null);
        setStatusLine('Verifying this reconnect link…');
        if (reconnectClaimValue !== claim || reconnectClaimPromise === null) {
          reconnectClaimValue = claim;
          reconnectClaimPromise = redeemHandoffClaim(claim);
        }
        const result = await reconnectClaimPromise;
        if (cancelled) return;
        clearPendingPairClaim();
        reconnectClaimPromise = null;
        reconnectClaimValue = null;
        finalizeSuccess(result, `Successfully reconnected to ${result.computer_name} as ${result.device.name}.`);
      } catch (err) {
        if (cancelled) return;
        clearPendingPairClaim();
        reconnectClaimPromise = null;
        reconnectClaimValue = null;
        setPhase('idle');
        setError((err as Error).message || 'This reconnect link could not be used.');
        setStatusLine('Reconnect needs a fresh secure link.');
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [mode]);

  function finalizeSuccess(result: PairResult, message: string): void {
    rememberDeviceToken(result.token, {
      id: result.device.id,
      name: result.device.name,
      computerName: result.computer_name,
    });
    setPhase('success');
    setStatusLine('Handing you into the full Synapse shell…');
    setSuccessCopy(message);
    window.setTimeout(() => onPaired(), 850);
  }

  async function pair(): Promise<void> {
    const trimmed = code.trim();
    if (!/^\d{6}$/.test(trimmed)) {
      setError('Enter the 6-digit code shown in Settings -> Phone access.');
      return;
    }
    setPhase('working');
    setStatusLine('Establishing trust with your computer…');
      setError(null);
    try {
      const result = await redeemPairingCode(
        trimmed,
        deviceName.trim() || device?.name || 'Phone',
        device?.id ?? null
      );
      finalizeSuccess(
        result,
        `Successfully paired to ${result.computer_name} as ${result.device.name}.`
      );
    } catch (err) {
      setPhase('idle');
      setError((err as Error).message || 'Pairing failed.');
      setStatusLine('Still waiting for a valid code.');
    }
  }

  const isBusy = phase === 'working';
  const isSuccess = phase === 'success';

  return (
    <div className='relative flex min-h-screen items-center justify-center overflow-hidden bg-background px-4 py-8 text-foreground'>
      <div className='absolute inset-0 bg-[radial-gradient(circle_at_top,_rgba(124,92,255,0.26),_transparent_36%),radial-gradient(circle_at_bottom_right,_rgba(56,189,248,0.18),_transparent_28%),linear-gradient(180deg,rgba(15,23,42,0.1),transparent)]' />
      <div className='absolute left-1/2 top-14 h-40 w-40 -translate-x-1/2 rounded-full bg-primary/10 blur-3xl' />

      <Card className='relative z-10 flex w-full max-w-md flex-col gap-5 overflow-hidden border-border/80 bg-card/95 p-6 shadow-2xl backdrop-blur'>
        <div className='absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-primary via-sky-400 to-emerald-400' />

        <div className='flex items-start justify-between gap-3'>
          <div className='flex items-center gap-3'>
            <div className='relative flex h-12 w-12 items-center justify-center rounded-[1.25rem] bg-primary/15 text-primary'>
              {isSuccess ? (
                <CheckCircle2 className='h-6 w-6' aria-hidden='true' />
              ) : mode === 'claiming' || mode === 'reconnect-required' ? (
                <Link2 className='h-5 w-5' aria-hidden='true' />
              ) : (
                <Smartphone className='h-5 w-5' aria-hidden='true' />
              )}
              {(isBusy || isSuccess) && (
                <span className='absolute inset-0 rounded-[1.25rem] border border-primary/30 animate-pulse' />
              )}
            </div>
            <div>
              <p className='text-xs font-semibold uppercase tracking-[0.24em] text-primary/90'>
                Synapse Mobile
              </p>
              <h1 className='text-2xl font-semibold tracking-tight'>
                {mode === 'claiming'
                  ? 'Reconnecting this phone'
                  : mode === 'reconnect-required'
                    ? 'Reconnect this phone'
                    : 'Pair this device'}
              </h1>
            </div>
          </div>
          <Badge variant='outline' className='rounded-full border-border/70 px-3 py-1 text-[10px] uppercase tracking-[0.18em]'>
            {isTunnelOrigin() ? 'WAN' : 'LAN'}
          </Badge>
        </div>

        <div className='grid grid-cols-3 gap-2'>
          <ProgressStep
            label='Trust'
            state={isSuccess ? 'done' : isBusy ? 'active' : 'idle'}
            icon={ShieldCheck}
          />
          <ProgressStep
            label='Verify'
            state={isSuccess ? 'done' : isBusy ? 'active' : mode === 'claiming' ? 'active' : 'idle'}
            icon={Link2}
          />
          <ProgressStep
            label='Open'
            state={isSuccess ? 'done' : 'idle'}
            icon={Sparkles}
          />
        </div>

        <div className='rounded-2xl border border-border/70 bg-secondary/35 p-4'>
          <div className='flex items-center gap-2 text-sm font-medium text-foreground'>
            {isSuccess ? (
              <CheckCircle2 className='h-4 w-4 text-emerald-400' aria-hidden='true' />
            ) : isBusy ? (
              <Loader2 className='h-4 w-4 animate-spin text-primary' aria-hidden='true' />
            ) : (
              <ChevronRight className='h-4 w-4 text-primary' aria-hidden='true' />
            )}
            {statusLine}
          </div>
          {successCopy && <p className='mt-2 text-sm text-emerald-300'>{successCopy}</p>}
          {!successCopy && device?.computerName && (
            <p className='mt-2 text-sm text-muted-foreground'>
              Last connected to <strong className='text-foreground'>{device.computerName}</strong> as{' '}
              <strong className='text-foreground'>{device.name}</strong>.
            </p>
          )}
        </div>

        {mode === 'pair-required' && !isSuccess && (
          <>
            <p className='text-sm text-muted-foreground'>
              On your computer, open <strong className='text-foreground'>Settings -&gt; Phone access</strong>,
              generate a 6-digit code, then enter it here.
            </p>

            <div className='grid gap-3'>
              <label className='grid gap-1.5 text-sm'>
                <span className='font-medium text-foreground'>Pairing code</span>
                <Input
                  ref={codeRef}
                  inputMode='numeric'
                  maxLength={6}
                  autoComplete='one-time-code'
                  placeholder='000000'
                  value={code}
                  onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                  className='h-14 text-center font-mono text-2xl tracking-[0.28em]'
                />
              </label>
              <label className='grid gap-1.5 text-sm'>
                <span className='font-medium text-foreground'>Device name</span>
                <Input
                  placeholder='My phone'
                  value={deviceName}
                  onChange={(e) => setDeviceName(e.target.value)}
                />
              </label>
            </div>

            <Button className='w-full rounded-2xl' disabled={isBusy} onClick={() => void pair()}>
              {isBusy ? (
                <Loader2 className='h-4 w-4 animate-spin' aria-hidden='true' />
              ) : (
                <KeyRound className='h-4 w-4' aria-hidden='true' />
              )}
              {isBusy ? 'Pairing securely…' : 'Pair and open Synapse'}
            </Button>
          </>
        )}

        {mode === 'reconnect-required' && !isSuccess && (
          <div className='space-y-4 rounded-2xl border border-border/70 bg-secondary/25 p-4'>
            <div>
              <p className='text-sm font-medium text-foreground'>This phone is already trusted.</p>
              <p className='mt-1 text-sm text-muted-foreground'>
                Open a fresh reconnect link or QR from the desktop app to restore access without
                entering another code.
              </p>
            </div>
            {device && (
              <div className='rounded-xl border border-border/70 bg-background/55 p-3 text-sm'>
                <p className='font-medium text-foreground'>{device.name}</p>
                <p className='mt-1 text-xs text-muted-foreground'>
                  Saved identity on this browser since {formatLocal(device.lastConnectedAt, 'short')}.
                </p>
              </div>
            )}
            <div className='flex flex-col gap-2 sm:flex-row'>
              <Button variant='outline' className='flex-1 rounded-2xl' onClick={onRequireFullReset}>
                Forget and pair with a new code
              </Button>
            </div>
          </div>
        )}

        {(mode === 'claiming' || isSuccess) && (
          <div className='rounded-2xl border border-primary/25 bg-primary/8 px-4 py-3 text-sm text-muted-foreground'>
            {isSuccess ? (
              <p>
                Security handoff complete. You&apos;re entering the full mobile mirror of Synapse now.
              </p>
            ) : (
              <p>
                This secure reconnect link is single-use and disappears after it finishes. Keep this
                tab open while Synapse completes the handoff.
              </p>
            )}
          </div>
        )}

        {error && (
          <div className='rounded-2xl border border-destructive/40 bg-destructive/10 px-4 py-3'>
            <p role='alert' className='text-sm text-destructive'>
              {error}
            </p>
          </div>
        )}

        <div className='rounded-2xl border border-border/70 bg-secondary/30 p-3 text-xs text-muted-foreground'>
          {isTunnelOrigin() ? (
            <p>
              You&apos;re coming in through a Cloudtap WAN link at{' '}
              <strong className='text-foreground'>{currentBrowserBaseUrl()}</strong>. After the first
              pairing, future WAN handoffs should use reconnect links instead of another 6-digit code.
            </p>
          ) : (
            <p>
              After pairing, this page becomes the full mobile mirror of the desktop app: Home, Apps,
              Tools, Sessions, Processes, and Settings.
            </p>
          )}
        </div>
      </Card>
    </div>
  );
}

interface ProgressStepProps {
  label: string;
  state: 'idle' | 'active' | 'done';
  icon: typeof ShieldCheck;
}

function ProgressStep({ label, state, icon: Icon }: ProgressStepProps): JSX.Element {
  return (
    <div
      className={[
        'flex flex-col items-center gap-1 rounded-2xl border px-3 py-2 text-center text-[11px] font-medium transition-colors',
        state === 'done'
          ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300'
          : state === 'active'
            ? 'border-primary/30 bg-primary/10 text-primary-foreground'
            : 'border-border/70 bg-secondary/20 text-muted-foreground',
      ].join(' ')}
    >
      <Icon className='h-4 w-4' aria-hidden='true' />
      <span>{label}</span>
    </div>
  );
}
