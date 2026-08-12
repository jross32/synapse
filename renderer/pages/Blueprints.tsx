/**
 * The blueprint gallery: what can be built, what it promises, and how good it was last time.
 *
 * Layout follows the one-window rule. The page itself never scrolls — it is a fixed-height
 * flex column, and only the list pane and the detail pane scroll internally. Long lists are
 * paged with "show more" rather than growing without end, so the window never becomes a
 * document you fall down.
 *
 * `guarantees` is the field that earns trust here. Every entry maps to a check that actually
 * runs during a build, so it is a promise the system enforces rather than a description of
 * intent — which is exactly the distinction that made the earlier build-off scores misleading.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Blocks, CheckCircle2, ChevronDown, Cpu, Layers, Loader2, Play, Puzzle, ShieldCheck, X,
} from 'lucide-react';

import { PageHeader } from '../components/PageHeader';
import { Button } from '../components/ui/button';
import {
  buildBlueprint, getCompatibility, listBlueprints,
  type Blueprint, type BuildResult, type Compatibility,
} from '../lib/blueprints-client';
import { cn } from '../lib/utils';

const PAGE_SIZE = 9;

const KIND_LABEL: Record<string, string> = {
  'web-app': 'Web app',
  backend: 'Backend',
  'ui-component': 'UI component',
  data: 'Data',
  animation: 'Animation',
  library: 'Library',
  integration: 'Integration',
  infra: 'Infrastructure',
  agent: 'Agent',
  other: 'Other',
};

function GradePill({ blueprint }: { blueprint: Blueprint }): JSX.Element {
  // shrink-0 and nowrap: without them the pill wraps to two lines and pushes out past the
  // card's right edge, because the title beside it is the flexible element, not this.
  const base =
    'shrink-0 whitespace-nowrap rounded-full border border-border px-2 py-0.5 text-[11px]';
  if (!blueprint.score) {
    return <span className={cn(base, 'text-muted-foreground')}>not built</span>;
  }
  const pct = Math.round(blueprint.score.percent);
  const tone =
    pct >= 90 ? 'text-[var(--status-ok,#6fcf87)]' : pct >= 70 ? 'text-foreground' : 'text-[var(--status-warn,#e0a76b)]';
  return <span className={cn(base, 'font-medium', tone)}>{pct}%</span>;
}

function BlueprintCard({
  blueprint, active, onSelect,
}: { blueprint: Blueprint; active: boolean; onSelect: () => void }): JSX.Element {
  return (
    <button
      type='button'
      onClick={onSelect}
      className={cn(
        // overflow-hidden on the card itself: a <button> does not shrink to its container
        // the way a div does, so without this the title's intrinsic width sets the card's
        // scrollWidth and it bleeds past the grid track.
        'flex w-full min-w-0 flex-col gap-2 overflow-hidden rounded-lg border p-3 text-left transition-colors',
        active ? 'border-primary bg-accent/40' : 'border-border bg-card hover:bg-accent/20',
      )}
    >
      <div className='flex w-full min-w-0 items-start justify-between gap-2'>
        <span className='min-w-0 flex-1 truncate text-sm font-medium'>{blueprint.name}</span>
        <GradePill blueprint={blueprint} />
      </div>
      <p className='line-clamp-2 text-xs text-muted-foreground'>{blueprint.summary}</p>
      <div className='flex flex-wrap items-center gap-1.5'>
        <span className='rounded bg-muted px-1.5 py-0.5 text-[11px] text-muted-foreground'>
          {KIND_LABEL[blueprint.kind] ?? blueprint.kind}
        </span>
        {blueprint.est_minutes > 0 && (
          <span className='text-[11px] text-muted-foreground'>~{blueprint.est_minutes} min</span>
        )}
        {blueprint.draft && (
          <span className='rounded bg-[var(--status-warn-bg,rgba(224,167,107,.15))] px-1.5 py-0.5 text-[11px]'>
            draft
          </span>
        )}
      </div>
    </button>
  );
}

function Detail({
  blueprint, onClose,
}: { blueprint: Blueprint; onClose: () => void }): JSX.Element {
  const [compat, setCompat] = useState<Compatibility | null>(null);
  const [building, setBuilding] = useState(false);
  const [result, setResult] = useState<BuildResult | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    setCompat(null);
    setResult(null);
    setError('');
    getCompatibility(blueprint.id).then(setCompat).catch(() => setCompat(null));
  }, [blueprint.id]);

  const start = useCallback(async () => {
    setBuilding(true);
    setError('');
    try {
      setResult(await buildBlueprint(blueprint.id, {}));
    } catch (err) {
      setError((err as Error).message || 'The build could not start.');
    } finally {
      setBuilding(false);
    }
  }, [blueprint.id]);

  return (
    // Its own scroll container: the page stays fixed, this pane moves.
    <aside className='flex min-h-0 w-full flex-col rounded-lg border border-border bg-card lg:w-[420px]'>
      <div className='flex shrink-0 items-start justify-between gap-2 border-b border-border p-3'>
        <div className='min-w-0'>
          <h2 className='truncate text-sm font-semibold'>{blueprint.name}</h2>
          <p className='text-xs text-muted-foreground'>
            {KIND_LABEL[blueprint.kind] ?? blueprint.kind}
            {blueprint.stack.length > 0 && ` · ${blueprint.stack.join(', ')}`}
          </p>
        </div>
        <button type='button' onClick={onClose} aria-label='Close details'
                className='rounded p-1 hover:bg-accent'>
          <X className='h-4 w-4' />
        </button>
      </div>

      <div className='min-h-0 flex-1 space-y-4 overflow-y-auto scrollbar-thin p-3 text-sm'>
        <p className='text-muted-foreground'>{blueprint.summary}</p>

        {blueprint.what_you_get.length > 0 && (
          <section>
            <h3 className='mb-1.5 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground'>
              <Blocks className='h-3.5 w-3.5' /> What you get
            </h3>
            <ul className='space-y-1'>
              {blueprint.what_you_get.map((item) => (
                <li key={item} className='flex gap-2 text-xs'>
                  <CheckCircle2 className='mt-0.5 h-3.5 w-3.5 shrink-0 text-[var(--status-ok,#6fcf87)]' />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </section>
        )}

        {blueprint.guarantees.length > 0 && (
          <section className='rounded-md border border-border bg-muted/30 p-2.5'>
            <h3 className='mb-1.5 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide'>
              <ShieldCheck className='h-3.5 w-3.5' /> Enforced guarantees
            </h3>
            <ul className='space-y-1'>
              {blueprint.guarantees.map((g) => (
                <li key={g} className='text-xs text-muted-foreground'>· {g}</li>
              ))}
            </ul>
            <p className='mt-2 text-[11px] text-muted-foreground'>
              Each of these maps to a check that runs during the build. A piece that cannot
              satisfy one is escalated rather than shipped.
            </p>
          </section>
        )}

        <section>
          <h3 className='mb-1.5 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground'>
            <Layers className='h-3.5 w-3.5' /> Pieces ({blueprint.pieces.length})
          </h3>
          <div className='space-y-1'>
            {blueprint.pieces.map((p) => (
              <div key={p.name} className='flex items-center justify-between gap-2 rounded border border-border px-2 py-1.5'>
                <span className='truncate font-mono text-xs'>{p.module || p.name}</span>
                <span className='shrink-0 text-[11px] text-muted-foreground'>
                  {p.checks.join(' · ')}
                </span>
              </div>
            ))}
          </div>
        </section>

        {(blueprint.provides.length > 0 || blueprint.requires.length > 0) && (
          <section>
            <h3 className='mb-1.5 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground'>
              <Puzzle className='h-3.5 w-3.5' /> Composition
            </h3>
            {blueprint.provides.length > 0 && (
              <p className='text-xs'>
                <span className='text-muted-foreground'>Provides: </span>
                {blueprint.provides.join(', ')}
              </p>
            )}
            <p className='text-xs'>
              <span className='text-muted-foreground'>Requires: </span>
              {blueprint.requires.length ? blueprint.requires.join(', ') : 'nothing — composes with anything'}
            </p>
            {compat && compat.satisfies_my_needs.length > 0 && (
              <p className='mt-1 text-xs text-muted-foreground'>
                Pairs with: {compat.satisfies_my_needs.join(', ')}
              </p>
            )}
          </section>
        )}

        {blueprint.score && (
          <section className='rounded-md border border-border p-2.5'>
            <h3 className='mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground'>
              Last build
            </h3>
            <p className='text-xs'>
              {Math.round(blueprint.score.percent)}% · {Math.round(blueprint.score.seconds)}s ·{' '}
              {blueprint.score.local_tokens} local tokens
              {blueprint.score.escalations.length > 0 &&
                ` · escalated: ${blueprint.score.escalations.join(', ')}`}
            </p>
          </section>
        )}

        {result && (
          <section className='rounded-md border border-border p-2.5'>
            <h3 className='mb-1.5 text-xs font-semibold uppercase tracking-wide'>Build result</h3>
            <ul className='space-y-1'>
              {result.pieces.map((p) => (
                <li key={p.name} className='flex items-center justify-between gap-2 text-xs'>
                  <span className='font-mono'>{p.name}</span>
                  <span className={p.passed ? 'text-[var(--status-ok,#6fcf87)]' : 'text-[var(--status-warn,#e0a76b)]'}>
                    {p.passed ? 'built' : 'escalated'} · {p.repairs} repairs · {Math.round(p.seconds)}s
                  </span>
                </li>
              ))}
            </ul>
            {result.notes.map((n) => (
              <p key={n} className='mt-2 text-[11px] text-muted-foreground'>{n}</p>
            ))}
          </section>
        )}

        {error && (
          <p className='rounded-md border border-[rgba(224,115,107,.4)] bg-[rgba(224,115,107,.12)] p-2 text-xs'>
            {error}
          </p>
        )}
      </div>

      <div className='shrink-0 border-t border-border p-3'>
        <Button onClick={() => void start()} disabled={building} className='w-full gap-2'>
          {building ? <Loader2 className='h-4 w-4 animate-spin' /> : <Play className='h-4 w-4' />}
          {building ? 'Building locally…' : 'Build with local models'}
        </Button>
        <p className='mt-1.5 text-center text-[11px] text-muted-foreground'>
          Runs on this machine. No API tokens.
        </p>
      </div>
    </aside>
  );
}

export function BlueprintsPage({ headerless = false }: { headerless?: boolean }): JSX.Element {
  const [blueprints, setBlueprints] = useState<Blueprint[]>([]);
  const [loading, setLoading] = useState(true);
  const [kind, setKind] = useState('');
  const [visible, setVisible] = useState(PAGE_SIZE);
  const [selectedId, setSelectedId] = useState('');

  useEffect(() => {
    listBlueprints()
      .then(setBlueprints)
      .catch(() => setBlueprints([]))
      .finally(() => setLoading(false));
  }, []);

  const kinds = useMemo(
    () => Array.from(new Set(blueprints.map((b) => b.kind))).sort(),
    [blueprints],
  );
  const filtered = useMemo(
    () => (kind ? blueprints.filter((b) => b.kind === kind) : blueprints),
    [blueprints, kind],
  );
  const selected = blueprints.find((b) => b.id === selectedId) ?? null;

  return (
    <div className='flex h-full min-h-0 flex-col'>
      {!headerless && (
        <PageHeader
          title='Blueprints'
          subtitle='Verified recipes. Each one states what it guarantees and proves it during the build.'
        />
      )}

      <div className='flex min-h-0 flex-1 flex-col gap-3 lg:flex-row'>
        <div className='flex min-h-0 flex-1 flex-col'>
          {kinds.length > 1 && (
            <div className='mb-2 flex shrink-0 flex-wrap gap-1.5'>
              <button
                type='button'
                onClick={() => { setKind(''); setVisible(PAGE_SIZE); }}
                className={cn('rounded-full border px-2.5 py-1 text-xs',
                  kind === '' ? 'border-primary bg-accent' : 'border-border hover:bg-accent/40')}
              >
                All ({blueprints.length})
              </button>
              {kinds.map((k) => (
                <button
                  key={k}
                  type='button'
                  onClick={() => { setKind(k); setVisible(PAGE_SIZE); }}
                  className={cn('rounded-full border px-2.5 py-1 text-xs',
                    kind === k ? 'border-primary bg-accent' : 'border-border hover:bg-accent/40')}
                >
                  {KIND_LABEL[k] ?? k}
                </button>
              ))}
            </div>
          )}

          {/* The only scrolling region on this side. */}
          <div className='min-h-0 flex-1 overflow-y-auto scrollbar-thin pr-1'>
            {loading ? (
              <p className='p-8 text-center text-sm text-muted-foreground'>Loading blueprints…</p>
            ) : filtered.length === 0 ? (
              <div className='rounded-lg border border-dashed border-border p-8 text-center'>
                <Cpu className='mx-auto mb-2 h-6 w-6 text-muted-foreground' />
                <p className='text-sm font-medium'>No blueprints yet</p>
                <p className='mt-1 text-xs text-muted-foreground'>
                  Blueprints are data. Register one with POST /api/v1/blueprints, or distil a
                  draft from an app you have already built.
                </p>
              </div>
            ) : (
              <>
                <div className='grid min-w-0 gap-2 sm:grid-cols-2 xl:grid-cols-3'>
                  {filtered.slice(0, visible).map((b) => (
                    <BlueprintCard
                      key={b.id}
                      blueprint={b}
                      active={b.id === selectedId}
                      onSelect={() => setSelectedId(b.id)}
                    />
                  ))}
                </div>
                {/* Show more, never endless scroll. */}
                {filtered.length > visible && (
                  <div className='mt-3 flex justify-center'>
                    <Button
                      variant='secondary'
                      size='sm'
                      className='gap-1.5'
                      onClick={() => setVisible((v) => v + PAGE_SIZE)}
                    >
                      <ChevronDown className='h-4 w-4' />
                      Show {Math.min(PAGE_SIZE, filtered.length - visible)} more
                      <span className='text-muted-foreground'>
                        ({visible} of {filtered.length})
                      </span>
                    </Button>
                  </div>
                )}
              </>
            )}
          </div>
        </div>

        {selected && <Detail blueprint={selected} onClose={() => setSelectedId('')} />}
      </div>
    </div>
  );
}

export default BlueprintsPage;
