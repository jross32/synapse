import { useEffect, useMemo, useState } from 'react';

import { apiFetch, daemonBase, setDaemonBase } from './lib/api-client';
import type { HealthResponse } from './lib/generated-types';
import { formatLocal, formatUptime } from './lib/format-time';
import { AppsPage } from './pages/Apps';
import { type ConnState, SynapseWsClient } from './lib/ws-client';

interface SynapseBridge {
  version: () => string;
  daemonBase: () => string;
  daemonWsBase: () => string;
  platform: () => string;
}

function getBridge(): SynapseBridge | null {
  return (window as unknown as { synapse?: SynapseBridge }).synapse ?? null;
}

const STATE_LABEL: Record<ConnState, string> = {
  idle: 'idle',
  connecting: 'connecting…',
  open: 'connected',
  reconnecting: 'reconnecting…',
  closed: 'closed',
};

const STATE_TOKEN: Record<ConnState, string> = {
  idle: 'var(--synapse-status-idle)',
  connecting: 'var(--synapse-status-launching)',
  open: 'var(--synapse-status-launched)',
  reconnecting: 'var(--synapse-status-launching)',
  closed: 'var(--synapse-status-error)',
};

// Milestone D — daemon status header + Apps page below.
// The full nucleus + synapses sidebar/layout arrives in Milestone F.
export default function App(): JSX.Element {
  const bridge = useMemo(() => getBridge(), []);
  const uiVersion = bridge?.version() ?? '0.1.7';
  const platform = bridge?.platform() ?? 'browser';

  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [connState, setConnState] = useState<ConnState>('idle');

  useEffect(() => {
    if (bridge) {
      setDaemonBase(bridge.daemonBase());
    }

    let cancelled = false;
    apiFetch<HealthResponse>('/health', { method: 'GET' })
      .then((res) => {
        if (!cancelled) setHealth(res);
      })
      .catch((err: Error) => {
        if (!cancelled) setHealthError(err.message || 'Failed to reach daemon');
      });

    const ws = new SynapseWsClient();
    const unsubState = ws.onState((s) => setConnState(s));
    ws.start();
    return () => {
      cancelled = true;
      unsubState();
      ws.stop();
    };
  }, [bridge]);

  return (
    <main
      style={{
        minHeight: '100vh',
        display: 'flex',
        flexDirection: 'column',
        padding: 'var(--synapse-space-8)',
        gap: 'var(--synapse-space-6)',
        backgroundColor: 'var(--synapse-bg-nucleus)',
        color: 'var(--synapse-text-primary)',
        fontFamily: 'var(--synapse-font-sans)',
      }}
    >
      <header style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between' }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 'var(--synapse-text-2xl)', letterSpacing: '-0.01em' }}>
            Synapse
          </h1>
          <p style={{ margin: 0, color: 'var(--synapse-text-secondary)', fontSize: 'var(--synapse-text-sm)' }}>
            by The WhatIf Company · UI v{uiVersion} · {platform}
          </p>
        </div>
        <StatusBadgePill label={STATE_LABEL[connState]} color={STATE_TOKEN[connState]} />
      </header>

      <section style={cardStyle}>
        <h2 style={cardTitle}>Daemon</h2>
        {health ? (
          <dl style={dlStyle}>
            <Row label='Version' value={health.version} />
            <Row label='Contracts' value={`${health.contracts.length} honoured (#1–#${Math.max(...health.contracts)})`} />
            <Row label='Started' value={formatLocal(health.started_at, 'long')} />
            <Row label='Uptime' value={formatUptime(health.started_at)} />
            <Row label='Base URL' value={bridge?.daemonBase() ?? daemonBase()} />
          </dl>
        ) : healthError ? (
          <p style={{ color: 'var(--synapse-status-error)' }}>
            Could not reach daemon: {healthError}
          </p>
        ) : (
          <p style={{ color: 'var(--synapse-text-secondary)' }}>Reaching daemon…</p>
        )}
      </section>

      <AppsPage />

      <footer style={{ marginTop: 'auto', color: 'var(--synapse-text-muted)', fontSize: 'var(--synapse-text-xs)' }}>
        Milestone D scaffold · Sidebar + Nucleus + Synapses layout arrives in Milestone F.
      </footer>
    </main>
  );
}

const cardStyle: React.CSSProperties = {
  backgroundColor: 'var(--synapse-bg-surface)',
  border: '1px solid var(--synapse-border-subtle)',
  borderRadius: 'var(--synapse-radius-lg)',
  padding: 'var(--synapse-space-6)',
};

const cardTitle: React.CSSProperties = {
  margin: '0 0 var(--synapse-space-4) 0',
  fontSize: 'var(--synapse-text-lg)',
  letterSpacing: '-0.01em',
  color: 'var(--synapse-text-primary)',
};

const dlStyle: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: '160px 1fr',
  gap: 'var(--synapse-space-2) var(--synapse-space-4)',
  margin: 0,
  fontSize: 'var(--synapse-text-sm)',
};

function Row({ label, value }: { label: string; value: string }): JSX.Element {
  return (
    <>
      <dt style={{ color: 'var(--synapse-text-muted)' }}>{label}</dt>
      <dd style={{ margin: 0, fontFamily: 'var(--synapse-font-mono)', color: 'var(--synapse-text-primary)' }}>
        {value}
      </dd>
    </>
  );
}

function StatusBadgePill({ label, color }: { label: string; color: string }): JSX.Element {
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 'var(--synapse-space-2)',
        padding: 'var(--synapse-space-1) var(--synapse-space-3)',
        borderRadius: 'var(--synapse-radius-pill)',
        backgroundColor: 'var(--synapse-bg-elevated)',
        border: '1px solid var(--synapse-border-subtle)',
        fontSize: 'var(--synapse-text-xs)',
        fontFamily: 'var(--synapse-font-mono)',
        color: 'var(--synapse-text-primary)',
      }}
    >
      <span
        style={{
          width: '8px',
          height: '8px',
          borderRadius: 'var(--synapse-radius-pill)',
          backgroundColor: color,
        }}
      />
      {label}
    </span>
  );
}
