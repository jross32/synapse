// What's New + Roadmap (ADR-0019). Two views: a changelog of what shipped, and
// a roadmap "path" (shipped -> in the works -> coming) so users + the AI working
// on the project can see where Synapse is headed.

import { useEffect, useState } from 'react';
import { CheckCircle2, CircleDashed, Loader2, Rocket, Sparkles } from 'lucide-react';

import {
  getChangelog,
  getRoadmap,
  type Changelog,
  type Roadmap,
  type RoadmapStatus,
} from '@shared/about-client';
import { cn } from '@shared/utils';
import { Card } from '../components/ui/card';
import { PageHeader } from '../components/PageHeader';

/** Render the bits of markdown the changelog actually uses (**bold** + `code`). */
function richText(text: string): JSX.Element {
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).filter(Boolean);
  return (
    <>
      {parts.map((p, i) => {
        if (p.startsWith('**') && p.endsWith('**')) return <strong key={i} className='text-foreground'>{p.slice(2, -2)}</strong>;
        if (p.startsWith('`') && p.endsWith('`')) return <code key={i} className='rounded bg-secondary/60 px-1 text-xs'>{p.slice(1, -1)}</code>;
        return <span key={i}>{p}</span>;
      })}
    </>
  );
}

const STATUS_META: Record<RoadmapStatus, { label: string; icon: typeof Rocket; cls: string; dot: string }> = {
  in_progress: { label: 'In the works', icon: Loader2, cls: 'text-amber-200', dot: 'bg-amber-400' },
  coming: { label: 'Coming', icon: CircleDashed, cls: 'text-muted-foreground', dot: 'bg-muted-foreground' },
  shipped: { label: 'Shipped', icon: CheckCircle2, cls: 'text-emerald-300', dot: 'bg-emerald-400' },
};
const STATUS_ORDER: RoadmapStatus[] = ['in_progress', 'coming', 'shipped'];

export function WhatsnewPage(): JSX.Element {
  const [view, setView] = useState<'roadmap' | 'changelog'>('roadmap');
  const [changelog, setChangelog] = useState<Changelog | null>(null);
  const [roadmap, setRoadmap] = useState<Roadmap | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void getRoadmap().then(setRoadmap).catch((e) => setError((e as Error).message));
    void getChangelog().then(setChangelog).catch(() => undefined);
  }, []);

  return (
    <div className='flex h-full flex-col gap-4 overflow-y-auto'>
      <PageHeader
        title="What's New"
        subtitle='What shipped recently — and the path of what’s coming to Synapse.'
      />

      <div className='inline-flex self-start rounded-md border border-border p-0.5 text-sm'>
        {(['roadmap', 'changelog'] as const).map((v) => (
          <button
            key={v}
            onClick={() => setView(v)}
            className={cn(
              'rounded px-3 py-1 font-medium capitalize transition-colors',
              view === v ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground'
            )}
          >
            {v === 'roadmap' ? 'Roadmap' : "What's changed"}
          </button>
        ))}
      </div>

      {error && <p role='alert' className='text-xs text-destructive'>{error}</p>}

      {view === 'roadmap' ? (
        <RoadmapView roadmap={roadmap} />
      ) : (
        <ChangelogView changelog={changelog} />
      )}
    </div>
  );
}

function RoadmapView({ roadmap }: { roadmap: Roadmap | null }): JSX.Element {
  if (!roadmap) {
    return (
      <Card className='flex items-center gap-2 p-6 text-sm text-muted-foreground'>
        <Loader2 className='h-4 w-4 animate-spin' /> Loading the roadmap…
      </Card>
    );
  }
  return (
    <div className='flex flex-col gap-5'>
      {STATUS_ORDER.map((status) => {
        const items = roadmap.items.filter((i) => i.status === status);
        if (items.length === 0) return null;
        const meta = STATUS_META[status];
        const Icon = meta.icon;
        return (
          <div key={status} className='flex flex-col gap-2'>
            <div className={cn('flex items-center gap-2 text-sm font-semibold', meta.cls)}>
              <Icon className={cn('h-4 w-4', status === 'in_progress' && 'animate-spin')} />
              {meta.label} <span className='text-muted-foreground'>· {items.length}</span>
            </div>
            <div className='ml-1.5 flex flex-col gap-2 border-l border-border pl-4'>
              {items.map((item) => (
                <div key={item.id} className='relative'>
                  <span className={cn('absolute -left-[1.42rem] top-1.5 h-2 w-2 rounded-full', meta.dot)} />
                  <div className='flex flex-wrap items-baseline gap-x-2'>
                    <h3 className='font-medium'>{item.title}</h3>
                    {item.adr && <span className='text-[10px] uppercase tracking-wide text-muted-foreground'>{item.adr}</span>}
                  </div>
                  <p className='text-sm text-muted-foreground'>{item.summary}</p>
                </div>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function ChangelogView({ changelog }: { changelog: Changelog | null }): JSX.Element {
  if (!changelog) {
    return (
      <Card className='flex items-center gap-2 p-6 text-sm text-muted-foreground'>
        <Loader2 className='h-4 w-4 animate-spin' /> Loading the changelog…
      </Card>
    );
  }
  return (
    <div className='flex flex-col gap-3'>
      {changelog.versions.map((v, idx) => (
        <Card key={`${v.version}-${idx}`} className='flex flex-col gap-2 p-4'>
          <div className='flex flex-wrap items-baseline gap-2'>
            <Sparkles className='h-4 w-4 text-primary' />
            <h2 className='text-base font-semibold'>{v.version}</h2>
            {v.date && <span className='text-xs text-muted-foreground'>{v.date}</span>}
          </div>
          {v.summary && <p className='text-sm text-muted-foreground'>{richText(v.summary)}</p>}
          {v.sections.map((s, si) => (
            <div key={si} className='flex flex-col gap-1'>
              {s.title && <h3 className='text-xs font-semibold uppercase tracking-wide text-muted-foreground'>{s.title}</h3>}
              <ul className='flex flex-col gap-1'>
                {s.items.map((item, ii) => (
                  <li key={ii} className='flex gap-2 text-sm text-muted-foreground'>
                    <span className='mt-1.5 h-1 w-1 shrink-0 rounded-full bg-primary/60' />
                    <span>{richText(item)}</span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </Card>
      ))}
    </div>
  );
}
