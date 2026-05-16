// Tools page (Milestone F) -- the Synapse plugin surface.
//
// v0.1.8 ships the page shell + an empty state. v0.1.9 wires the real
// plugin system: manifest-driven tool cards (Cloudtap, Open-in-VSCode,
// Terminal runner) plus the agent / workflow slots.

import { Wrench } from 'lucide-react';

import { Card } from '../components/ui/card';
import { PageHeader } from '../components/PageHeader';

export function ToolsPage(): JSX.Element {
  return (
    <div className='flex flex-col gap-6'>
      <PageHeader
        title='Tools'
        subtitle='Synapses — modular tools, AI agents, and workflows. Drop a manifest in, get a card.'
      />
      <Card className='flex flex-col items-center gap-3 border-dashed p-12 text-center'>
        <div className='flex h-12 w-12 items-center justify-center rounded-lg bg-secondary'>
          <Wrench className='h-6 w-6 text-primary' />
        </div>
        <h3 className='text-lg font-semibold'>Plugin system arrives in v0.1.9</h3>
        <p className='max-w-md text-sm text-muted-foreground'>
          The first built-in tools — Cloudtap (port → public tunnel), Open-in-VSCode, and a
          Terminal runner — land next, each as a manifest-driven card.
        </p>
      </Card>
    </div>
  );
}
