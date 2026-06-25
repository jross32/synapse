// Workers gallery (ADR-0018 MW3): a worker = a role + a personality. Shows the
// installed personalities (create/remove custom ones) alongside the role roster,
// so the same role can be paired with different personalities in the squad
// builder and the AIs actually collaborate/debate.

import { useEffect, useState } from 'react';
import { Briefcase, Drama, Loader2, Plus, Trash2, X } from 'lucide-react';

import { listAgentRoleTemplates } from '@shared/agent-squads-client';
import {
  createPersonality,
  deletePersonality,
  listPersonalities,
  type Personality,
} from '@shared/personalities-client';
import type { AgentRoleTemplate } from '@shared/generated-types';
import { Card } from './ui/card';
import { cn } from '@shared/utils';

const INPUT =
  'w-full rounded-md border border-border bg-background px-2.5 py-1.5 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary/50 focus:outline-none';

export function WorkerBrowser(): JSX.Element {
  const [personalities, setPersonalities] = useState<Personality[]>([]);
  const [roles, setRoles] = useState<AgentRoleTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  async function load(): Promise<void> {
    setLoading(true);
    try {
      const [p, r] = await Promise.all([listPersonalities(), listAgentRoleTemplates()]);
      setPersonalities(p);
      setRoles(r.filter((role) => role.enabled));
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function remove(id: string): Promise<void> {
    await deletePersonality(id);
    setPersonalities((prev) => prev.filter((p) => p.id !== id));
  }

  if (loading) {
    return (
      <Card className='flex items-center gap-2 p-6 text-sm text-muted-foreground'>
        <Loader2 className='h-4 w-4 animate-spin' /> Loading workers…
      </Card>
    );
  }

  return (
    <div className='flex flex-col gap-6'>
      {error && <p role='alert' className='text-xs text-destructive'>{error}</p>}

      {/* Personalities ------------------------------------------------------ */}
      <section className='flex flex-col gap-3'>
        <div className='flex items-center justify-between'>
          <h2 className='flex items-center gap-2 text-sm font-semibold'>
            <Drama className='h-4 w-4 text-primary' /> Personalities
            <span className='text-muted-foreground'>· {personalities.length}</span>
          </h2>
          <button
            onClick={() => setCreating((v) => !v)}
            className='inline-flex items-center gap-1.5 rounded-md border border-border px-2.5 py-1 text-xs font-medium text-muted-foreground transition-colors hover:bg-accent/60 hover:text-foreground'
          >
            {creating ? <X className='h-3.5 w-3.5' /> : <Plus className='h-3.5 w-3.5' />}
            {creating ? 'Cancel' : 'New personality'}
          </button>
        </div>

        {creating && <CreatePersonalityForm onCreated={(p) => { setPersonalities((prev) => [...prev, p]); setCreating(false); }} />}

        <div className='grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3'>
          {personalities.map((p) => (
            <Card key={p.id} className='group flex flex-col gap-2 p-4'>
              <div className='flex items-start justify-between gap-2'>
                <h3 className='font-medium'>{p.name}</h3>
                {p.builtin ? (
                  <span className='rounded-full bg-secondary/60 px-2 py-0.5 text-[10px] uppercase tracking-wide text-muted-foreground'>Built-in</span>
                ) : (
                  <button
                    onClick={() => void remove(p.id)}
                    title='Remove personality'
                    className='text-muted-foreground opacity-0 transition-opacity hover:text-destructive group-hover:opacity-100'
                  >
                    <Trash2 className='h-4 w-4' />
                  </button>
                )}
              </div>
              {p.blurb && <p className='text-sm text-muted-foreground'>{p.blurb}</p>}
              {p.traits.length > 0 && (
                <div className='mt-auto flex flex-wrap gap-1'>
                  {p.traits.map((t) => (
                    <span key={t} className='rounded-full bg-primary/10 px-2 py-0.5 text-[11px] text-primary'>{t}</span>
                  ))}
                </div>
              )}
            </Card>
          ))}
        </div>
      </section>

      {/* Roles -------------------------------------------------------------- */}
      <section className='flex flex-col gap-3'>
        <h2 className='flex items-center gap-2 text-sm font-semibold'>
          <Briefcase className='h-4 w-4 text-primary' /> Roles
          <span className='text-muted-foreground'>· {roles.length}</span>
        </h2>
        <p className='-mt-1 text-xs text-muted-foreground'>
          Pair any role with a personality in the squad builder — two of the same role with different
          personalities will collaborate and debate.
        </p>
        <div className='grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3'>
          {roles.map((r) => (
            <Card key={r.id} className='flex flex-col gap-2 p-4'>
              <div className='flex items-start justify-between gap-2'>
                <h3 className='font-medium'>{r.name}</h3>
                <span className='rounded-full bg-secondary/60 px-2 py-0.5 text-[10px] uppercase tracking-wide text-muted-foreground'>{r.role_tier}</span>
              </div>
              <p className='text-sm text-muted-foreground'>{r.description}</p>
            </Card>
          ))}
        </div>
      </section>
    </div>
  );
}

function CreatePersonalityForm({ onCreated }: { onCreated: (p: Personality) => void }): JSX.Element {
  const [name, setName] = useState('');
  const [blurb, setBlurb] = useState('');
  const [traits, setTraits] = useState('');
  const [preamble, setPreamble] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function save(): Promise<void> {
    if (!name.trim() || !preamble.trim()) {
      setErr('A name and a personality description are required.');
      return;
    }
    setBusy(true);
    try {
      const created = await createPersonality({
        name: name.trim(),
        blurb: blurb.trim(),
        traits: traits.split(',').map((t) => t.trim()).filter(Boolean),
        prompt_preamble_md: preamble.trim(),
      });
      onCreated(created);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className='flex flex-col gap-2 border-dashed p-4'>
      <input className={INPUT} placeholder='Name (e.g. The Optimist)' value={name} onChange={(e) => setName(e.target.value)} />
      <input className={INPUT} placeholder='One-line blurb (optional)' value={blurb} onChange={(e) => setBlurb(e.target.value)} />
      <input className={INPUT} placeholder='Traits, comma-separated (e.g. bold, fast)' value={traits} onChange={(e) => setTraits(e.target.value)} />
      <textarea
        className={cn(INPUT, 'min-h-[64px] resize-y')}
        placeholder='Personality description — how this worker should think and behave.'
        value={preamble}
        onChange={(e) => setPreamble(e.target.value)}
      />
      {err && <p role='alert' className='text-xs text-destructive'>{err}</p>}
      <div className='flex justify-end'>
        <button
          onClick={() => void save()}
          disabled={busy}
          className='inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-50'
        >
          {busy && <Loader2 className='h-3.5 w-3.5 animate-spin' />} Add personality
        </button>
      </div>
    </Card>
  );
}
