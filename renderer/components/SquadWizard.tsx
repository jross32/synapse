// Guided "Build a team" wizard for Agent Squads.
//
// Replaces the "four raw forms at once" experience with a short, friendly
// flow: goal & project -> pick a preset team -> tweak the roster -> review &
// create. It composes the existing agent-squads client calls (createAgentSquad
// + createAgentWorkItem); the raw forms stay available behind "Advanced" in
// AgentSquadsView for power users.

import { useEffect, useMemo, useState } from 'react';
import {
  Check,
  ChevronLeft,
  ChevronRight,
  Crown,
  Loader2,
  Plus,
  Shield,
  Sparkles,
  Users,
  Wrench,
  X,
} from 'lucide-react';

import type { AgentRoleTemplate, AgentRoleTier, Project } from '@shared/generated-types';
import { cn } from '@shared/utils';
import { createAgentSquad, createAgentWorkItem } from '../lib/agent-squads-client';
import { listPersonalities, type Personality } from '@shared/personalities-client';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Modal } from './ui/modal';

interface SquadWizardProps {
  open: boolean;
  onClose: () => void;
  projects: Project[];
  roles: AgentRoleTemplate[];
  onCreated: (squadId: string) => void;
}

interface Preset {
  id: string;
  name: string;
  blurb: string;
  roleIds: string[];
}

// Presets reference the seeded role ids. If a role is missing (custom install),
// it is silently skipped when building the roster, so a preset can never crash.
const PRESETS: Preset[] = [
  {
    id: 'ship-feature',
    name: 'Ship a feature',
    blurb: 'A boss plans it, an implementer builds it, a reviewer checks it.',
    roleIds: ['boss', 'implementer', 'reviewer'],
  },
  {
    id: 'research-plan',
    name: 'Research & plan',
    blurb: 'A planner with two researchers to map the work before any code.',
    roleIds: ['planner', 'researcher', 'researcher'],
  },
  {
    id: 'bug-hunt',
    name: 'Bug hunt',
    blurb: 'A boss, a reviewer, and a tester to find and pin down a bug.',
    roleIds: ['boss', 'reviewer', 'tester'],
  },
  {
    id: 'full-build',
    name: 'Full build',
    blurb: 'A boss + supervisor coordinating implementer, reviewer, tester, docs.',
    roleIds: ['boss', 'supervisor', 'implementer', 'reviewer', 'tester', 'docs-writer'],
  },
  {
    id: 'solo-lead',
    name: 'Solo lead',
    blurb: 'Just a boss. Start small; delegate to helpers whenever you want.',
    roleIds: ['boss'],
  },
  {
    id: 'custom',
    name: 'Custom',
    blurb: 'Start empty and pick exactly the roles you want.',
    roleIds: [],
  },
];

const TIER_ORDER: AgentRoleTier[] = ['boss', 'supervisor', 'worker'];
const TIER_LABEL: Record<AgentRoleTier, string> = {
  boss: 'Bosses',
  supervisor: 'Supervisors',
  worker: 'Workers',
};
const TIER_ICON: Record<AgentRoleTier, typeof Crown> = {
  boss: Crown,
  supervisor: Shield,
  worker: Wrench,
};

const STEPS = ['Goal', 'Team', 'Roster', 'Review'] as const;

