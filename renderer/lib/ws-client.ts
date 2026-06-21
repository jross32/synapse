// WebSocket client with reconnect + replay (Contract #5).
//
// Behaviour:
//   • Tracks `lastEventId` cursor across reconnects.
//   • On reconnect sends `{type: "resume", since: lastEventId}` so the daemon
//     can replay missed events from its 1 000-event ring buffer.
//   • Backoff: 1s, 2s, 4s, 8s, 16s, 30s (capped). Reset on successful connect.
//   • Emits a `state` event (idle | connecting | open | reconnecting | closed)
//     so the UI can show a "reconnecting…" badge.
//
// This file is wired to a real daemon WebSocket in Milestone C.

import { daemonBase, getAuthToken, tryRefreshLocalToken } from './api-client';

export type ConnState = 'idle' | 'connecting' | 'open' | 'reconnecting' | 'closed';

export interface SynapseEvent<TPayload = unknown> {
  id: number;
  name: string; // 'v1.entity.verb' (Contract #10)
  payload: TPayload;
  timestamp_utc: string;
}

type EventHandler = (event: SynapseEvent) => void;
type StateHandler = (state: ConnState) => void;

const BACKOFF_MS = [1000, 2000, 4000, 8000, 16000, 30000] as const;
const WS_PATH = '/api/v1/ws' as const;

export class SynapseWsClient {
  private ws: WebSocket | null = null;
  private lastEventId = 0;
  private state: ConnState = 'idle';
  private retryIndex = 0;
  private retryTimer: ReturnType<typeof setTimeout> | null = null;
  private eventHandlers = new Set<EventHandler>();
  private stateHandlers = new Set<StateHandler>();
  private stopped = false;

  /** Begin connecting. Idempotent. */
  start(): void {
    if (this.state === 'open' || this.state === 'connecting') return;
    this.stopped = false;
    this.open();
  }

  /** Permanently stop. Call on app shutdown. */
  stop(): void {
    this.stopped = true;
    if (this.retryTimer) {
      clearTimeout(this.retryTimer);
      this.retryTimer = null;
    }
    this.ws?.close();
    this.transition('closed');
  }

  onEvent(handler: EventHandler): () => void {
    this.eventHandlers.add(handler);
    return () => this.eventHandlers.delete(handler);
  }

  onState(handler: StateHandler): () => void {
    this.stateHandlers.add(handler);
    handler(this.state);
    return () => this.stateHandlers.delete(handler);
  }

  currentState(): ConnState {
    return this.state;
  }

  lastSeenEventId(): number {
    return this.lastEventId;
  }

  // ── internals ─────────────────────────────────────────────────────────

  private open(): void {
    this.transition(this.retryIndex === 0 ? 'connecting' : 'reconnecting');

    const url = daemonBase().replace(/^http/, 'ws') + WS_PATH;
    const sock = new WebSocket(url);
    this.ws = sock;

    sock.addEventListener('open', () => {
      this.retryIndex = 0;
      this.transition('open');
      // The resume frame carries the auth token (Milestone H) so a non-local
      // socket can authenticate; the daemon trusts loopback without it.
      sock.send(
        JSON.stringify({ type: 'resume', since: this.lastEventId, token: getAuthToken() })
      );
    });

    sock.addEventListener('message', (msg) => {
      const events = this.parse(msg.data);
      for (const event of events) {
        this.lastEventId = Math.max(this.lastEventId, event.id);
        for (const h of this.eventHandlers) h(event);
      }
    });

    sock.addEventListener('close', (event) => {
      this.ws = null;
      if (this.stopped) return;
      if (event.code === 1008) {
        void this.recoverAuthThenReconnect();
        return;
      }
      this.scheduleReconnect();
    });

    sock.addEventListener('error', () => {
      // The close handler will fire next; reconnect logic is centralised there.
    });
  }

  private scheduleReconnect(): void {
    const delay = BACKOFF_MS[Math.min(this.retryIndex, BACKOFF_MS.length - 1)];
    this.retryIndex += 1;
    this.transition('reconnecting');
    this.retryTimer = setTimeout(() => this.open(), delay);
  }

  private async recoverAuthThenReconnect(): Promise<void> {
    const refreshed = await tryRefreshLocalToken();
    if (!refreshed && typeof window !== 'undefined') {
      window.dispatchEvent(
        new CustomEvent('synapse:unauthorized', { detail: { status: 401, source: 'ws' } })
      );
    }
    this.scheduleReconnect();
  }

  private transition(next: ConnState): void {
    if (this.state === next) return;
    this.state = next;
    for (const h of this.stateHandlers) h(next);
  }

  /**
   * Parse one wire frame into zero or more events.
   *
   * The daemon sends three shapes (see daemon/ws.py wire protocol):
   *   • a live event:        {id, name, payload, timestamp_utc}
   *   • a replay envelope:   {type:"replay", events:[<event>, ...]}
   *   • control frames:      {type:"pong"} / {type:"error", ...}
   *
   * The replay envelope is emitted once after every (re)connect and carries
   * every event the client missed — dropping it leaves "Recent activity"
   * permanently empty. Control frames yield no events.
   */
  private parse(raw: unknown): SynapseEvent[] {
    if (typeof raw !== 'string') return [];
    let parsed: unknown;
    try {
      parsed = JSON.parse(raw);
    } catch {
      return []; // ignore — daemon will resend on next event
    }
    if (typeof parsed !== 'object' || parsed === null) return [];

    const frame = parsed as Record<string, unknown>;

    // Replay envelope — unwrap the events array.
    if (frame.type === 'replay' && Array.isArray(frame.events)) {
      return frame.events.filter(isSynapseEvent);
    }

    // Live event.
    if (isSynapseEvent(frame)) return [frame];

    return []; // pong / error / unknown control frame
  }
}

function isSynapseEvent(value: unknown): value is SynapseEvent {
  if (typeof value !== 'object' || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    typeof v.id === 'number' &&
    typeof v.name === 'string' &&
    typeof v.timestamp_utc === 'string'
  );
}
