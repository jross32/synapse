import { useEffect, useMemo, useRef, useState } from 'react';
import {
  ExternalLink,
  Globe,
  Loader2,
  RefreshCw,
  Search,
  Wifi,
  WifiOff,
} from 'lucide-react';

import {
  getWebScraperActive,
  getWebScraperOverview,
  getWebScraperSaves,
  getWebScraperSchedules,
  scrapeWebScraperUrl,
  type WebScraperOverview,
} from '@shared/installed-pages-client';
import { openExternal } from '@shared/electron-bridge';
import { cn } from '@shared/utils';
import { Button } from '../components/ui/button';
import { Card } from '../components/ui/card';
import { Input } from '../components/ui/input';
import { PageHeader } from '../components/PageHeader';

function extractList(payload: unknown): Array<Record<string, unknown>> {
  if (Array.isArray(payload)) {
    return payload.filter((item): item is Record<string, unknown> => !!item && typeof item === 'object');
  }
  if (!payload || typeof payload !== 'object') return [];
  const obj = payload as Record<string, unknown>;
  for (const key of ['items', 'saves', 'schedules', 'active', 'data', 'results']) {
    const value = obj[key];
    if (Array.isArray(value)) {
      return value.filter((item): item is Record<string, unknown> => !!item && typeof item === 'object');
    }
  }
  return [];
}

function itemLabel(item: Record<string, unknown>): string {
  const candidates = [
    item.title,
    item.name,
    item.url,
    item.public_url,
    item.id,
  ];
  const label = candidates.find((value): value is string => typeof value === 'string' && value.trim().length > 0);
  return label ?? 'Untitled item';
}

function itemMeta(item: Record<string, unknown>): string | null {
  const parts = [item.status, item.updated_at, item.created_at]
    .filter((value): value is string => typeof value === 'string' && value.trim().length > 0)
    .slice(0, 2);
  return parts.length > 0 ? parts.join(' · ') : null;
}

