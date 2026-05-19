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

const GITHUB_URL = 'https://github.com/jross32/synapse';

// Human-readable labels for the raw WebSocket connection state.
const CONN_LABEL: Record<string, string> = {
  idle: 'Idle',
  connecting: 'Connecting…',
  open: 'Connected',
  reconnecting: 'Reconnecting…',
  closed: 'Disconnected',
};

export function SettingsPage(): JSX.Element {
  const { health, healthError, connState, uiVersion, platform, daemonBaseUrl } = useDaemon();

  return (
    <div className='flex flex-col gap-6'>
      <PageHeader title='Settings' subtitle='Daemon diagnostics, connection, and about.' />

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
        <Row label='Base URL'>{daemonBaseUrl}</Row>
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

      <SnapshotPanel />

      <Card className='flex flex-col gap-2 border-dashed p-6'>
        <h2 className='text-lg font-semibold'>Coming soon</h2>
        <p className='text-sm text-muted-foreground'>
          Theme toggle, start-with-Windows, and LAN exposure for the mobile UI land in
          upcoming versions as their daemon settings are wired.
        </p>
      </Card>
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }): JSX.Element {
  return (
    <div className='grid grid-cols-[180px_1fr] gap-4 text-sm'>
      <span className='text-muted-foreground'>{label}</span>
      <span className='font-mono text-foreground'>{children}</span>
    </div>
  );
}
