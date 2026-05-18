// Tools page (Milestone F · v0.1.9) -- the Synapse plugin surface.
//
// Renders one manifest-driven ToolCard per tool the daemon loaded from
// `tools/<id>/manifest.json`. No tool-specific code here: a new tool is a
// folder + a manifest, never a renderer change.

import { useEffect, useRef, useState } from 'react';
import { Loader2, Wrench } from 'lucide-react';

import type { ToolEntry } from '@shared/generated-types';
import { listTools } from '@shared/tools-client';
import { useDaemon } from '@shared/daemon-context';
import { Card } from '../components/ui/card';
import { PageHeader } from '../components/PageHeader';
import { ToolCard } from '../components/ToolCard';

export function ToolsPage(): JSX.Element {
  const { recentEvents } = useDaemon();
  const [tools, setTools] = useState<ToolEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Highest WS event id already accounted for -- so we only refetch on
  // genuinely new tool events, not the backlog present at mount.
  const seenEventId = useRef(0);

  function refresh(): void {
    listTools()
      .then(setTools)
      .catch((err: Error) => setError(err.message || 'Failed to load tools'));
  }

  useEffect(() => {
    seenEventId.current = recentEvents.reduce((m, e) => Math.max(m, e.id), 0);
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // A tunnel can drop on its own; the daemon broadcasts v1.tool.* events.
  // Refetch when one lands so the card never shows stale state.
  useEffect(() => {
    const fresh = recentEvents.filter(
      (e) => e.id > seenEventId.current && e.name.startsWith('v1.tool.')
    );
    if (fresh.length === 0) return;
    seenEventId.current = recentEvents.reduce((m, e) => Math.max(m, e.id), seenEventId.current);
    refresh();
  }, [recentEvents]);

  function handleChanged(updated: ToolEntry): void {
    setTools((prev) =>
      prev ? prev.map((t) => (t.manifest.id === updated.manifest.id ? updated : t)) : prev
    );
  }

  return (
    <div className='flex flex-col gap-6'>
      <PageHeader
        title='Tools'
        subtitle='Synapses — modular tools backed by manifest plugins. Drop a folder in, get a card.'
      />

      {error && (
        <p role='alert' className='text-sm text-destructive'>
          {error}
        </p>
      )}

      {tools === null && !error && (
        <Card className='flex items-center justify-center gap-2 p-12 text-sm text-muted-foreground'>
          <Loader2 className='h-4 w-4 animate-spin' /> Loading tools…
        </Card>
      )}

      {tools !== null && tools.length === 0 && (
        <Card className='flex flex-col items-center gap-3 border-dashed p-12 text-center'>
          <div className='flex h-12 w-12 items-center justify-center rounded-lg bg-secondary'>
            <Wrench className='h-6 w-6 text-primary' />
          </div>
          <h3 className='text-lg font-semibold'>No tools loaded</h3>
          <p className='max-w-md text-sm text-muted-foreground'>
            Drop a tool folder with a <code className='font-mono'>manifest.json</code> into{' '}
            <code className='font-mono'>tools/</code> and restart the daemon.
          </p>
        </Card>
      )}

      {tools !== null && tools.length > 0 && (
        <div className='grid grid-cols-[repeat(auto-fill,minmax(min(100%,340px),1fr))] gap-6'>
          {tools.map((entry) => (
            <ToolCard key={entry.manifest.id} entry={entry} onChanged={handleChanged} />
          ))}
        </div>
      )}
    </div>
  );
}
