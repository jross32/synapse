import { useState } from 'react';
import { CheckCircle2, ChevronDown, ChevronUp, CircleHelp, ShieldCheck, Wrench } from 'lucide-react';
import { Card } from './ui/card';
import { Button } from './ui/button';

/** An honest setup guide: never infer completion from a click or cached UI state. */
const stages = [
  { title: 'Connect your machine', detail: 'Confirm the Synapse daemon is reachable before configuring tools.' },
  { title: 'Choose a workflow', detail: 'Select a skill or tool for the job. You can skip optional integrations.' },
  { title: 'Verify a real action', detail: 'Run a safe test and inspect its result before trusting automation.' },
] as const;

export function SetupReadinessPanel({ connected }: { connected: boolean }): JSX.Element {
  const [expanded, setExpanded] = useState(false);
  return (
    <Card className='overflow-hidden border-primary/20' data-testid='setup-readiness-panel'>
      <div className='flex flex-wrap items-center justify-between gap-3 p-5'>
        <div className='flex min-w-0 items-center gap-3'>
          <div className='rounded-xl bg-primary/10 p-2 text-primary'><Wrench className='h-5 w-5' aria-hidden='true' /></div>
          <div><h2 className='font-semibold'>Setup &amp; readiness</h2><p className='mt-1 text-sm text-muted-foreground'>A clear path from installation to your first verified result.</p></div>
        </div>
        <Button variant='outline' size='sm' aria-expanded={expanded} aria-controls='setup-readiness-details' onClick={() => setExpanded(value => !value)}>
          {expanded ? 'Hide guide' : 'View guide'}{expanded ? <ChevronUp /> : <ChevronDown />}
        </Button>
      </div>
      {expanded && <div id='setup-readiness-details' className='space-y-3 border-t border-border/70 p-5'>
        {stages.map((stage, index) => {
          const verified = index === 0 && connected;
          return <div key={stage.title} className='flex items-start gap-3 rounded-xl border border-border/70 bg-secondary/10 p-3'>
            <span className='mt-0.5 shrink-0 text-muted-foreground'>{verified ? <CheckCircle2 className='h-5 w-5 text-emerald-500' aria-label='Connected' /> : index === 0 ? <CircleHelp className='h-5 w-5' aria-label='Not connected' /> : <ShieldCheck className='h-5 w-5' aria-label='Requires verification' />}</span>
            <div className='min-w-0'><p className='text-sm font-medium'>{stage.title}</p><p className='mt-1 text-xs leading-5 text-muted-foreground'>{stage.detail}</p><p className='mt-1 text-xs font-medium'>{verified ? 'Connection confirmed' : index === 0 ? 'Waiting for daemon connection' : 'Not yet verified'}</p></div>
          </div>;
        })}
        <p className='text-xs text-muted-foreground'>A setup click is not proof of success. Synapse marks a step complete only when the actual outcome can be verified.</p>
      </div>}
    </Card>
  );
}