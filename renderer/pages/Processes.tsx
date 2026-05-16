// Processes page (Milestone F) -- full-page live process monitor.

import { useState } from 'react';

import { useDaemon } from '@shared/daemon-context';
import { ProcessMonitor } from '../components/ProcessMonitor';
import { PageHeader } from '../components/PageHeader';

const RUNNING = new Set(['launching', 'launched', 'stopping']);

export function ProcessesPage(): JSX.Element {
  const { projects, resourcesById } = useDaemon();
  const [actionError, setActionError] = useState<string | null>(null);

  const runningCount = projects.filter((p) => RUNNING.has(p.status)).length;

  return (
    <div className='flex flex-col gap-6'>
      <PageHeader
        title='Processes'
        subtitle={`Everything Synapse is running right now. CPU + memory update live (~2s). ${runningCount} active.`}
      />
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
    </div>
  );
}