export function SquadWizard({
  open,
  onClose,
  projects,
  roles,
  onCreated,
}: SquadWizardProps): JSX.Element | null {
  const [step, setStep] = useState(0);
  const [projectId, setProjectId] = useState('');
  const [goal, setGoal] = useState('');
  const [teamName, setTeamName] = useState('');
  const [roster, setRoster] = useState<string[]>([]);
  // Personality per roster slot, aligned to `roster` by index (null = default).
  const [personalityIds, setPersonalityIds] = useState<(string | null)[]>([]);
  const [personalities, setPersonalities] = useState<Personality[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    void listPersonalities()
      .then(setPersonalities)
      .catch(() => setPersonalities([]));
  }, [open]);

  const roleById = useMemo(() => {
    const map = new Map<string, AgentRoleTemplate>();
    for (const role of roles) map.set(role.id, role);
    return map;
  }, [roles]);

  const rolesByTier = useMemo(() => {
    const groups: Record<AgentRoleTier, AgentRoleTemplate[]> = {
      boss: [],
      supervisor: [],
      worker: [],
    };
    for (const role of roles) {
      if (!role.enabled) continue;
      (groups[role.role_tier] ?? groups.worker).push(role);
    }
    return groups;
  }, [roles]);

  if (!open) return null;

  const effectiveProjectId = projectId || projects[0]?.id || '';
  const canNext =
    (step === 0 && goal.trim().length > 0 && effectiveProjectId) ||
    (step === 1) ||
    (step === 2 && roster.length > 0) ||
    step === 3;

  function applyPreset(preset: Preset): void {
    const valid = preset.roleIds.filter((id) => roleById.has(id));
    setRoster(valid);
    setPersonalityIds(valid.map(() => null));
    if (!teamName.trim()) setTeamName(preset.id === 'custom' ? '' : preset.name);
    setStep(2);
  }

  function addRole(id: string): void {
    setRoster((prev) => [...prev, id]);
    setPersonalityIds((prev) => [...prev, null]);
  }
  function removeRoleAt(index: number): void {
    setRoster((prev) => prev.filter((_, i) => i !== index));
    setPersonalityIds((prev) => prev.filter((_, i) => i !== index));
  }
  function setPersonalityAt(index: number, value: string | null): void {
    setPersonalityIds((prev) => prev.map((p, i) => (i === index ? value : p)));
  }
  function clearRoster(): void {
    setRoster([]);
    setPersonalityIds([]);
  }

  async function create(): Promise<void> {
    setBusy(true);
    setError(null);
    try {
      const leadId =
        roster.find((id) => roleById.get(id)?.role_tier === 'boss') ??
        roster.find((id) => roleById.get(id)?.default_visibility === 'lead') ??
        roster[0] ??
        null;
      const name = teamName.trim() || goal.trim().slice(0, 48) || 'New team';
      const squad = await createAgentSquad({
        project_id: effectiveProjectId,
        name,
        goal_md: goal.trim(),
        lead_role_id: leadId,
      });
      // Seed one queued work item per roster role so the whole team is visible
      // immediately. Nothing launches until the user clicks Launch.
      for (let i = 0; i < roster.length; i += 1) {
        const roleId = roster[i];
        const role = roleById.get(roleId);
        await createAgentWorkItem(squad.id, {
          title: `${role?.name ?? roleId}: ${name}`,
          instructions_md: goal.trim(),
          assigned_role_id: roleId,
          personality_id: personalityIds[i] ?? null,
        });
      }
      onCreated(squad.id);
      reset();
    } catch (err) {
      setError((err as Error).message || 'Could not create the team.');
    } finally {
      setBusy(false);
    }
  }

  function reset(): void {
    setStep(0);
    setProjectId('');
    setGoal('');
    setTeamName('');
    setRoster([]);
    setPersonalityIds([]);
    setError(null);
  }

  function handleClose(): void {
    reset();
    onClose();
  }

  return (
    <Modal open={open} onClose={handleClose} labelledBy='squad-wizard-title' className='max-w-2xl'>
      <div className='flex items-center justify-between gap-3'>
        <div className='flex items-center gap-2'>
          <span className='flex h-9 w-9 items-center justify-center rounded-xl bg-primary/15 text-primary'>
            <Users className='h-5 w-5' />
          </span>
          <div>
            <h2 id='squad-wizard-title' className='text-lg font-semibold leading-tight'>
              Build a team
            </h2>
            <p className='text-xs text-muted-foreground'>
              A few clicks and you have a coordinated multi-AI squad on a project.
            </p>
          </div>
        </div>
        <Button variant='ghost' size='icon' onClick={handleClose} aria-label='Close'>
          <X className='h-4 w-4' />
        </Button>
      </div>

      {/* Stepper */}
      <ol className='flex items-center gap-2 text-xs'>
        {STEPS.map((label, index) => (
          <li key={label} className='flex items-center gap-2'>
            <span
              className={cn(
                'flex h-6 w-6 items-center justify-center rounded-full border text-[11px] font-semibold',
                index < step && 'border-primary bg-primary text-primary-foreground',
                index === step && 'border-primary text-primary',
                index > step && 'border-border text-muted-foreground'
              )}
            >
              {index < step ? <Check className='h-3 w-3' /> : index + 1}
            </span>
            <span className={cn(index === step ? 'text-foreground' : 'text-muted-foreground')}>{label}</span>
            {index < STEPS.length - 1 && <ChevronRight className='h-3 w-3 text-muted-foreground' />}
          </li>
        ))}
      </ol>

      <div className='min-h-[260px]'>
        {step === 0 && (
          <div className='space-y-4'>
            <div>
              <label className='flex flex-col gap-1.5 text-sm'>
                <span className='font-medium'>What should this team accomplish?</span>
                <textarea
                  value={goal}
                  onChange={(e) => setGoal(e.target.value)}
                  rows={4}
                  placeholder='e.g. Build a small to-do web page with add/remove and localStorage.'
                  className='rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring'
                  style={{ colorScheme: 'dark' }}
                />
              </label>
            </div>
            <div className='grid gap-3 sm:grid-cols-2'>
              <label className='flex flex-col gap-1.5 text-sm'>
                <span className='font-medium'>Project</span>
                <select
                  value={effectiveProjectId}
                  onChange={(e) => setProjectId(e.target.value)}
                  className='rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring'
                  style={{ colorScheme: 'dark' }}
                >
                  {projects.length === 0 && <option value=''>No projects yet</option>}
                  {projects.map((project) => (
                    <option key={project.id} value={project.id} className='bg-card'>
                      {project.name}
                    </option>
                  ))}
                </select>
              </label>
              <label className='flex flex-col gap-1.5 text-sm'>
                <span className='font-medium'>Team name (optional)</span>
                <Input
                  value={teamName}
                  onChange={(e) => setTeamName(e.target.value)}
                  placeholder='Auto from your goal'
                />
              </label>
            </div>
            <p className='text-xs text-muted-foreground'>
              The team shares this project&apos;s working directory and memory. You can add or
              change roles in the next steps.
            </p>
          </div>
        )}

        {step === 1 && (
          <div className='space-y-3'>
            <p className='text-sm text-muted-foreground'>
              Pick a starting team. You can fine-tune the roster next.
            </p>
            <div className='grid gap-3 sm:grid-cols-2'>
              {PRESETS.map((preset) => (
                <button
                  key={preset.id}
                  type='button'
                  onClick={() => applyPreset(preset)}
                  className='rounded-xl border border-border bg-card/60 p-4 text-left transition-colors hover:border-primary/60 hover:bg-accent/40'
                >
                  <div className='flex items-center justify-between gap-2'>
                    <span className='font-medium'>{preset.name}</span>
                    {preset.roleIds.length > 0 ? (
                      <span className='rounded-full border border-border px-2 py-0.5 text-[11px] text-muted-foreground'>
                        {preset.roleIds.length} {preset.roleIds.length === 1 ? 'role' : 'roles'}
                      </span>
                    ) : (
                      <Sparkles className='h-4 w-4 text-primary' />
                    )}
                  </div>
                  <p className='mt-1 text-xs text-muted-foreground'>{preset.blurb}</p>
                </button>
              ))}
            </div>
          </div>
        )}

        {step === 2 && (
          <div className='space-y-4'>
            <div>
              <div className='flex items-center justify-between'>
                <h3 className='text-sm font-semibold'>Your team ({roster.length})</h3>
                {roster.length > 0 && (
                  <button
                    type='button'
                    onClick={clearRoster}
                    className='text-xs text-muted-foreground hover:text-foreground'
                  >
                    Clear all
                  </button>
                )}
              </div>
              {roster.length === 0 ? (
                <p className='mt-2 rounded-lg border border-dashed border-border p-3 text-xs text-muted-foreground'>
                  No roles yet. Add some from the list below — a boss is a good start.
                </p>
              ) : (
                <ul className='mt-2 flex flex-col gap-2'>
                  {roster.map((id, index) => {
                    const role = roleById.get(id);
                    const Icon = TIER_ICON[role?.role_tier ?? 'worker'];
                    return (
                      <li
                        key={`${id}-${index}`}
                        className='flex items-center gap-2 rounded-lg border border-border bg-secondary/20 px-3 py-2 text-sm'
                      >
                        <Icon className='h-3.5 w-3.5 shrink-0 text-muted-foreground' />
                        <span className='min-w-0 flex-1 truncate'>{role?.name ?? id}</span>
                        <select
                          value={personalityIds[index] ?? ''}
                          onChange={(e) => setPersonalityAt(index, e.target.value || null)}
                          title='Personality'
                          aria-label={`Personality for ${role?.name ?? id}`}
                          className='max-w-[10rem] shrink-0 rounded-md border border-input bg-background px-2 py-1 text-xs outline-none focus-visible:ring-2 focus-visible:ring-ring'
                          style={{ colorScheme: 'dark' }}
                        >
                          <option value='' className='bg-card'>Default personality</option>
                          {personalities.map((p) => (
                            <option key={p.id} value={p.id} className='bg-card'>
                              {p.name}
                            </option>
                          ))}
                        </select>
                        <button
                          type='button'
                          onClick={() => removeRoleAt(index)}
                          className='flex h-6 w-6 shrink-0 items-center justify-center rounded-full hover:bg-destructive/20'
                          aria-label={`Remove ${role?.name ?? id}`}
                        >
                          <X className='h-3 w-3' />
                        </button>
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>

            <div className='space-y-3'>
              {TIER_ORDER.map((tier) => {
                const tierRoles = rolesByTier[tier];
                if (!tierRoles || tierRoles.length === 0) return null;
                const TierIcon = TIER_ICON[tier];
                return (
                  <div key={tier}>
                    <div className='flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground'>
                      <TierIcon className='h-3.5 w-3.5' />
                      {TIER_LABEL[tier]}
                    </div>
                    <div className='mt-1.5 flex flex-wrap gap-2'>
                      {tierRoles.map((role) => (
                        <button
                          key={role.id}
                          type='button'
                          onClick={() => addRole(role.id)}
                          title={role.description}
                          className='flex items-center gap-1.5 rounded-lg border border-border bg-card/60 px-3 py-1.5 text-sm transition-colors hover:border-primary/60 hover:bg-accent/40'
                        >
                          <Plus className='h-3.5 w-3.5 text-primary' />
                          {role.name}
                        </button>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {step === 3 && (
          <div className='space-y-4 text-sm'>
            <div className='rounded-xl border border-border bg-card/60 p-4'>
              <dl className='space-y-2'>
                <div className='flex justify-between gap-4'>
                  <dt className='text-muted-foreground'>Team</dt>
                  <dd className='text-right font-medium'>{teamName.trim() || goal.trim().slice(0, 48) || 'New team'}</dd>
                </div>
                <div className='flex justify-between gap-4'>
                  <dt className='text-muted-foreground'>Project</dt>
                  <dd className='text-right'>{roleById && (projects.find((p) => p.id === effectiveProjectId)?.name ?? effectiveProjectId)}</dd>
                </div>
                <div className='flex justify-between gap-4'>
                  <dt className='text-muted-foreground'>Roles</dt>
                  <dd className='text-right'>{roster.length}</dd>
                </div>
              </dl>
              <p className='mt-3 border-t border-border pt-3 text-xs text-muted-foreground'>{goal.trim()}</p>
            </div>
            <ul className='flex flex-wrap gap-2'>
              {roster.map((id, index) => {
                const role = roleById.get(id);
                const Icon = TIER_ICON[role?.role_tier ?? 'worker'];
                return (
                  <li
                    key={`${id}-${index}`}
                    className='flex items-center gap-1.5 rounded-full border border-border bg-secondary/30 px-3 py-1 text-xs'
                  >
                    <Icon className='h-3 w-3 text-muted-foreground' />
                    {role?.name ?? id}
                    {personalityIds[index] && (
                      <span className='text-primary'>
                        · {personalities.find((p) => p.id === personalityIds[index])?.name ?? personalityIds[index]}
                      </span>
                    )}
                  </li>
                );
              })}
            </ul>
            <p className='text-xs text-muted-foreground'>
              Creating the team adds one queued task per role. Nothing launches until you click
              Launch on a task, so you stay in control. Give two of the same role different
              personalities and they&apos;ll collaborate and debate.
            </p>
          </div>
        )}
      </div>

      {error && <p role='alert' className='text-sm text-destructive'>{error}</p>}

      <div className='flex items-center justify-between gap-2 border-t border-border pt-4'>
        <Button
          variant='ghost'
          onClick={() => (step === 0 ? handleClose() : setStep((s) => s - 1))}
          disabled={busy}
        >
          {step === 0 ? 'Cancel' : (<><ChevronLeft className='h-4 w-4' /> Back</>)}
        </Button>
        {step < 3 ? (
          <Button onClick={() => setStep((s) => s + 1)} disabled={!canNext || busy}>
            Next <ChevronRight className='h-4 w-4' />
          </Button>
        ) : (
          <Button onClick={() => void create()} disabled={busy || roster.length === 0 || !effectiveProjectId}>
            {busy ? <Loader2 className='h-4 w-4 animate-spin' /> : <Check className='h-4 w-4' />}
            Create team
          </Button>
        )}
      </div>
    </Modal>
  );
}