export function WebScraperPage(): JSX.Element {
  const [overview, setOverview] = useState<WebScraperOverview | null>(null);
  const [saves, setSaves] = useState<Array<Record<string, unknown>>>([]);
  const [schedules, setSchedules] = useState<Array<Record<string, unknown>>>([]);
  const [active, setActive] = useState<Array<Record<string, unknown>>>([]);
  const [loading, setLoading] = useState(true);
  const [detailsLoading, setDetailsLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [url, setUrl] = useState('');
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const refreshTokenRef = useRef(0);

  async function loadConnectedCollections(refreshToken: number): Promise<void> {
    setDetailsLoading(true);
    const [nextSaves, nextSchedules, nextActive] = await Promise.allSettled([
      getWebScraperSaves(),
      getWebScraperSchedules(),
      getWebScraperActive(),
    ]);
    if (refreshToken !== refreshTokenRef.current) return;

    setSaves(nextSaves.status === 'fulfilled' ? extractList(nextSaves.value) : []);
    setSchedules(nextSchedules.status === 'fulfilled' ? extractList(nextSchedules.value) : []);
    setActive(nextActive.status === 'fulfilled' ? extractList(nextActive.value) : []);
    if (
      nextSaves.status === 'rejected' ||
      nextSchedules.status === 'rejected' ||
      nextActive.status === 'rejected'
    ) {
      setError((current) => current ?? 'Connected, but some Web Scraper activity could not be loaded.');
    }
    setDetailsLoading(false);
  }

  async function refresh(showSpinner = true): Promise<void> {
    const refreshToken = refreshTokenRef.current + 1;
    refreshTokenRef.current = refreshToken;
    if (showSpinner) setRefreshing(true);
    setError(null);
    try {
      const nextOverview = await getWebScraperOverview();
      if (refreshToken !== refreshTokenRef.current) return;
      setOverview(nextOverview);
      setLoading(false);
      if (nextOverview.status === 'connected') {
        void loadConnectedCollections(refreshToken);
      } else {
        setSaves([]);
        setSchedules([]);
        setActive([]);
        setDetailsLoading(false);
      }
    } catch (err) {
      if (refreshToken !== refreshTokenRef.current) return;
      setError((err as Error).message || 'Could not load the Web Scraper page.');
      setLoading(false);
      setDetailsLoading(false);
    } finally {
      if (refreshToken === refreshTokenRef.current && showSpinner) setRefreshing(false);
    }
  }

  useEffect(() => {
    void refresh(false);
    return () => {
      refreshTokenRef.current += 1;
    };
  }, []);

  async function submitQuickScrape(): Promise<void> {
    const nextUrl = url.trim();
    if (!nextUrl) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const payload = await scrapeWebScraperUrl({ url: nextUrl });
      if (payload && typeof payload === 'object') {
        const dict = payload as Record<string, unknown>;
        const id = [dict.save_id, dict.id, dict.job_id].find(
          (value): value is string => typeof value === 'string' && value.length > 0
        );
        setNotice(id ? `Scrape submitted (${id}).` : 'Scrape submitted.');
      } else {
        setNotice('Scrape submitted.');
      }
      setUrl('');
      await refresh(false);
    } catch (err) {
      setError((err as Error).message || 'Could not start the scrape.');
    } finally {
      setBusy(false);
    }
  }

  const counts = useMemo(
    () => [
      { label: 'Saved runs', value: saves.length },
      { label: 'Schedules', value: schedules.length },
      { label: 'Active jobs', value: active.length },
      { label: 'Tools exposed', value: overview?.tool_count ?? 0 },
    ],
    [active.length, overview?.tool_count, saves.length, schedules.length]
  );

  return (
    <div className='flex flex-col gap-6'>
      <PageHeader
        title='Web Scraper'
        subtitle='A dedicated workspace for your installed Web Scraper MCP server, routed through Synapse.'
        action={
          <Button variant='outline' onClick={() => void refresh()} disabled={refreshing}>
            {refreshing ? (
              <Loader2 className='h-4 w-4 animate-spin' />
            ) : (
              <RefreshCw className='h-4 w-4' />
            )}
            Refresh
          </Button>
        }
      />

      {loading ? (
        <Card className='flex items-center gap-2 p-6 text-sm text-muted-foreground'>
          <Loader2 className='h-4 w-4 animate-spin' /> Loading Web Scraper...
        </Card>
      ) : (
        <>
          {error && (
            <p role='alert' className='text-sm text-destructive'>
              {error}
            </p>
          )}
          {notice && (
            <p role='status' className='text-sm text-emerald-300'>
              {notice}
            </p>
          )}

          <Card className='flex flex-col gap-4 p-6'>
            <div className='flex flex-wrap items-start justify-between gap-3'>
              <div className='space-y-2'>
                <div className='flex items-center gap-2'>
                  <Globe className='h-5 w-5 text-primary' />
                  <h2 className='text-lg font-semibold'>{overview?.label ?? 'Web Scraper'}</h2>
                  <StatusPill status={overview?.status ?? 'offline'} />
                </div>
                <p className='text-sm text-muted-foreground'>
                  {overview?.detail ??
                    'Synapse found your scraper and can route this page through the daemon.'}
                </p>
                {detailsLoading && (
                  <p className='text-xs text-muted-foreground'>Refreshing scraper activity...</p>
                )}
              </div>

              <div className='flex flex-wrap gap-2'>
                {overview?.ui_url && (
                  <Button
                    variant='outline'
                    size='sm'
                    onClick={() => void openExternal(overview.ui_url!)}
                  >
                    <ExternalLink className='h-4 w-4' />
                    Open scraper UI
                  </Button>
                )}
                {overview?.docs_url && (
                  <Button
                    variant='outline'
                    size='sm'
                    onClick={() => void openExternal(overview.docs_url!)}
                  >
                    <ExternalLink className='h-4 w-4' />
                    Open docs
                  </Button>
                )}
              </div>
            </div>

            <div className='grid grid-cols-[repeat(auto-fit,minmax(160px,1fr))] gap-3'>
              {counts.map((item) => (
                <div key={item.label} className='rounded-xl border border-border bg-secondary/30 p-4'>
                  <p className='text-xs uppercase tracking-[0.2em] text-muted-foreground'>
                    {item.label}
                  </p>
                  <p className='mt-2 text-2xl font-semibold'>{item.value}</p>
                </div>
              ))}
            </div>
          </Card>

          {overview?.status !== 'connected' ? (
            <Card className='flex flex-col gap-4 border-dashed p-8 text-center'>
              <div className='mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-secondary'>
                <WifiOff className='h-7 w-7 text-muted-foreground' />
              </div>
              <div className='space-y-2'>
                <h2 className='text-lg font-semibold'>Web Scraper is currently offline</h2>
                <p className='mx-auto max-w-xl text-sm text-muted-foreground'>
                  The installed page stays visible because Synapse still recognizes your
                  scraper. Start or reconnect the MCP server, then refresh this page.
                </p>
              </div>
            </Card>
          ) : (
            <>
              <Card className='flex flex-col gap-4 p-6'>
                <div className='flex items-center gap-2'>
                  <Wifi className='h-4 w-4 text-emerald-300' />
                  <h2 className='text-lg font-semibold'>Quick scrape</h2>
                </div>
                <p className='text-sm text-muted-foreground'>
                  Send a URL through the Synapse proxy and let the scraper capture it.
                </p>
                <div className='flex flex-col gap-3 md:flex-row'>
                  <Input
                    value={url}
                    onChange={(event) => setUrl(event.target.value)}
                    placeholder='https://example.com/article'
                    aria-label='URL to scrape'
                  />
                  <Button onClick={() => void submitQuickScrape()} disabled={busy || !url.trim()}>
                    {busy ? (
                      <Loader2 className='h-4 w-4 animate-spin' />
                    ) : (
                      <Search className='h-4 w-4' />
                    )}
                    Scrape URL
                  </Button>
                </div>
              </Card>

              <div className='grid gap-4 xl:grid-cols-3'>
                <RecentListCard title='Recent saves' items={saves} loading={detailsLoading} />
                <RecentListCard title='Schedules' items={schedules} loading={detailsLoading} />
                <RecentListCard title='Active jobs' items={active} loading={detailsLoading} />
              </div>
            </>
          )}
        </>
      )}
    </div>
  );
}

