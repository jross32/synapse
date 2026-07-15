// Featured slideshow (Milestone F · v0.1.10) -- the Home hero.
//
// A Microsoft-Store-style rotating banner over the user's featured projects
// (pinned first, then most-recently-active). Auto-advances, pauses on hover,
// and exposes prev/next + dot navigation. Launch / View actions act on the
// project the current slide shows.

import { useEffect, useState } from 'react';
import { ArrowRight, ChevronLeft, ChevronRight, Pin, Rocket } from 'lucide-react';

import type { Project } from '@shared/generated-types';
import { cn } from '@shared/utils';
import { Button } from './ui/button';
import { Card } from './ui/card';
import { StatusBadge } from './StatusBadge';

const AUTO_ADVANCE_MS = 6500;

export interface FeaturedSlideshowProps {
  projects: Project[];
  onLaunch: (project: Project) => void;
  onView: (project: Project) => void;
  busyId?: string | null;
}

export function FeaturedSlideshow({
  projects,
  onLaunch,
  onView,
  busyId,
}: FeaturedSlideshowProps): JSX.Element | null {
  const [index, setIndex] = useState(0);
  const [paused, setPaused] = useState(false);

  const count = projects.length;
  const safeIndex = count > 0 ? index % count : 0;

  // Clamp the index if the featured list shrank under us.
  useEffect(() => {
    if (index >= count && count > 0) setIndex(0);
  }, [count, index]);

  // Auto-advance unless paused, there's nothing to rotate, or the user asked for
  // reduced motion (respect prefers-reduced-motion -- no auto-sliding banner).
  useEffect(() => {
    if (paused || count < 2) return;
    if (
      typeof window !== 'undefined' &&
      window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    ) {
      return;
    }
    const timer = setTimeout(() => setIndex((i) => (i + 1) % count), AUTO_ADVANCE_MS);
    return () => clearTimeout(timer);
  }, [safeIndex, paused, count]);

  if (count === 0) return null;

  const project = projects[safeIndex];
  const isRunning =
    project.status === 'launched' ||
    project.status === 'launching' ||
    project.status === 'stopping';
  const busy = busyId === project.id;

  return (
    <Card
      className='relative h-[228px] overflow-hidden border-border p-0'
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      onFocusCapture={() => setPaused(true)}
      onBlurCapture={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget as Node)) setPaused(false);
      }}
    >
      <div className='absolute inset-0 bg-gradient-to-br from-primary/20 via-secondary to-secondary' />
      {/* Decorative watermark */}
      <Rocket className='absolute -right-8 -top-8 h-44 w-44 text-primary/10' />

      <div className='relative flex h-full flex-col justify-between px-14 py-6'>
        <div className='flex min-w-0 flex-col gap-2'>
          <span className='flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-muted-foreground'>
            {project.pinned ? (
              <>
                <Pin className='h-3.5 w-3.5 fill-current text-primary' /> Pinned
              </>
            ) : (
              'Featured app'
            )}
          </span>
          <div className='flex min-w-0 items-center gap-3'>
            <h2 className='truncate text-2xl font-semibold tracking-tight'>{project.name}</h2>
            <StatusBadge status={project.status} className='shrink-0' />
          </div>
          <p className='line-clamp-2 max-w-2xl text-sm text-muted-foreground'>
            {project.description?.trim() || project.path}
          </p>
          {(project.group || project.tags.length > 0) && (
            <div className='flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground'>
              {project.group && (
                <span className='rounded bg-background/60 px-1.5 py-0.5'>{project.group}</span>
              )}
              {project.tags.slice(0, 4).map((t) => (
                <span key={t} className='rounded bg-background/60 px-1.5 py-0.5'>
                  #{t}
                </span>
              ))}
            </div>
          )}
        </div>

        <div className='flex items-center justify-between gap-3'>
          <div className='flex flex-wrap gap-2'>
            {!isRunning && (
              <Button size='sm' disabled={busy} onClick={() => onLaunch(project)}>
                <Rocket className='h-4 w-4' /> {busy ? 'Launching…' : 'Launch'}
              </Button>
            )}
            <Button size='sm' variant='outline' onClick={() => onView(project)}>
              View in Apps <ArrowRight className='h-4 w-4' />
            </Button>
          </div>

          {count > 1 && (
            <div className='flex items-center gap-1'>
              {projects.map((p, i) => (
                <button
                  key={p.id}
                  type='button'
                  aria-label={`Show ${p.name}`}
                  aria-current={i === safeIndex}
                  onClick={() => setIndex(i)}
                  className={cn(
                    'h-1.5 rounded-full transition-all',
                    i === safeIndex ? 'w-5 bg-primary' : 'w-1.5 bg-muted-foreground/40'
                  )}
                />
              ))}
            </div>
          )}
        </div>
      </div>

      {count > 1 && (
        <>
          <SlideArrow side='left' onClick={() => setIndex((i) => (i - 1 + count) % count)} />
          <SlideArrow side='right' onClick={() => setIndex((i) => (i + 1) % count)} />
        </>
      )}
    </Card>
  );
}

function SlideArrow({
  side,
  onClick,
}: {
  side: 'left' | 'right';
  onClick: () => void;
}): JSX.Element {
  const Icon = side === 'left' ? ChevronLeft : ChevronRight;
  return (
    <button
      type='button'
      aria-label={side === 'left' ? 'Previous' : 'Next'}
      onClick={onClick}
      className={cn(
        'absolute top-1/2 -translate-y-1/2 rounded-full border border-border bg-background/70 p-1.5',
        'text-muted-foreground transition-colors hover:bg-background hover:text-foreground',
        side === 'left' ? 'left-3' : 'right-3'
      )}
    >
      <Icon className='h-4 w-4' />
    </button>
  );
}
