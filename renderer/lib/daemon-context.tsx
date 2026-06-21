// DaemonProvider -- one shared connection to the Synapse daemon.
//
// Before Milestone F every page opened its own WebSocket + did its own
// fetches. With the multi-page shell that would mean 3-4 sockets. This
// context owns exactly one SynapseWsClient and one source of truth for
// health / projects / live resource snapshots; every page consumes it via
// useDaemon().

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';

import {
  apiFetch,
  bootstrapLocalToken,
  daemonBase,
  getAuthToken,
  setDaemonBase,
} from './api-client';
import type { HealthResponse, ProfileSummary, Project, ResourceSnapshot } from './generated-types';
import { getProfile } from './profile-client';
import { listProjects } from './projects-client';
import { type ConnState, SynapseWsClient, type SynapseEvent } from './ws-client';

interface SynapseBridge {
  version: () => string;
  daemonBase: () => string;
  daemonWsBase: () => string;
  platform: () => string;
}

function getBridge(): SynapseBridge | null {
  return (window as unknown as { synapse?: SynapseBridge }).synapse ?? null;
}

function formatDisplayVersion(value: string | null | undefined): string {
  const trimmed = value?.trim() ?? '';
  if (!trimmed) return '';
  return trimmed.replace(/\.dev0$/, '-dev').replace(/\.dev(\d+)$/, '-dev.$1');
}

export interface DaemonContextValue {
  connState: ConnState;
  health: HealthResponse | null;
  healthError: string | null;
  profile: ProfileSummary | null;
  profileError: string | null;
  projects: Project[];
  resourcesById: Record<string, ResourceSnapshot>;
  /** Most recent events, newest first (capped) -- handy for Home / debugging. */
  recentEvents: SynapseEvent[];
  /**
   * Subscribe to every event from the daemon as it arrives. Returns an
   * unsubscribe function. Use this for high-frequency streams (PTY output,
   * heartbeats) that would otherwise overflow the 30-item recentEvents cap.
   */
  subscribeRaw: (handler: (event: SynapseEvent) => void) => () => void;
  uiVersion: string;
  platform: string;
  daemonBaseUrl: string;
  refreshProjects: () => Promise<void>;
  refreshHealth: () => Promise<void>;
  refreshProfile: () => Promise<void>;
  /** Optimistic local mutations so a page doesn't have to wait for a refetch. */
  upsertProjectLocal: (project: Project) => void;
  removeProjectLocal: (id: string) => void;
}

const DaemonContext = createContext<DaemonContextValue | null>(null);

const RECENT_EVENTS_CAP = 30;

