// MCP-server marketplace UI (ADR-0017 MW2). Browse + install MCP servers, see
// whether each is running, launch/stop the standalone (http) ones, toggle
// autorun, and choose which get wired into your AI. Works in the mobile shell.

import { useCallback, useEffect, useRef, useState } from 'react';
import { Check, Download, Loader2, Play, RefreshCw, RotateCcw, Server, Square, Star, Trash2, Zap } from 'lucide-react';

import {
  getMcpRegistry,
  getWardenStatus,
  installMcpServer,
  listMcpServers,
  removeMcpServer,
  rollbackWarden,
  startMcpServer,
  stopMcpServer,
  syncWardenRegistry,
  updateMcpServer,
  updateWarden,
  type McpCatalogEntry,
  type McpServerStatus,
  type McpServerView,
  type WardenStatus,
} from '@shared/mcp-servers-client';
import { cn } from '@shared/utils';
import { Button } from './ui/button';
import { Card } from './ui/card';

const STATUS_META: Record<McpServerStatus, { label: string; cls: string; dot: string }> = {
  connected: { label: 'Connected', cls: 'bg-emerald-500/15 text-emerald-300', dot: 'bg-emerald-400' },
  stdio_ready: { label: 'Ready', cls: 'bg-emerald-500/15 text-emerald-300', dot: 'bg-emerald-400' },
  starting: { label: 'Starting…', cls: 'bg-amber-500/15 text-amber-100', dot: 'bg-amber-400' },
  stopped: { label: 'Not running', cls: 'bg-secondary/60 text-muted-foreground', dot: 'bg-muted-foreground' },
  error: { label: 'Trouble connecting', cls: 'bg-destructive/15 text-destructive', dot: 'bg-destructive' },
};

interface Row {
  id: string;
  name: string;
  publisher: string | null;
  description: string;
  transport: string;
  tags: string[];
  recommended: boolean;
  installed: boolean;
  server: McpServerView | null;
}

