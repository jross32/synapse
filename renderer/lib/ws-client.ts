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

import { daemonBase } from './api-client';

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
      sock.send(JSON.stringify({ type: 'resume', since: this.lastEventId }));
    });

    sock.addEventListener('message', (msg) => {
      const event = this.parse(msg.data);
      if (!event) return;
      this.lastEventId = Math.max(this.lastEventId, event.id);
      for (const h of this.eventHandlers) h(event);
    });

    sock.addEventListener('close', () => {
      this.ws = null;
      if (this.stopped) return;
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

  private transition(next: ConnState): void {
    if (this.state === next) return;
    this.state = next;
    for (const h of this.stateHandlers) h(next);
  }

  private parse(raw: unknown): SynapseEvent | null {
    if (typeof raw !== 'string') return null;
    try {
      const parsed = JSON.parse(raw) as Partial<SynapseEvent>;
      if (
        typeof parsed.id === 'number' &&
        typeof parsed.name === 'string' &&
        typeof parsed.timestamp_utc === 'string'
      ) {
        return parsed as SynapseEvent;
      }
    } catch {
      // ignore — daemon will resend on next event
    }
    return null;
  }
}
