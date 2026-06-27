import { useCallback, useEffect, useMemo, useState } from 'react';
import { Aperture, BookTemplate, BrainCircuit, FolderSearch, GitBranchPlus, Layers3, Sparkles } from 'lucide-react';

import { PageHeader } from '../components/PageHeader';
import { Badge } from '../components/ui/badge';
import { Button } from '../components/ui/button';
import { Card } from '../components/ui/card';
import { useDaemon } from '@shared/daemon-context';
import { cn } from '@shared/utils';
import { createAiCase, getAiCaseMeta, listAiCases, openProjectInAiOs, runAiCase, stopAiCase } from '@shared/ai-cases-client';
import { getAiFactoryCatalog, type AiFactoryCatalogResponse } from '@shared/ai-factory-client';

type FactoryTab = 'recipes' | 'components' | 'sources' | 'cases';

const TABS: Array<{ id: FactoryTab; label: string; icon: typeof BookTemplate }> = [
  { id: 'recipes', label: 'Recipes', icon: BookTemplate },
  { id: 'components', label: 'Components', icon: Layers3 },
  { id: 'sources', label: 'Sources', icon: FolderSearch },
  { id: 'cases', label: 'Runs', icon: GitBranchPlus },
];

export function AiFactoryPage(): JSX.Element {
  const { projects, subscribeRaw } = useDaemon();
  const [catalog, setCatalog] = useState<AiFactoryCatalogResponse | null>(null);
  const [meta, setMeta] = useState<any>(null);
  const [cases, setCases] = useState<any[]>([]);
  const [tab, setTab] = useState<FactoryTab>('recipes');
  const [busy, setBusy] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [form, setForm] = useState({
    projectId: '',
    missionProfileId: '',
    caseMode: 'generate',
    recipeId: '',
    goal: '',
    success: '',
  });
  const [flash, setFlash] = useState<string | null>(null);

  useEffect(() => {
    if (!projects.length) return;
    setForm((current) => ({
      ...current,
      projectId: current.projectId || projects[0]?.id || '',
    }));
  }, [projects]);

  const refresh = useCallback(async (): Promise<void> => {
    const [catalogRes, metaRes, casesRes] = await Promise.all([
      getAiFactoryCatalog(),
      getAiCaseMeta(),
      listAiCases(),
    ]);
    setCatalog(catalogRes);
    setMeta(metaRes);
    setCases(casesRes.cases ?? []);
    if (!form.missionProfileId && metaRes.mission_profiles?.length) {
      setForm((current) => ({
        ...current,
        missionProfileId: current.missionProfileId || metaRes.mission_profiles[0].id,
        caseMode: current.missionProfileId ? current.caseMode : metaRes.mission_profiles[0].case_mode,
      }));
    }
  }, [form.missionProfileId]);

  const missionProfiles = meta?.mission_profiles ?? [];
  const listItems = useMemo(() => {
    if (!catalog) return [];
    if (tab === 'recipes') return catalog.catalog.recipes;
    if (tab === 'components') return catalog.catalog.components;
    if (tab === 'sources') return catalog.catalog.sources;
    return cases;
  }, [catalog, cases, tab]);
  const selected = useMemo(
    () => listItems.find((item: any) => item.id === selectedId) ?? listItems[0] ?? null,
    [listItems, selectedId]
  );

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(
    () =>
      subscribeRaw((event) => {
        if (event.name.startsWith('v1.ai_case.')) {
          void refresh();
        }
      }),
    [refresh, subscribeRaw]
  );

  function onMissionProfileChange(profileId: string): void {
    const profile = missionProfiles.find((item: any) => item.id === profileId);
    setForm((current) => ({
      ...current,
      missionProfileId: profileId,
      caseMode: profile?.case_mode || current.caseMode,
    }));
  }

  async function createCase(openInBoard: boolean): Promise<void> {
    if (!form.projectId || !form.goal.trim()) return;
    setBusy(true);
    try {
      const created = await createAiCase({
        case_mode: form.caseMode,
        mission_profile_id: form.missionProfileId || null,
        intent: {
          goal_md: form.goal.trim(),
          success_criteria_md: form.success.trim(),
          autonomy_mode: 'full_autopilot',
        },
        targets: {
          primary_project_id: form.projectId,
        },
        directives: {
          selected_recipe_id: form.recipeId || null,
          generation_mode: form.caseMode === 'generate' ? 'local_fullstack' : 'prototype',
        },
      });
      await refresh();
      setTab('cases');
      setSelectedId(created.case.id);
      setFlash('Case created.');
      if (openInBoard) {
        const launch = await openProjectInAiOs(form.projectId, [], created.case.id);
        const { openExternal } = await import('@shared/electron-bridge');
        await openExternal(launch.url);
      }
    } catch (error) {
      setFlash((error as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function runSelectedCase(): Promise<void> {
    if (!selected?.case?.id && !selected?.id) return;
    const caseId = selected?.case?.id || selected?.id;
    setBusy(true);
    try {
      await runAiCase(caseId, {});
      await refresh();
      setTab('cases');
      setSelectedId(caseId);
      setFlash('Run launched.');
    } catch (error) {
      setFlash((error as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function stopSelectedCase(): Promise<void> {
    if (!selected?.case?.id && !selected?.id) return;
    const caseId = selected?.case?.id || selected?.id;
    setBusy(true);
    try {
      await stopAiCase(caseId);
      await refresh();
      setTab('cases');
      setSelectedId(caseId);
      setFlash('Case stopped.');
    } catch (error) {
      setFlash((error as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className='flex h-full flex-col gap-4'>
      <PageHeader
        title='AI Factory'
        subtitle='The native Synapse surface for case design, recipe intelligence, sources, and the reusable pieces that make your AI workforce smarter over time.'
      />

      <div className='grid gap-4 xl:grid-cols-[380px_minmax(0,1fr)_360px]'>
        <Card className='overflow-hidden border-primary/20 bg-gradient-to-b from-card to-card/70 p-0'>
          <div className='border-b border-border/70 bg-gradient-to-r from-primary/10 to-transparent px-5 py-4'>
            <p className='text-xs font-semibold uppercase tracking-[0.24em] text-primary'>Launch Studio</p>
            <h2 className='mt-1 text-xl font-semibold tracking-tight'>Advanced case engine</h2>
            <p className='mt-2 text-sm text-muted-foreground'>
              Create a mission, bind it to a project, optionally anchor it on a recipe, and open it in the dedicated AI OS board.
            </p>
          </div>
          <div className='grid gap-4 p-5'>
            <label className='grid gap-2 text-sm'>
              <span className='text-muted-foreground'>Primary project</span>
              <select
                className='rounded-lg border border-border bg-background px-3 py-2'
                value={form.projectId}
                onChange={(e) => setForm((current) => ({ ...current, projectId: e.target.value }))}
              >
                {projects.map((project) => (
                  <option key={project.id} value={project.id}>
                    {project.name}
                  </option>
                ))}
              </select>
            </label>

            <label className='grid gap-2 text-sm'>
              <span className='text-muted-foreground'>Mission profile</span>
              <select
                className='rounded-lg border border-border bg-background px-3 py-2'
                value={form.missionProfileId}
                onChange={(e) => onMissionProfileChange(e.target.value)}
              >
                {missionProfiles.map((profile: any) => (
                  <option key={profile.id} value={profile.id}>
                    {profile.title}
                  </option>
                ))}
              </select>
            </label>

            <label className='grid gap-2 text-sm'>
              <span className='text-muted-foreground'>Case mode</span>
              <select
                className='rounded-lg border border-border bg-background px-3 py-2'
                value={form.caseMode}
                onChange={(e) => setForm((current) => ({ ...current, caseMode: e.target.value }))}
              >
                {(meta?.case_modes ?? []).map((mode: string) => (
                  <option key={mode} value={mode}>
                    {startCase(mode)}
                  </option>
                ))}
              </select>
            </label>

            <label className='grid gap-2 text-sm'>
              <span className='text-muted-foreground'>Seed recipe</span>
              <select
                className='rounded-lg border border-border bg-background px-3 py-2'
                value={form.recipeId}
                onChange={(e) => setForm((current) => ({ ...current, recipeId: e.target.value }))}
              >
                <option value=''>Auto / none</option>
                {(catalog?.catalog.recipes ?? []).map((recipe) => (
                  <option key={recipe.id} value={recipe.id}>
                    {recipe.name}
                  </option>
                ))}
              </select>
            </label>

            <label className='grid gap-2 text-sm'>
              <span className='text-muted-foreground'>Goal</span>
              <textarea
                className='min-h-28 rounded-lg border border-border bg-background px-3 py-2'
                value={form.goal}
                onChange={(e) => setForm((current) => ({ ...current, goal: e.target.value }))}
                placeholder='What should this case accomplish?'
              />
            </label>

            <label className='grid gap-2 text-sm'>
              <span className='text-muted-foreground'>Success criteria</span>
              <textarea
                className='min-h-24 rounded-lg border border-border bg-background px-3 py-2'
                value={form.success}
                onChange={(e) => setForm((current) => ({ ...current, success: e.target.value }))}
                placeholder='What would a clearly good result look like?'
              />
            </label>

            <div className='flex flex-wrap gap-2'>
              <Button disabled={busy || !form.projectId || !form.goal.trim()} onClick={() => void createCase(false)}>
                <Sparkles className='mr-2 h-4 w-4' />
                Create case
              </Button>
              <Button
                variant='secondary'
                disabled={busy || !form.projectId || !form.goal.trim()}
                onClick={() => void createCase(true)}
              >
                <BrainCircuit className='mr-2 h-4 w-4' />
                Create + open AI OS
              </Button>
            </div>

            <div className='grid grid-cols-3 gap-2'>
              <MetricCard label='Recipes' value={String(catalog?.counts.recipes ?? 0)} />
              <MetricCard label='Components' value={String(catalog?.counts.components ?? 0)} />
              <MetricCard label='Sources' value={String(catalog?.counts.sources ?? 0)} />
            </div>
          </div>
        </Card>

        <Card className='flex min-h-[640px] flex-col overflow-hidden p-0'>
          <div className='border-b border-border/70 px-5 py-4'>
            <div className='flex flex-wrap gap-2'>
              {TABS.map((item) => {
                const Icon = item.icon;
                const active = item.id === tab;
                return (
                  <button
                    key={item.id}
                    type='button'
                    onClick={() => setTab(item.id)}
                    className={cn(
                      'inline-flex items-center gap-2 rounded-full border px-3 py-2 text-sm transition-colors',
                      active
                        ? 'border-primary/30 bg-primary/10 text-foreground'
                        : 'border-border text-muted-foreground hover:bg-accent hover:text-foreground'
                    )}
                  >
                    <Icon className='h-4 w-4' />
                    {item.label}
                  </button>
                );
              })}
            </div>
          </div>
          <div className='grid flex-1 gap-3 overflow-y-auto p-5'>
            {listItems.map((item: any) => {
              const active = (item.case?.id || item.id) === (selected?.case?.id || selected?.id);
              const title = item.case?.title || item.name || item.label || item.case?.intent?.goal_md || item.case?.id || item.id;
              const subtitle =
                item.case?.mission_profile_id ||
                item.description ||
                item.provenance_summary ||
                item.family ||
                item.case?.case_mode;
              return (
                <button
                  key={item.case?.id || item.id}
                  type='button'
                  onClick={() => setSelectedId(item.case?.id || item.id)}
                  className={cn(
                    'rounded-2xl border p-4 text-left transition-colors',
                    active
                      ? 'border-primary/30 bg-primary/10'
                      : 'border-border bg-card hover:bg-accent/40'
                  )}
                >
                  <div className='flex flex-wrap items-start justify-between gap-3'>
                    <div>
                      <p className='font-medium'>{title}</p>
                      <p className='mt-1 text-sm text-muted-foreground'>{subtitle || 'No description yet.'}</p>
                    </div>
                    {'case' in item && item.case?.status && <Badge variant='outline'>{item.case.status}</Badge>}
                    {'archetype' in item && <Badge variant='secondary'>{item.archetype}</Badge>}
                    {'family' in item && <Badge variant='secondary'>{item.family}</Badge>}
                    {'source_type' in item && <Badge variant='secondary'>{item.source_type}</Badge>}
                  </div>
                </button>
              );
            })}
            {!listItems.length && (
              <div className='rounded-2xl border border-dashed border-border p-8 text-sm text-muted-foreground'>
                Nothing loaded here yet.
              </div>
            )}
          </div>
        </Card>

        <Card className='min-h-[640px] overflow-hidden p-0'>
          <div className='border-b border-border/70 bg-gradient-to-r from-primary/10 to-transparent px-5 py-4'>
            <p className='text-xs font-semibold uppercase tracking-[0.24em] text-primary'>Inspector</p>
            <h2 className='mt-1 text-xl font-semibold tracking-tight'>
              {selected?.case?.title || selected?.name || selected?.label || 'Select an item'}
            </h2>
          </div>
          <div className='grid gap-4 p-5'>
            {selected ? (
              <>
                {'case' in selected ? (
                  <>
                    <InspectorLine label='Mode' value={selected.case.case_mode} />
                    <InspectorLine label='Mission profile' value={selected.case.mission_profile_id || 'n/a'} />
                    <InspectorLine label='Status' value={selected.case.status} />
                    <InspectorLine label='Phase' value={selected.case.phase} />
                    <InspectorLine label='Primary project' value={selected.case.primary_project_id} />
                    <p className='rounded-2xl border border-border bg-secondary/40 p-4 text-sm text-muted-foreground'>
                      {selected.case.intent?.goal_md || 'No goal captured yet.'}
                    </p>
                    <div className='grid gap-2'>
                      <Button
                        disabled={busy || selected.case.status === 'running'}
                        onClick={() => void runSelectedCase()}
                      >
                        <Aperture className='mr-2 h-4 w-4' />
                        Run selected case
                      </Button>
                      <Button
                        variant='secondary'
                        disabled={busy || selected.case.status !== 'running'}
                        onClick={() => void stopSelectedCase()}
                      >
                        <Sparkles className='mr-2 h-4 w-4' />
                        Stop selected case
                      </Button>
                      <Button
                        variant='outline'
                        disabled={busy}
                        onClick={async () => {
                          const launch = await openProjectInAiOs(selected.case.primary_project_id, [], selected.case.id);
                          const { openExternal } = await import('@shared/electron-bridge');
                          await openExternal(launch.url);
                        }}
                      >
                        <BrainCircuit className='mr-2 h-4 w-4' />
                        Open in AI OS
                      </Button>
                    </div>
                  </>
                ) : (
                  <>
                    {'archetype' in selected && (
                      <>
                        <InspectorLine label='Archetype' value={selected.archetype} />
                        <InspectorLine label='Navigation' value={selected.nav_model} />
                        <InspectorLine label='Interaction' value={selected.interaction_model} />
                        <InspectorLine label='Visual language' value={selected.visual_language} />
                        <InspectorLine label='Data behavior' value={selected.data_behavior} />
                      </>
                    )}
                    {'family' in selected && <InspectorLine label='Family' value={selected.family} />}
                    {'source_type' in selected && (
                      <>
                        <InspectorLine label='Source type' value={selected.source_type} />
                        <InspectorLine label='Reuse posture' value={selected.reuse_posture} />
                      </>
                    )}
                    <p className='rounded-2xl border border-border bg-secondary/40 p-4 text-sm text-muted-foreground'>
                      {selected.description || selected.provenance_summary || selected.notes_md || 'No notes recorded yet.'}
                    </p>
                    {'component_ids' in selected && selected.component_ids?.length > 0 && (
                      <div className='flex flex-wrap gap-2'>
                        {selected.component_ids.slice(0, 8).map((id: string) => (
                          <Badge key={id} variant='outline'>
                            {id}
                          </Badge>
                        ))}
                      </div>
                    )}
                    {'tags' in selected && selected.tags?.length > 0 && (
                      <div className='flex flex-wrap gap-2'>
                        {selected.tags.slice(0, 8).map((tag: string) => (
                          <Badge key={tag} variant='secondary'>
                            {tag}
                          </Badge>
                        ))}
                      </div>
                    )}
                  </>
                )}
              </>
            ) : (
              <p className='text-sm text-muted-foreground'>Pick a recipe, component, source, or case to inspect it here.</p>
            )}

            {flash && (
              <div className='rounded-2xl border border-primary/20 bg-primary/10 px-4 py-3 text-sm text-foreground'>
                {flash}
              </div>
            )}
          </div>
        </Card>
      </div>
    </div>
  );
}

function MetricCard({ label, value }: { label: string; value: string }): JSX.Element {
  return (
    <div className='rounded-2xl border border-border bg-secondary/40 p-3'>
      <p className='text-xs uppercase tracking-[0.22em] text-muted-foreground'>{label}</p>
      <p className='mt-1 text-xl font-semibold'>{value}</p>
    </div>
  );
}

function InspectorLine({ label, value }: { label: string; value: string }): JSX.Element {
  return (
    <div className='grid grid-cols-[120px_1fr] gap-3 text-sm'>
      <span className='text-muted-foreground'>{label}</span>
      <span className='break-words'>{startCase(value)}</span>
    </div>
  );
}

function startCase(value: string): string {
  return String(value || '')
    .split('-')
    .join(' ')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase());
}
