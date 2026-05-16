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

import { apiFetch, daemonBase, setDaemonBase } from './api-client';
import type { HealthResponse, Project, ResourceSnapshot } from './generated-types';
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

export interface DaemonContextValue {
  connState: ConnState;
  health: HealthResponse | null;
  healthError: string | null;
  projects: Project[];
  resourcesById: Record<string, ResourceSnapshot>;
  /** Most recent events, newest first (capped) -- handy for Home / debugging. */
  recentEvents: SynapseEvent[];
  uiVersion: string;
  platform: string;
  daemonBaseUrl: string;
  refreshProjects: () => Promise<void>;
  refreshHealth: () => Promise<void>;
  /** Optimistic local mutations so a page doesn't have to wait for a refetch. */
  upsertProjectLocal: (project: Project) => void;
  removeProjectLocal: (id: string) => void;
}

const DaemonContext = createContext<DaemonContextValue | null>(null);

const RECENT_EVENTS_CAP = 30;

export function DaemonProvider({ children }: { children: ReactNode }): JSX.Element {
  const bridge = useMemo(() => getBridge(), []);
  const uiVersion = bridge?.version() ?? '0.1.8';
  const platform = bridge?.platform() ?? 'browser';

  const [connState, setConnState] = useState<ConnState>('idle');
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [resourcesById, setResourcesById] = useState<Record<string, ResourceSnapshot>>({});
  const [recentEvents, setRecentEvents] = useState<SynapseEvent[]>([]);
  const wsRef = useRef<SynapseWsClient | null>(null);

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

    void refreshHealth();
    void refreshProjects();

    const ws = new SynapseWsClient();
    wsRef.current = ws;
    const unsubState = ws.onState(setConnState);
    const unsubEvent = ws.onEvent((event) => {
      setRecentEvents((prev) => [event, ...prev].slice(0, RECENT_EVENTS_CAP));
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
      }
    });
    ws.start();

    return () => {
      unsubState();
      unsubEvent();
      ws.stop();
    };
  }, [bridge, refreshHealth, refreshProjects]);

  const value: DaemonContextValue = {
    connState,
    health,
    healthError,
    projects,
    resourcesById,
    recentEvents,
    uiVersion,
    platform,
    daemonBaseUrl: bridge?.daemonBase() ?? daemonBase(),
    refreshProjects,
    refreshHealth,
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