export function McpServerBrowser(): JSX.Element {
  const [catalog, setCatalog] = useState<McpCatalogEntry[]>([]);
  const [installed, setInstalled] = useState<Map<string, McpServerView>>(new Map());
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [wardenStatus, setWardenStatus] = useState<WardenStatus | null>(null);
  const timer = useRef<number | null>(null);

  const refreshInstalled = useCallback(async () => {
    try {
      const { servers } = await listMcpServers();
      setInstalled(new Map(servers.map((s) => [s.id, s])));
    } catch {
      /* surfaced on actions */
    }
  }, []);

  const refreshAll = useCallback(async () => {
    try {
      const [cat, , warden] = await Promise.all([getMcpRegistry(), refreshInstalled(), getWardenStatus()]);
      setCatalog(cat.servers);
      setWardenStatus(warden);
      setError(null);
    } catch (e) {
      setError((e as Error).message || 'Could not load the MCP catalog.');
    } finally {
      setLoading(false);
    }
  }, [refreshInstalled]);

  useEffect(() => {
    void refreshAll();
    // Poll status so http servers flip to Connected as they come up.
    timer.current = window.setInterval(() => void refreshInstalled(), 4000);
    return () => {
      if (timer.current) window.clearInterval(timer.current);
    };
  }, [refreshAll, refreshInstalled]);

  async function run(key: string, fn: () => Promise<unknown>): Promise<void> {
    setBusy(key);
    setError(null);
    try {
      await fn();
      await refreshAll();
    } catch (e) {
      setError((e as Error).message || 'Action failed.');
    } finally {
      setBusy(null);
    }
  }

  if (loading) {
    return (
      <Card className='flex items-center gap-2 p-6 text-sm text-muted-foreground'>
        <Loader2 className='h-4 w-4 animate-spin' /> Loading MCP servers…
      </Card>
    );
  }

  const catalogIds = new Set(catalog.map((c) => c.id));
  const rows: Row[] = [
    ...catalog.map((c) => ({
      id: c.id,
      name: c.name,
      publisher: c.publisher,
      description: c.description,
      transport: c.transport,
      tags: c.tags,
      recommended: c.recommended,
      installed: installed.has(c.id),
      server: installed.get(c.id) ?? null,
    })),
    ...[...installed.values()]
      .filter((s) => !catalogIds.has(s.id))
      .map((s) => ({
        id: s.id,
        name: s.name,
        publisher: s.publisher,
        description: s.description,
        transport: s.transport,
        tags: [],
        recommended: false,
        installed: true,
        server: s,
      })),
  ];

  return (
    <div className='flex flex-col gap-3'>
      {error && <p role='alert' className='text-xs text-destructive'>{error}</p>}
      <p className='text-xs text-muted-foreground'>
        AI-enabled servers remain directly available. Warden is optional and adds search/routing without replacing them.
      </p>
      <div className='grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3'>
        {rows.map((row) => {
          const s = row.server;
          const meta = s ? STATUS_META[s.status] : null;
          const isHttp = row.transport === 'http';
          const canLaunch = isHttp && s && (s.status === 'stopped' || s.status === 'error') && !!s.launch_command;
          const canStop = isHttp && s && (s.status === 'connected' || s.status === 'starting');
          const isWarden = row.id === 'warden';
          return (
            <Card key={row.id} className='flex flex-col gap-2 p-4'>
              <div className='flex items-start justify-between gap-2'>
                <div className='min-w-0'>
                  <div className='flex items-center gap-1.5'>
                    <Server className='h-4 w-4 shrink-0 text-muted-foreground' />
                    <h3 className='truncate font-semibold'>{row.name}</h3>
                    {row.recommended && <Star className='h-3.5 w-3.5 shrink-0 fill-primary text-primary' aria-label='Recommended' />}
                  </div>
                  <p className='text-xs text-muted-foreground'>
                    {row.publisher ? `${row.publisher} · ` : ''}{row.transport === 'http' ? 'standalone server' : 'launched by your AI'}
                  </p>
                </div>
                {meta && (
                  <span className={cn('inline-flex shrink-0 items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium', meta.cls)}>
                    <span className={cn('h-1.5 w-1.5 rounded-full', meta.dot)} /> {meta.label}
                  </span>
                )}
              </div>

              <p className='line-clamp-2 text-sm text-muted-foreground'>{row.description}</p>

              {isWarden && wardenStatus && (
                <div className='rounded-md border border-border/70 bg-secondary/20 p-2 text-xs text-muted-foreground'>
                  {wardenStatus.installed ? (
                    <>
                      <p>
                        <span className='font-medium text-foreground'>Pinned {wardenStatus.active_version ?? wardenStatus.pinned_version}</span>
                        {' · '}{wardenStatus.verified ? 'verified' : 'verification unavailable'}
                      </p>
                      <p className='mt-1'>
                        Indexing {wardenStatus.registry?.indexed_stdio_servers.length ?? 0} local MCP server(s).
                        {(wardenStatus.registry?.skipped_http_servers.length ?? 0) > 0
                          ? ` ${wardenStatus.registry?.skipped_http_servers.length} HTTP server(s) stay directly available.`
                          : ''}
                      </p>
                    </>
                  ) : (
                    <p>Downloads a verified, immutable release into Synapse. Git and Python 3.10+ are required.</p>
                  )}
                </div>
              )}

              {row.tags.length > 0 && (
                <div className='flex flex-wrap gap-1'>
                  {row.tags.map((t) => (
                    <span key={t} className='rounded bg-secondary/50 px-1.5 py-0.5 text-[10px] text-muted-foreground'>{t}</span>
                  ))}
                </div>
              )}

              <div className='mt-auto flex flex-wrap items-center gap-2 pt-1'>
                {!row.installed ? (
                  <Button size='sm' disabled={busy === `install:${row.id}`} onClick={() => void run(`install:${row.id}`, () => installMcpServer({ catalog_id: row.id }))}>
                    {busy === `install:${row.id}` ? <Loader2 className='h-4 w-4 animate-spin' /> : <Download className='h-4 w-4' />}
                    {busy === `install:${row.id}` && isWarden ? 'Downloading & verifying…' : 'Install'}
                  </Button>
                ) : (
                  <>
                    {canLaunch && (
                      <Button size='sm' variant='outline' disabled={busy === `start:${row.id}`} onClick={() => void run(`start:${row.id}`, () => startMcpServer(row.id))}>
                        <Play className='h-4 w-4' /> Launch
                      </Button>
                    )}
                    {canStop && (
                      <Button size='sm' variant='ghost' disabled={busy === `stop:${row.id}`} onClick={() => void run(`stop:${row.id}`, () => stopMcpServer(row.id))}>
                        <Square className='h-4 w-4' /> Stop
                      </Button>
                    )}
                    {s && (
                      <button
                        type='button'
                        onClick={() => void run(`enable:${row.id}`, () => updateMcpServer(row.id, { enabled: !s.enabled }))}
                        className={cn('inline-flex items-center gap-1 rounded-md border px-2 py-1 text-xs', s.enabled ? 'border-primary/40 text-primary' : 'border-border text-muted-foreground')}
                        title={s.enabled ? 'Your AI can use this' : 'Disabled — not wired into your AI'}
                      >
                        <Check className='h-3.5 w-3.5' /> {s.enabled ? 'AI-enabled' : 'Disabled'}
                      </button>
                    )}
                    {isHttp && s && (
                      <button
                        type='button'
                        onClick={() => void run(`autorun:${row.id}`, () => updateMcpServer(row.id, { autorun: !s.autorun }))}
                        className={cn('inline-flex items-center gap-1 rounded-md border px-2 py-1 text-xs', s.autorun ? 'border-primary/40 text-primary' : 'border-border text-muted-foreground')}
                        title='Start automatically when Synapse launches'
                      >
                        <Zap className='h-3.5 w-3.5' /> Autorun
                      </button>
                    )}
                    {isWarden && s && (
                      <>
                        <Button
                          size='sm'
                          variant='outline'
                          disabled={busy === 'warden:sync'}
                          onClick={() => void run('warden:sync', syncWardenRegistry)}
                        >
                          {busy === 'warden:sync' ? <Loader2 className='h-4 w-4 animate-spin' /> : <RefreshCw className='h-4 w-4' />}
                          Sync
                        </Button>
                        {wardenStatus?.update_available && (
                          <Button size='sm' variant='outline' disabled={busy === 'warden:update'} onClick={() => void run('warden:update', updateWarden)}>
                            <Download className='h-4 w-4' /> Update
                          </Button>
                        )}
                        {wardenStatus?.rollback_available && (
                          <Button size='sm' variant='outline' disabled={busy === 'warden:rollback'} onClick={() => void run('warden:rollback', rollbackWarden)}>
                            <RotateCcw className='h-4 w-4' /> Restore {wardenStatus.rollback_version}
                          </Button>
                        )}
                      </>
                    )}
                    <Button
                      size='sm'
                      variant='ghost'
                      className='ml-auto text-destructive'
                      aria-label={`Uninstall ${row.name}`}
                      disabled={busy === `remove:${row.id}`}
                      onClick={() => void run(`remove:${row.id}`, () => removeMcpServer(row.id))}
                    >
                      <Trash2 className='h-4 w-4' />
                    </Button>
                  </>
                )}
              </div>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