export function DaemonProvider({ children }: { children: ReactNode }): JSX.Element {
  const bridge = useMemo(() => getBridge(), []);
  const platform = bridge?.platform() ?? 'browser';

  const [connState, setConnState] = useState<ConnState>('idle');
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [profile, setProfile] = useState<ProfileSummary | null>(null);
  const [profileError, setProfileError] = useState<string | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [resourcesById, setResourcesById] = useState<Record<string, ResourceSnapshot>>({});
  const [recentEvents, setRecentEvents] = useState<SynapseEvent[]>([]);
  const wsRef = useRef<SynapseWsClient | null>(null);
  // Raw-event subscribers. Lives on a ref so the subscribe function we hand
  // to consumers is stable across renders AND survives the WS being created
  // *after* the child effect that subscribed. Child effects run before
  // parent effects on mount, so subscribers were missing events until we
  // routed through this in-memory Set rather than ws.onEvent directly.
  const rawHandlersRef = useRef<Set<(event: SynapseEvent) => void>>(new Set());

  const subscribeRaw = useCallback((handler: (event: SynapseEvent) => void) => {
    rawHandlersRef.current.add(handler);
    return () => {
      rawHandlersRef.current.delete(handler);
    };
  }, []);

  const refreshProjects = useCallback(async () => {
    try {
      setProjects(await listProjects());
    } catch {
      // The Apps page surfaces load errors; the context stays quiet.
    }
  }, []);

  const refreshHealth = useCallback(async () => {
    try {
      const res = await apiFetch<HealthResponse>('/health', { method: 'GET' });
      setHealth(res);
      setHealthError(null);
    } catch (err) {
      setHealthError((err as Error).message || 'Failed to reach daemon');
    }
  }, []);

  const refreshProfile = useCallback(async () => {
    try {
      setProfile(await getProfile());
      setProfileError(null);
    } catch (err) {
      setProfileError((err as Error).message || 'Failed to load profile');
    }
  }, []);

  const upsertProjectLocal = useCallback((project: Project) => {
    setProjects((prev) => {
      const exists = prev.some((p) => p.id === project.id);
      return exists ? prev.map((p) => (p.id === project.id ? project : p)) : [...prev, project];
    });
  }, []);

  const removeProjectLocal = useCallback((id: string) => {
    setProjects((prev) => prev.filter((p) => p.id !== id));
  }, []);

  useEffect(() => {
    if (bridge) setDaemonBase(bridge.daemonBase());

    let cancelled = false;
    const ws = new SynapseWsClient();
    wsRef.current = ws;
    const unsubState = ws.onState(setConnState);
    const unsubEvent = ws.onEvent((event) => {
      setRecentEvents((prev) => [event, ...prev].slice(0, RECENT_EVENTS_CAP));
      // Fan out to raw subscribers (PTY terminals etc.) BEFORE the routing
      // below so high-volume streams aren't gated on React re-renders.
      for (const handler of rawHandlersRef.current) {
        try {
          handler(event);
        } catch {
          // A bad subscriber must never poison the others.
        }
      }
      if (event.name === 'v1.process.heartbeat') {
        const procs = (event.payload as { processes?: ResourceSnapshot[] }).processes ?? [];
        setResourcesById((prev) => {
          const next = { ...prev };
          for (const snap of procs) next[snap.entity_id] = snap;
          return next;
        });
        return;
      }
      if (event.name.startsWith('v1.project.')) {
        void refreshProjects();
        return;
      }
      if (
        event.name === 'v1.profile.updated' ||
        event.name === 'v1.profile.sync.updated' ||
        event.name === 'v1.service_connection.updated'
      ) {
        void refreshProfile();
      }
    });

    // Auth bootstrap (Milestone H): grab the local token before any protected
    // request or the WebSocket handshake. /health is open so it can go first.
    void (async () => {
      void refreshHealth();
      if (!getAuthToken()) {
        try {
          await bootstrapLocalToken();
        } catch {
          // Off-machine or daemon down — protected calls will surface the error.
        }
      }
      if (cancelled) return;
      void refreshProjects();
      void refreshProfile();
      ws.start();
    })();

    return () => {
      cancelled = true;
      unsubState();
      unsubEvent();
      ws.stop();
    };
  }, [bridge, refreshHealth, refreshProfile, refreshProjects]);

  // Prefer the Electron bundle version, fall back to whatever the live daemon
  // reports, and only then a neutral placeholder -- never a stale literal.
  const bridgeVersion = formatDisplayVersion(bridge?.version());
  const healthVersion = formatDisplayVersion(health?.version);
  const uiVersion = bridgeVersion || healthVersion || 'dev';

  const value: DaemonContextValue = {
    connState,
    health,
    healthError,
    profile,
    profileError,
    projects,
    resourcesById,
    recentEvents,
    subscribeRaw,
    uiVersion,
    platform,
    daemonBaseUrl: bridge?.daemonBase() ?? daemonBase(),
    refreshProjects,
    refreshHealth,
    refreshProfile,
    upsertProjectLocal,
    removeProjectLocal,
  };

  return <DaemonContext.Provider value={value}>{children}</DaemonContext.Provider>;
}

export function useDaemon(): DaemonContextValue {
  const ctx = useContext(DaemonContext);
  if (ctx === null) {
    throw new Error('useDaemon() must be used inside <DaemonProvider>');
  }
  return ctx;
}
