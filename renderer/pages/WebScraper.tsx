import { type ReactNode, useEffect, useMemo, useRef, useState } from 'react';
import {
  ExternalLink,
  Globe,
  Loader2,
  RefreshCw,
  Save,
  Search,
  Sparkles,
  Wifi,
  WifiOff,
} from 'lucide-react';

import { useDaemon } from '@shared/daemon-context';
import {
  getWebScraperActive,
  getWebScraperHarvestCapabilities,
  getWebScraperOverview,
  getWebScraperSaves,
  getWebScraperSchedules,
  runWebScraperHarvestAction,
  saveWebScraperHarvestArtifacts,
  scrapeWebScraperUrl,
  type WebScraperHarvestCapabilities,
  type WebScraperOverview,
} from '@shared/installed-pages-client';
import { openExternal } from '@shared/electron-bridge';
import { cn } from '@shared/utils';
import { Button } from '../components/ui/button';
import { Card } from '../components/ui/card';
import { Input } from '../components/ui/input';
import { PageHeader } from '../components/PageHeader';

type HarvestOutputKey = 'capture' | 'summary' | 'brief' | 'styles' | 'structure' | 'react' | 'css';

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
  const candidates = [item.title, item.name, item.url, item.public_url, item.id];
  const label = candidates.find((value): value is string => typeof value === 'string' && value.trim().length > 0);
  return label ?? 'Untitled item';
}

function itemMeta(item: Record<string, unknown>): string | null {
  const parts = [item.status, item.updated_at, item.created_at]
    .filter((value): value is string => typeof value === 'string' && value.trim().length > 0)
    .slice(0, 2);
  return parts.length > 0 ? parts.join(' · ') : null;
}

