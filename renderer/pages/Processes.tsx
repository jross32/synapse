// Processes page (Milestone F) -- full-page live process monitor.

import { useState } from 'react';
import { Loader2, Square } from 'lucide-react';

import type { Project } from '@shared/generated-types';
import { stopProject } from '@shared/projects-client';
import { useDaemon } from '@shared/daemon-context';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { Button } from '../components/ui/button';
import { ProcessMonitor } from '../components/ProcessMonitor';
import { PageHeader } from '../components/PageHeader';

// 'launched' = up + responding. We stop those; 'launching' / 'stopping'
// are mid-transition and the daemon refuses to stop them anyway, so
// don't include them in the "Stop all" batch.
const STOPPABLE = new Set(['launched']);
const RUNNING = new Set(['launching', 'launched', 'stopping']);

export interface ProcessesPageProps {
  headerless?: boolean;
}

export function ProcessesPage({ headerless = false }: ProcessesPageProps): JSX.Element {
  const { projects, resourcesById, upsertProjectLocal } = useDaemon();
  const [actionError, setActionError] = useState<string | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [stoppingAll, setStoppingAll] = useState(false);

  const runningCount = projects.filter((p) => RUNNING.has(p.status)).length;
  const stoppable = projects.filter((p) => STOPPABLE.has(p.status));

  async function handleStopAll(): Promise<void> {
    setStoppingAll(true);
    setActionError(null);
    setConfirmOpen(false);
    const results = await Promise.allSettled(
      stoppable.map((p) => stopProject(p.id))
    );
    const failures: string[] = [];
    results.forEach((r, i) => {
      if (r.status === 'fulfilled') {
        upsertProjectLocal(r.value);
      } else {
        failures.push(stoppable[i].name);
      }
    });
    if (failures.length === results.length) {
      setActionError(`Couldn't stop any of the ${results.length} projects -- check the daemon log.`);
    } else if (failures.length > 0) {
      setActionError(
        `Stopped ${results.length - failures.length} of ${results.length}; resisted: ${failures.join(', ')}.`
      );
    }
    setStoppingAll(false);
  }

  return (
    <div className='flex flex-col gap-6'>
      {!headerless && (
        <PageHeader
          title='Processes'
          subtitle={`Everything Synapse is running right now. CPU + memory update live (~2s). ${runningCount} active.`}
          action={
            stoppable.length > 0 && (
              <Button
                variant='outline'
                disabled={stoppingAll}
                onClick={() => setConfirmOpen(true)}
                aria-label={`Stop all ${stoppable.length} running projects`}
              >
                {stoppingAll ? (
                  <Loader2 className='h-4 w-4 animate-spin' aria-hidden='true' />
                ) : (
                  <Square className='h-4 w-4' aria-hidden='true' />
                )}
                Stop all ({stoppable.length})
              </Button>
            )
          }
        />
      )}
      {headerless && stoppable.length > 0 && (
        <div className='flex justify-end'>
          <Button
            variant='outline'
            disabled={stoppingAll}
            onClick={() => setConfirmOpen(true)}
            aria-label={`Stop all ${stoppable.length} running projects`}
          >
            {stoppingAll ? (
              <Loader2 className='h-4 w-4 animate-spin' aria-hidden='true' />
            ) : (
              <Square className='h-4 w-4' aria-hidden='true' />
            )}
            Stop all ({stoppable.length})
          </Button>
        </div>
      )}
      {actionError && (
        <p role='alert' className='text-sm text-destructive'>
          {actionError}
        </p>
      )}
      <ProcessMonitor
        projects={projects}
        resourcesById={resourcesById}
        onActionError={(_p, err) => setActionError(err.message)}
      />

      <ConfirmDialog
        open={confirmOpen}
        title={`Stop ${stoppable.length} running project${stoppable.length === 1 ? '' : 's'}?`}
        body={
          <>
            <p>
              Synapse will send a stop to each of these projects in parallel.
              Their child processes get a clean shutdown signal and a few
              seconds to exit.
            </p>
            <ul className='mt-2 max-h-[180px] overflow-y-auto rounded-md border border-border bg-secondary/40 p-2 text-xs'>
              {stoppable.map((p: Project) => (
                <li key={p.id} className='font-mono text-foreground'>
                  {p.name}
                </li>
              ))}
            </ul>
          </>
        }
        confirmLabel={`Stop all (${stoppable.length})`}
        danger
        onConfirm={() => void handleStopAll()}
        onCancel={() => setConfirmOpen(false)}
      />
    </div>
  );
}
