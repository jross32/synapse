import { useEffect, useState } from 'react';

// Milestone A — placeholder shell. Real Nucleus + Synapses layout arrives in Milestone F.
// At this stage the renderer simply renders a holding screen.
export default function App(): JSX.Element {
  const [version, setVersion] = useState<string>('0.1.0-alpha.1');

  useEffect(() => {
    // Preload bridge wired in Milestone C — until then this is a no-op.
    const bridge = (window as unknown as { synapse?: { version?: () => string } }).synapse;
    if (bridge?.version) {
      setVersion(bridge.version());
    }
  }, []);

  return (
    <main className='flex min-h-screen flex-col items-center justify-center gap-4 p-8'>
      <h1 className='text-4xl font-bold tracking-tight'>Synapse</h1>
      <p className='text-sm text-slate-400'>by The WhatIf Company</p>
      <p className='text-xs text-slate-500'>v{version} · Milestone A scaffolding</p>
    </main>
  );
}