function StatusPill({
  status,
}: {
  status: WebScraperOverview['status'];
}): JSX.Element {
  const meta: Record<WebScraperOverview['status'], { label: string; cls: string }> = {
    connected: { label: 'Connected', cls: 'bg-emerald-500/15 text-emerald-300' },
    available: { label: 'Available', cls: 'bg-sky-500/15 text-sky-200' },
    offline: { label: 'Offline', cls: 'bg-secondary/70 text-muted-foreground' },
    error: { label: 'Error', cls: 'bg-destructive/15 text-destructive' },
  };
  return (
    <span className={cn('rounded-full px-2 py-0.5 text-[11px] font-medium', meta[status].cls)}>
      {meta[status].label}
    </span>
  );
}

function RecentListCard({
  title,
  items,
  loading,
}: {
  title: string;
  items: Array<Record<string, unknown>>;
  loading?: boolean;
}): JSX.Element {
  return (
    <Card className='flex flex-col gap-3 p-5'>
      <div className='flex items-center justify-between gap-2'>
        <h3 className='text-base font-semibold'>{title}</h3>
        <span className='text-xs text-muted-foreground'>{items.length}</span>
      </div>
      {items.length === 0 ? (
        <p className='text-sm text-muted-foreground'>
          {loading ? 'Loading activity...' : 'Nothing to show yet.'}
        </p>
      ) : (
        <ul className='flex flex-col gap-2'>
          {items.slice(0, 5).map((item, index) => (
            <li key={`${title}-${index}`} className='rounded-lg border border-border bg-secondary/20 px-3 py-2'>
              <p className='truncate text-sm font-medium'>{itemLabel(item)}</p>
              {itemMeta(item) && (
                <p className='mt-1 text-xs text-muted-foreground'>{itemMeta(item)}</p>
              )}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