function parseReferenceUrls(value: string): string[] {
  return value
    .split(/\r?\n|,/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function stringifyPayload(payload: unknown): string {
  if (payload == null) return '';
  if (typeof payload === 'string') return payload;
  return JSON.stringify(payload, null, 2);
}

function pickCode(payload: unknown, keys: string[]): string {
  if (typeof payload === 'string') return payload;
  if (!payload || typeof payload !== 'object') return '';
  const obj = payload as Record<string, unknown>;
  for (const key of keys) {
    if (typeof obj[key] === 'string' && obj[key]!.trim().length > 0) {
      return obj[key] as string;
    }
  }
  return JSON.stringify(obj, null, 2);
}

export function WebScraperPage(): JSX.Element {
  const { projects } = useDaemon();
  const [overview, setOverview] = useState<WebScraperOverview | null>(null);
  const [capabilities, setCapabilities] = useState<WebScraperHarvestCapabilities | null>(null);
  const [saves, setSaves] = useState<Array<Record<string, unknown>>>([]);
  const [schedules, setSchedules] = useState<Array<Record<string, unknown>>>([]);
  const [active, setActive] = useState<Array<Record<string, unknown>>>([]);
  const [loading, setLoading] = useState(true);
  const [detailsLoading, setDetailsLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [harvestBusy, setHarvestBusy] = useState<string | null>(null);
  const [url, setUrl] = useState('');
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [referenceUrls, setReferenceUrls] = useState('');
  const [goal, setGoal] = useState('Turn these references into reusable components, tokens, and layout notes for the target project.');
  const [provenanceMode, setProvenanceMode] = useState('inspiration-only');
  const [originalityNotes, setOriginalityNotes] = useState(
    'Regenerate the strengths, but make the output clearly belong to the target project.'
  );
  const [targetProjectId, setTargetProjectId] = useState<string>('');
  const [harvestOutputs, setHarvestOutputs] = useState<Partial<Record<HarvestOutputKey, unknown>>>({});
  const [savedArtifacts, setSavedArtifacts] = useState<Array<Record<string, unknown>>>([]);
  const refreshTokenRef = useRef(0);

  const sortedProjects = useMemo(
    () =>
      [...projects].sort((a, b) => {
        if (a.pinned !== b.pinned) return a.pinned ? -1 : 1;
        return a.name.localeCompare(b.name);
      }),
    [projects]
  );

  useEffect(() => {
    if (!targetProjectId && sortedProjects.length > 0) {
      setTargetProjectId(sortedProjects[0]!.id);
    }
  }, [sortedProjects, targetProjectId]);

  async function loadConnectedCollections(refreshToken: number): Promise<void> {
    setDetailsLoading(true);
    const [nextSaves, nextSchedules, nextActive, nextCapabilities] = await Promise.allSettled([
      getWebScraperSaves(),
      getWebScraperSchedules(),
      getWebScraperActive(),
      getWebScraperHarvestCapabilities(),
    ]);
    if (refreshToken !== refreshTokenRef.current) return;

    setSaves(nextSaves.status === 'fulfilled' ? extractList(nextSaves.value) : []);
    setSchedules(nextSchedules.status === 'fulfilled' ? extractList(nextSchedules.value) : []);
    setActive(nextActive.status === 'fulfilled' ? extractList(nextActive.value) : []);
    setCapabilities(nextCapabilities.status === 'fulfilled' ? nextCapabilities.value : null);
    if (
      nextSaves.status === 'rejected' ||
      nextSchedules.status === 'rejected' ||
      nextActive.status === 'rejected' ||
      nextCapabilities.status === 'rejected'
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
        setCapabilities(null);
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

  async function runHarvest(action: string, target: HarvestOutputKey): Promise<void> {
    const urls = parseReferenceUrls(referenceUrls);
    if (urls.length === 0) {
      setError('Enter at least one authorized reference URL before running a harvest pass.');
      return;
    }
    setHarvestBusy(action);
    setError(null);
    setNotice(null);
    try {
      const payload = await runWebScraperHarvestAction(action, {
        url: urls[0],
        urls,
        goal,
        prompt: goal,
        project_id: targetProjectId || undefined,
        provenance_mode: provenanceMode,
        originality_notes: originalityNotes,
      });
      setHarvestOutputs((current) => ({ ...current, [target]: payload }));
      setNotice(`Harvest step completed: ${action}.`);
    } catch (err) {
      setError((err as Error).message || `Could not run harvest action ${action}.`);
    } finally {
      setHarvestBusy(null);
    }
  }

  async function saveHarvestResult(): Promise<void> {
    const urls = parseReferenceUrls(referenceUrls);
    if (!targetProjectId) {
      setError('Choose a target project before saving harvest artifacts.');
      return;
    }
    const artifacts = [
      harvestOutputs.brief
        ? {
            name: 'reference-brief.md',
            kind: 'reference-brief',
            mime: 'text/markdown',
            content: pickCode(harvestOutputs.brief, ['markdown', 'content', 'text']),
          }
        : null,
      harvestOutputs.structure || harvestOutputs.summary
        ? {
            name: 'structure-summary.md',
            kind: 'structure-summary',
            mime: 'text/markdown',
            content: pickCode(harvestOutputs.structure ?? harvestOutputs.summary, ['markdown', 'summary', 'content', 'text']),
          }
        : null,
      harvestOutputs.styles
        ? {
            name: 'style-summary.md',
            kind: 'style-summary',
            mime: 'text/markdown',
            content: pickCode(harvestOutputs.styles, ['markdown', 'summary', 'content', 'text']),
          }
        : null,
      harvestOutputs.react
        ? {
            name: 'component-candidate.tsx',
            kind: 'component-candidate',
            mime: 'text/plain',
            content: pickCode(harvestOutputs.react, ['component', 'code', 'tsx', 'react']),
          }
        : null,
      harvestOutputs.css
        ? {
            name: 'component-candidate.css',
            kind: 'style-tokens',
            mime: 'text/css',
            content: pickCode(harvestOutputs.css, ['css', 'code', 'content']),
          }
        : null,
      {
        name: 'originality-notes.md',
        kind: 'originality-notes',
        mime: 'text/markdown',
        content: [
          `Provenance mode: ${provenanceMode}`,
          '',
          `Reference URLs:`,
          ...urls.map((item) => `- ${item}`),
          '',
          originalityNotes || 'No additional originality notes were provided.',
        ].join('\n'),
      },
    ].filter(Boolean) as Array<{
      name: string;
      kind: string;
      mime: string;
      content: string;
    }>;
    if (artifacts.length === 0) {
      setError('Run at least one harvest step before saving.');
      return;
    }
    setHarvestBusy('save');
    setError(null);
    try {
      const saved = await saveWebScraperHarvestArtifacts({
        project_id: targetProjectId,
        reference_urls: urls,
        provenance_mode: provenanceMode,
        originality_notes: originalityNotes,
        artifacts,
      });
      setSavedArtifacts(saved.saved);
      setNotice(`Saved ${saved.saved.length} project artifacts for the harvest result.`);
    } catch (err) {
      setError((err as Error).message || 'Could not save harvest artifacts.');
    } finally {
      setHarvestBusy(null);
    }
  }

  const counts = useMemo(
    () => [
      { label: 'Saved runs', value: saves.length },
      { label: 'Schedules', value: schedules.length },
      { label: 'Active jobs', value: active.length },
      { label: 'Harvest actions', value: capabilities?.actions.length ?? 0 },
    ],
    [active.length, capabilities?.actions.length, saves.length, schedules.length]
  );

  const referencePanels = [
    {
      title: 'Reference brief',
      value: stringifyPayload(harvestOutputs.brief),
    },
    {
      title: 'Structure notes',
      value: stringifyPayload(harvestOutputs.structure ?? harvestOutputs.summary),
    },
    {
      title: 'Style notes',
      value: stringifyPayload(harvestOutputs.styles),
    },
  ];

  const generatedPanels = [
    {
      title: 'React candidate',
      value: pickCode(harvestOutputs.react, ['component', 'code', 'tsx', 'react']),
      language: 'tsx',
    },
    {
      title: 'CSS candidate',
      value: pickCode(harvestOutputs.css, ['css', 'code', 'content']),
      language: 'css',
    },
  ];

  return (
    <div className='flex flex-col gap-6'>
      <PageHeader
        title='Web Scraper'
        subtitle='A dedicated workspace for your installed Web Scraper MCP server, with design harvest, provenance capture, and project-file handoff built in.'
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
                  {overview?.detail ?? 'Synapse found your scraper and can route this page through the daemon.'}
                </p>
                {detailsLoading && (
                  <p className='text-xs text-muted-foreground'>Refreshing scraper activity...</p>
                )}
              </div>

              <div className='flex flex-wrap gap-2'>
                {overview?.ui_url && (
                  <Button variant='outline' size='sm' onClick={() => void openExternal(overview.ui_url!)}>
                    <ExternalLink className='h-4 w-4' />
                    Open scraper UI
                  </Button>
                )}
                {overview?.docs_url && (
                  <Button variant='outline' size='sm' onClick={() => void openExternal(overview.docs_url!)}>
                    <ExternalLink className='h-4 w-4' />
                    Open docs
                  </Button>
                )}
              </div>
            </div>

            <div className='grid grid-cols-[repeat(auto-fit,minmax(160px,1fr))] gap-3'>
              {counts.map((item) => (
                <div key={item.label} className='rounded-xl border border-border bg-secondary/30 p-4'>
                  <p className='text-xs uppercase tracking-[0.2em] text-muted-foreground'>{item.label}</p>
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
                  The installed page stays visible because Synapse still recognizes your scraper. Start or reconnect the MCP server, then refresh this page.
                </p>
              </div>
            </Card>
          ) : (
            <>
              <div className='grid gap-4 xl:grid-cols-[1.1fr_0.9fr]'>
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

                <Card className='flex flex-col gap-3 p-6'>
                  <div className='flex items-center gap-2'>
                    <Sparkles className='h-4 w-4 text-primary' />
                    <h2 className='text-lg font-semibold'>Design-harvest signals</h2>
                  </div>
                  <p className='text-sm text-muted-foreground'>
                    Provenance stays explicit all the way from reference capture to adopted project artifacts.
                  </p>
                  <div className='grid gap-2 text-sm'>
                    {(capabilities?.adaptation_modes ?? [
                      { id: 'inspiration-only', label: 'Inspiration only' },
                      { id: 'licensed-close-copy', label: 'Licensed close-copy' },
                      { id: 'regenerated-original-output', label: 'Regenerated original output' },
                    ]).map((mode) => (
                      <div key={mode.id} className='rounded-lg border border-border bg-secondary/20 px-3 py-2'>
                        <p className='font-medium'>{mode.label}</p>
                        <p className='mt-1 text-xs text-muted-foreground'>
                          {mode.id === provenanceMode ? 'Current adaptation mode for this harvest run.' : 'Available adaptation mode.'}
                        </p>
                      </div>
                    ))}
                  </div>
                </Card>
              </div>

              <Card className='flex flex-col gap-5 p-6'>
                <div className='space-y-2'>
                  <p className='text-xs font-semibold uppercase tracking-[0.2em] text-primary/85'>Design harvest workspace</p>
                  <h2 className='text-xl font-semibold'>Reference {'->'} generated result {'->'} adopted result</h2>
                  <p className='text-sm text-muted-foreground'>
                    Capture authorized references, generate candidate components and tokens, then save the artifacts directly into a project with provenance and originality notes.
                  </p>
                </div>

                <div className='grid gap-4 lg:grid-cols-2'>
                  <label className='flex flex-col gap-2 text-sm'>
                    <span className='font-medium'>Authorized reference URLs</span>
                    <textarea
                      value={referenceUrls}
                      onChange={(event) => setReferenceUrls(event.target.value)}
                      placeholder={'https://example.com\nhttps://example.com/pricing'}
                      rows={5}
                      className='min-h-[120px] rounded-xl border border-border bg-background px-3 py-2 text-sm outline-none transition focus:border-primary/50'
                    />
                  </label>
                  <div className='grid gap-4'>
                    <label className='flex flex-col gap-2 text-sm'>
                      <span className='font-medium'>Target project</span>
                      <select
                        value={targetProjectId}
                        onChange={(event) => setTargetProjectId(event.target.value)}
                        className='rounded-xl border border-border bg-background px-3 py-2 text-sm outline-none transition focus:border-primary/50'
                      >
                        {sortedProjects.map((project) => (
                          <option key={project.id} value={project.id}>
                            {project.name}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className='flex flex-col gap-2 text-sm'>
                      <span className='font-medium'>Provenance / adaptation mode</span>
                      <select
                        value={provenanceMode}
                        onChange={(event) => setProvenanceMode(event.target.value)}
                        className='rounded-xl border border-border bg-background px-3 py-2 text-sm outline-none transition focus:border-primary/50'
                      >
                        {(capabilities?.adaptation_modes ?? []).map((mode) => (
                          <option key={mode.id} value={mode.id}>
                            {mode.label}
                          </option>
                        ))}
                        {!capabilities && (
                          <option value='inspiration-only'>Inspiration only</option>
                        )}
                      </select>
                    </label>
                  </div>
                </div>

                <label className='flex flex-col gap-2 text-sm'>
                  <span className='font-medium'>Harvest goal</span>
                  <textarea
                    value={goal}
                    onChange={(event) => setGoal(event.target.value)}
                    rows={3}
                    className='rounded-xl border border-border bg-background px-3 py-2 text-sm outline-none transition focus:border-primary/50'
                  />
                </label>

                <label className='flex flex-col gap-2 text-sm'>
                  <span className='font-medium'>Originality notes</span>
                  <textarea
                    value={originalityNotes}
                    onChange={(event) => setOriginalityNotes(event.target.value)}
                    rows={3}
                    className='rounded-xl border border-border bg-background px-3 py-2 text-sm outline-none transition focus:border-primary/50'
                  />
                </label>

                <div className='flex flex-wrap gap-2'>
                  <Button
                    variant='outline'
                    disabled={harvestBusy !== null}
                    onClick={() => void runHarvest('capture', 'capture')}
                  >
                    {harvestBusy === 'capture' ? <Loader2 className='h-4 w-4 animate-spin' /> : <Globe className='h-4 w-4' />}
                    Capture
                  </Button>
                  <Button
                    variant='outline'
                    disabled={harvestBusy !== null}
                    onClick={() => void runHarvest('research_url', 'summary')}
                  >
                    {harvestBusy === 'research_url' ? <Loader2 className='h-4 w-4 animate-spin' /> : <Search className='h-4 w-4' />}
                    Summarize
                  </Button>
                  <Button
                    variant='outline'
                    disabled={harvestBusy !== null}
                    onClick={() => void runHarvest('to_markdown', 'brief')}
                  >
                    {harvestBusy === 'to_markdown' ? <Loader2 className='h-4 w-4 animate-spin' /> : <Sparkles className='h-4 w-4' />}
                    Reference brief
                  </Button>
                  <Button
                    variant='outline'
                    disabled={harvestBusy !== null}
                    onClick={() => void runHarvest('extract_styles', 'styles')}
                  >
                    {harvestBusy === 'extract_styles' ? <Loader2 className='h-4 w-4 animate-spin' /> : <Sparkles className='h-4 w-4' />}
                    Extract styles
                  </Button>
                  <Button
                    variant='outline'
                    disabled={harvestBusy !== null}
                    onClick={() => void runHarvest('extract_structure', 'structure')}
                  >
                    {harvestBusy === 'extract_structure' ? <Loader2 className='h-4 w-4 animate-spin' /> : <Sparkles className='h-4 w-4' />}
                    Extract structure
                  </Button>
                  <Button
                    variant='outline'
                    disabled={harvestBusy !== null}
                    onClick={() => void runHarvest('generate_react', 'react')}
                  >
                    {harvestBusy === 'generate_react' ? <Loader2 className='h-4 w-4 animate-spin' /> : <Sparkles className='h-4 w-4' />}
                    Generate React
                  </Button>
                  <Button
                    variant='outline'
                    disabled={harvestBusy !== null}
                    onClick={() => void runHarvest('generate_css', 'css')}
                  >
                    {harvestBusy === 'generate_css' ? <Loader2 className='h-4 w-4 animate-spin' /> : <Sparkles className='h-4 w-4' />}
                    Generate CSS
                  </Button>
                  <Button disabled={harvestBusy !== null} onClick={() => void saveHarvestResult()}>
                    {harvestBusy === 'save' ? <Loader2 className='h-4 w-4 animate-spin' /> : <Save className='h-4 w-4' />}
                    Save artifacts
                  </Button>
                </div>
              </Card>

              <div className='grid gap-4 xl:grid-cols-3'>
                <ColumnCard
                  title='Reference'
                  subtitle='Authorized sources plus the harvested summaries that describe them.'
                >
                  <div className='rounded-xl border border-border bg-secondary/20 p-3 text-sm'>
                    <p className='text-xs uppercase tracking-[0.18em] text-muted-foreground'>Reference URLs</p>
                    <div className='mt-2 whitespace-pre-wrap text-foreground'>
                      {parseReferenceUrls(referenceUrls).join('\n') || 'No reference URLs yet.'}
                    </div>
                  </div>
                  {referencePanels.map((panel) => (
                    <ArtifactPreview key={panel.title} title={panel.title} value={panel.value} />
                  ))}
                </ColumnCard>

                <ColumnCard
                  title='Generated result'
                  subtitle='Candidate implementation artifacts coming back from the harvest engine.'
                >
                  {generatedPanels.map((panel) => (
                    <ArtifactPreview key={panel.title} title={panel.title} value={panel.value} mono />
                  ))}
                </ColumnCard>

                <ColumnCard
                  title='Adopted result'
                  subtitle='Saved project files plus the provenance mode that explains how they can be used.'
                >
                  <div className='rounded-xl border border-border bg-secondary/20 p-3 text-sm'>
                    <p className='text-xs uppercase tracking-[0.18em] text-muted-foreground'>Provenance mode</p>
                    <p className='mt-2 font-medium capitalize'>{provenanceMode.replace(/-/g, ' ')}</p>
                    <p className='mt-2 whitespace-pre-wrap text-muted-foreground'>
                      {originalityNotes || 'No originality notes yet.'}
                    </p>
                  </div>
                  {savedArtifacts.length === 0 ? (
                    <p className='text-sm text-muted-foreground'>
                      Save the harvest result to create project artifacts here.
                    </p>
                  ) : (
                    <ul className='flex flex-col gap-2'>
                      {savedArtifacts.map((artifact, index) => (
                        <li
                          key={`${artifact.id ?? artifact.original_name ?? index}`}
                          className='rounded-xl border border-border bg-secondary/20 px-3 py-2 text-sm'
                        >
                          <p className='font-medium'>{String(artifact.original_name ?? 'artifact')}</p>
                          <p className='mt-1 text-xs text-muted-foreground'>
                            {(artifact.mime as string | undefined) ?? 'saved to project files'}
                          </p>
                        </li>
                      ))}
                    </ul>
                  )}
                </ColumnCard>
              </div>

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

function ColumnCard({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle: string;
  children: ReactNode;
}): JSX.Element {
  return (
    <Card className='flex flex-col gap-3 p-5'>
      <div className='space-y-1'>
        <h3 className='text-base font-semibold'>{title}</h3>
        <p className='text-sm text-muted-foreground'>{subtitle}</p>
      </div>
      {children}
    </Card>
  );
}

function ArtifactPreview({
  title,
  value,
  mono = false,
}: {
  title: string;
  value: string;
  mono?: boolean;
}): JSX.Element {
  return (
    <div className='rounded-xl border border-border bg-secondary/20 p-3'>
      <p className='text-xs uppercase tracking-[0.18em] text-muted-foreground'>{title}</p>
      <pre
        className={cn(
          'mt-2 max-h-56 overflow-y-auto whitespace-pre-wrap break-words text-sm text-foreground',
          mono ? 'font-mono leading-5' : 'leading-6'
        )}
      >
        {value || 'Not generated yet.'}
      </pre>
    </div>
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
              {itemMeta(item) && <p className='mt-1 text-xs text-muted-foreground'>{itemMeta(item)}</p>}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
