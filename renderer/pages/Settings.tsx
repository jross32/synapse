// Settings page (Milestone F) -- daemon diagnostics + About.
// Theme toggle, autostart, and LAN exposure controls land in later versions
// as their backing daemon settings are wired.

import { useDaemon } from '@shared/daemon-context';
import { formatLocal, formatUptime } from '@shared/format-time';
import { openExternal } from '@shared/electron-bridge';
import { Card } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { StatusBadge } from '../components/StatusBadge';
import { PageHeader } from '../components/PageHeader';
import { SnapshotPanel } from '../components/SnapshotPanel';
import { StartupPanel } from '../components/StartupPanel';
import { AuditLogPanel } from '../components/AuditLogPanel';
import { PhoneAccessPanel } from '../components/PhoneAccessPanel';
import { ThemePanel } from '../components/ThemePanel';

const GITHUB_URL = 'https://github.com/jross32/synapse';

// Human-readable labels for the raw WebSocket connection state.
const CONN_LABEL: Record<string, string> = {
  idle: 'Idle',
  connecting: 'Connecting…',
  open: 'Connected',
  reconnecting: 'Reconnecting…',
  closed: 'Disconnected',
};

export interface SettingsPageProps {
  mobileRoute?: boolean;
  onForgetDevice?: () => void;
}

export function SettingsPage({
  mobileRoute = false,
  onForgetDevice,
}: SettingsPageProps): JSX.Element {
  const { health, healthError, connState, uiVersion, platform, daemonBaseUrl } = useDaemon();

  return (
    <div className='flex flex-col gap-6'>
      <PageHeader title='Settings' subtitle='Daemon diagnostics, connection, and about.' />

      {mobileRoute && onForgetDevice && (
        <Card className='flex flex-col gap-4 p-6'>
          <div>
            <h2 className='text-lg font-semibold'>This browser</h2>
            <p className='mt-1 text-sm text-muted-foreground'>
              Clears the saved device token from this browser only. The device stays paired in
              Synapse until you revoke it from the desktop app.
            </p>
          </div>
          <div>
            <Button variant='outline' onClick={onForgetDevice}>
              Forget this device in this browser
            </Button>
          </div>
        </Card>
      )}

      <Card className='flex flex-col gap-4 p-6'>
        <h2 className='text-lg font-semibold'>Daemon</h2>
        {health ? (
          <Row label='Status'>
            <StatusBadge
              status={connState === 'open' ? 'launched' : 'error'}
              label={CONN_LABEL[connState] ?? connState}
            />
          </Row>
        ) : (
          <p className='text-sm text-destructive'>{healthError ?? 'Reaching daemon…'}</p>
        )}
        {health && (
          <>
            <Row label='Daemon version'>{health.version}</Row>
            <Row label='Contracts honoured'>{health.contracts.length} (#1–#{Math.max(...health.contracts)})</Row>
            <Row label='Started'>{formatLocal(health.started_at, 'long')}</Row>
            <Row label='Uptime'>{formatUptime(health.started_at)}</Row>
          </>
        )}
        <Row label='Daemon URL'>{daemonBaseUrl}</Row>
        <p className='-mt-2 text-xs text-muted-foreground'>
          The only port Synapse cares about is{' '}
          <code className='font-mono text-foreground'>7878</code>. If you
          tunnel from your phone or open a Cloudtap tunnel, point it at this
          URL.{' '}
          <code className='font-mono'>5173</code> only exists while
          <code className='font-mono'> npm run dev </code>
          is running -- it's the Vite dev server for the renderer, not
          something users connect to.
        </p>
      </Card>

      <Card className='flex flex-col gap-4 p-6'>
        <h2 className='text-lg font-semibold'>About</h2>
        <Row label='Synapse UI'>v{uiVersion}</Row>
        <Row label='Platform'>{platform}</Row>
        <Row label='Company'>The WhatIf Company</Row>
        <div className='flex gap-2'>
          <Button variant='outline' size='sm' onClick={() => void openExternal(GITHUB_URL)}>
            GitHub repository
          </Button>
        </div>
      </Card>

      <ThemePanel />

      <StartupPanel />

      <PhoneAccessPanel />

      <SnapshotPanel />

      <AuditLogPanel />
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }): JSX.Element {
  return (
    <div className='grid gap-1 text-sm sm:grid-cols-[180px_1fr] sm:gap-4'>
      <span className='text-muted-foreground'>{label}</span>
      <span className='font-mono text-foreground'>{children}</span>
    </div>
  );
}
