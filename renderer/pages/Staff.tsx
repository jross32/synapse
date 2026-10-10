import { useEffect, useMemo, useState } from 'react';
import {
  Activity,
  BadgeCheck,
  BellRing,
  Bot,
  BriefcaseBusiness,
  CheckCircle2,
  ChevronLeft,
  CircleDot,
  Clock3,
  Goal,
  Gauge,
  Link2,
  MessageCircle,
  Mic,
  Network,
  NotebookPen,
  Play,
  Route,
  Send,
  ShieldCheck,
  Sparkles,
  Target,
  UsersRound,
  Volume2,
  VolumeX,
  WandSparkles,
  Zap,
} from 'lucide-react';

import { StaffChatPanel } from '../components/StaffChatPanel';
import { MayaGrowthReviewPanel } from '../components/MayaGrowthReviewPanel';
import { MayaExecutionPanel } from '../components/MayaExecutionPanel';
import { launchAgentWorkItem } from '@shared/agent-squads-client';
import { listProjects } from '@shared/projects-client';
import {
  createStaffCouncil,
  createStaffMemory,
  getStaff,
  getStaffBriefing,
  getStaffDashboard,
  getStaffChat,
  listStaff,
  routeStaffTask,
  sendStaffChat,
  summonStaff,
  updateStaff,
  type StaffAvatarAsset,
  type StaffBriefing,
  type StaffChannelConnection,
  type StaffChatMessage,
  type StaffCouncilResponse,
  type StaffDashboard,
  type StaffEvent,
  type StaffKpi,
  type StaffMember,
  type StaffMemory,
  type StaffPermission,
  type StaffProfile,
  type StaffRouteResult,
  type StaffTrigger,
} from '@shared/staff-client';
import { cn } from '@shared/utils';

type ProjectOption = { id: string; name: string };
type StaffSection = 'overview' | 'kpis' | 'memory' | 'permissions' | 'automation' | 'activity';

function AvatarBadge({
  asset,
  name,
  size = 'lg',
  onClick,
}: {
  asset?: StaffAvatarAsset | null;
  name: string;
  size?: 'sm' | 'lg' | 'xl';
  onClick?: () => void;
}): JSX.Element {
  const dimensions =
    size === 'xl'
      ? 'h-28 w-28 text-4xl'
      : size === 'lg'
        ? 'h-16 w-16 text-2xl'
        : 'h-11 w-11 text-lg';

  return (
    <button
      type='button'
      onClick={onClick}
      disabled={!onClick}
      aria-label={onClick ? `Change ${name}'s avatar` : undefined}
      className={cn(
        'relative grid shrink-0 place-items-center overflow-hidden rounded-[28%] border border-white/15 shadow-[0_18px_60px_rgba(0,0,0,.35)]',
        dimensions,
        onClick &&
          'cursor-pointer transition hover:scale-[1.03] hover:border-primary/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary'
      )}
      style={{
        background: asset?.background ?? 'linear-gradient(145deg,#111827,#334155)',
        color: asset?.accent ?? '#fff',
      }}
    >
      <span className='select-none drop-shadow-[0_2px_10px_rgba(255,255,255,.25)]'>
        {asset?.glyph ?? name.slice(0, 1)}
      </span>
      <span className='absolute inset-x-2 bottom-1 h-px bg-white/20' />
    </button>
  );
}

function statusLabel(status: StaffMember['status']): string {
  return status.replaceAll('_', ' ');
}

function StatusPill({ status }: { status: StaffMember['status'] }): JSX.Element {
  const tone =
    status === 'blocked'
      ? 'border-red-400/30 bg-red-500/10 text-red-300'
      : status === 'waiting_for_owner'
        ? 'border-amber-400/30 bg-amber-500/10 text-amber-300'
        : status === 'working'
          ? 'border-blue-400/30 bg-blue-500/10 text-blue-300'
          : status === 'offline'
            ? 'border-border bg-background/70 text-muted-foreground'
            : 'border-emerald-400/25 bg-emerald-500/10 text-emerald-300';
  return (
    <span className={cn('inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[10px] capitalize', tone)}>
      <CircleDot className='h-3 w-3' />
      {statusLabel(status)}
    </span>
  );
}

function StaffCard({
  member,
  asset,
  selected,
  onClick,
}: {
  member: StaffMember;
  asset?: StaffAvatarAsset;
  selected: boolean;
  onClick: () => void;
}): JSX.Element {
  return (
    <button
      type='button'
      onClick={onClick}
      className={cn(
        'group w-full rounded-3xl border p-4 text-left transition',
        selected
          ? 'border-primary/50 bg-primary/10 shadow-[0_18px_55px_rgba(59,130,246,.12)]'
          : 'border-border bg-card/70 hover:border-primary/30 hover:bg-accent/50'
      )}
    >
      <div className='flex items-start gap-3'>
        <AvatarBadge asset={asset} name={member.display_name} size='sm' />
        <div className='min-w-0 flex-1'>
          <div className='flex items-start justify-between gap-2'>
            <div>
              <p className='truncate font-semibold text-foreground'>{member.display_name}</p>
              <p className='truncate text-xs text-primary'>@{member.handle}</p>
            </div>
            <StatusPill status={member.status} />
          </div>
          <p className='mt-2 text-xs font-medium text-foreground/90'>{member.title}</p>
          <p className='mt-1 line-clamp-2 text-xs leading-5 text-muted-foreground'>
            {member.status_line || member.bio}
          </p>
        </div>
      </div>
    </button>
  );
}

function ModalShell({
  children,
  onClose,
  maxWidth = 'max-w-2xl',
}: {
  children: React.ReactNode;
  onClose: () => void;
  maxWidth?: string;
}): JSX.Element {
  return (
    <div
      className='fixed inset-0 z-50 grid place-items-center overflow-y-auto bg-black/70 p-4 backdrop-blur-sm'
      onMouseDown={onClose}
    >
      <div
        className={cn('my-6 w-full rounded-3xl border border-border bg-card p-5 shadow-2xl', maxWidth)}
        onMouseDown={(event) => event.stopPropagation()}
      >
        {children}
      </div>
    </div>
  );
}

function AvatarPicker({
  assets,
  selectedId,
  onPick,
  onClose,
}: {
  assets: StaffAvatarAsset[];
  selectedId: string | null;
  onPick: (asset: StaffAvatarAsset) => void;
  onClose: () => void;
}): JSX.Element {
  return (
    <ModalShell onClose={onClose}>
      <div className='mb-4 flex items-start justify-between gap-4'>
        <div>
          <p className='text-sm font-semibold text-foreground'>Choose profile badge</p>
          <p className='mt-1 text-xs text-muted-foreground'>
            Synapse avatar assets work like classic gamer profile tiles: fast to recognize and easy to swap.
          </p>
        </div>
        <button type='button' onClick={onClose} className='rounded-xl border border-border px-3 py-1.5 text-xs text-muted-foreground hover:text-foreground'>
          Close
        </button>
      </div>
      <div className='grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-5'>
        {assets.map((asset) => (
          <button
            key={asset.id}
            type='button'
            onClick={() => onPick(asset)}
            className={cn(
              'rounded-2xl border p-3 text-center transition hover:-translate-y-0.5',
              selectedId === asset.id
                ? 'border-primary bg-primary/10'
                : 'border-border bg-background/45 hover:border-primary/35'
            )}
          >
            <div
              className='mx-auto grid h-16 w-16 place-items-center rounded-2xl border border-white/15 text-2xl'
              style={{ background: asset.background, color: asset.accent }}
            >
              {asset.glyph}
            </div>
            <p className='mt-2 truncate text-[11px] font-medium text-foreground'>{asset.name}</p>
          </button>
        ))}
      </div>
    </ModalShell>
  );
}

function CallInModal({
  person,
  projects,
  onClose,
  onAssigned,
}: {
  person: StaffMember;
  projects: ProjectOption[];
  onClose: () => void;
  onAssigned: () => void;
}): JSX.Element {
  const [projectId, setProjectId] = useState(projects[0]?.id ?? '');
  const [task, setTask] = useState('');
  const [details, setDetails] = useState('');
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState('');

  async function assign(): Promise<void> {
    if (!projectId || !task.trim() || busy) return;
    setBusy(true);
    setResult('');
    try {
      const created = await summonStaff(person.id, {
        project_id: projectId,
        task: task.trim(),
        instructions_md: details.trim(),
      });
      try {
        const launched = await launchAgentWorkItem(created.work_item.id, {
          execution_mode: 'automatic',
          authority: created.recommended_execution_authority,
          open_in_tab: true,
          timeout_seconds: 1800,
        });
        setResult(
          'Called in ' +
            person.display_name +
            '. ' +
            launched.runtime +
            ' is working with ' +
            created.recommended_execution_authority +
            ' authority.'
        );
      } catch (launchError) {
        const message =
          launchError instanceof Error ? launchError.message : 'runtime launch needs attention';
        setResult(
          'Assignment saved for ' +
            person.display_name +
            ', but the runtime did not launch: ' +
            message
        );
      }
      onAssigned();
    } catch (error) {
      setResult(error instanceof Error ? error.message : 'Could not create the assignment.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <ModalShell onClose={onClose} maxWidth='max-w-xl'>
      <div className='flex items-start justify-between gap-4'>
        <div>
          <p className='text-sm font-semibold text-foreground'>Call in {person.display_name}</p>
          <p className='mt-1 text-xs text-muted-foreground'>
            Give {person.display_name} a real assignment. Synapse keeps this identity attached to the work and enforces the stored authority policy at launch.
          </p>
        </div>
        <button type='button' onClick={onClose} className='rounded-xl border border-border px-3 py-1.5 text-xs text-muted-foreground hover:text-foreground'>
          Close
        </button>
      </div>

      <div className='mt-5 space-y-4'>
        <label className='block text-xs font-medium text-foreground'>
          App / project
          <select
            value={projectId}
            onChange={(event) => setProjectId(event.target.value)}
            className='mt-2 w-full rounded-2xl border border-border bg-background px-3 py-3 text-sm text-foreground'
          >
            {projects.map((project) => (
              <option key={project.id} value={project.id}>
                {project.name}
              </option>
            ))}
          </select>
        </label>

        <label className='block text-xs font-medium text-foreground'>
          What should {person.display_name} do?
          <input
            value={task}
            onChange={(event) => setTask(event.target.value)}
            placeholder='e.g. Find the highest-ROI growth move for this app'
            className='mt-2 w-full rounded-2xl border border-border bg-background px-3 py-3 text-sm text-foreground outline-none focus:border-primary/60'
          />
        </label>

        <label className='block text-xs font-medium text-foreground'>
          Extra context <span className='font-normal text-muted-foreground'>(optional)</span>
          <textarea
            value={details}
            onChange={(event) => setDetails(event.target.value)}
            rows={4}
            placeholder='Constraints, what success looks like, or anything they should know.'
            className='mt-2 w-full resize-none rounded-2xl border border-border bg-background px-3 py-3 text-sm text-foreground outline-none focus:border-primary/60'
          />
        </label>

        <div className='rounded-2xl border border-border bg-background/50 p-3 text-xs text-muted-foreground'>
          Staff policy: <span className='font-medium capitalize text-foreground'>{person.authority_policy.replaceAll('_', ' ')}</span>. Full machine authority is never granted through a normal staff assignment.
        </div>

        {result && (
          <div className='rounded-2xl border border-primary/25 bg-primary/10 p-3 text-xs leading-5 text-foreground'>
            {result}
          </div>
        )}

        <button
          type='button'
          disabled={busy || !projectId || !task.trim()}
          onClick={() => void assign()}
          className='flex w-full items-center justify-center gap-2 rounded-2xl bg-primary px-4 py-3 text-sm font-semibold text-primary-foreground transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-50'
        >
          <BriefcaseBusiness className='h-4 w-4' />
          {busy ? 'Calling in...' : 'Call in ' + person.display_name}
        </button>
      </div>
    </ModalShell>
  );
}


function StaffChatModal({
  person,
  asset,
  onClose,
}: {
  person: StaffMember;
  asset?: StaffAvatarAsset | null;
  onClose: () => void;
}): JSX.Element {
  const [messages, setMessages] = useState<StaffChatMessage[]>([]);
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(true);
  const [listening, setListening] = useState(false);
  const [readAloud, setReadAloud] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    void getStaffChat(person.id)
      .then((result) => {
        if (active) setMessages(result.messages);
      })
      .catch((err: unknown) => {
        if (active) setError(err instanceof Error ? err.message : 'Could not load the conversation.');
      })
      .finally(() => {
        if (active) setBusy(false);
      });
    return () => {
      active = false;
      window.speechSynthesis?.cancel();
    };
  }, [person.id]);

  function speak(text: string): void {
    if (!readAloud || !('speechSynthesis' in window)) return;
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = 1.02;
    utterance.pitch = 1.02;
    window.speechSynthesis.speak(utterance);
  }

  function startListening(): void {
    const SpeechRecognitionCtor =
      (window as unknown as { SpeechRecognition?: new () => any }).SpeechRecognition ??
      (window as unknown as { webkitSpeechRecognition?: new () => any }).webkitSpeechRecognition;
    if (!SpeechRecognitionCtor) {
      setError('Voice dictation is not available in this Chromium build yet. You can still type to Maya.');
      return;
    }
    const recognition = new SpeechRecognitionCtor();
    recognition.lang = 'en-US';
    recognition.interimResults = false;
    recognition.continuous = false;
    recognition.onstart = () => setListening(true);
    recognition.onend = () => setListening(false);
    recognition.onerror = () => {
      setListening(false);
      setError('I could not hear that clearly. Try the mic again or type your message.');
    };
    recognition.onresult = (event: any) => {
      const transcript = event?.results?.[0]?.[0]?.transcript ?? '';
      if (transcript) setDraft((current) => (current ? current + ' ' : '') + transcript);
    };
    recognition.start();
  }

  async function send(): Promise<void> {
    const text = draft.trim();
    if (!text || busy) return;
    setBusy(true);
    setError('');
    setDraft('');
    const optimistic: StaffChatMessage = {
      id: 'optimistic-' + Date.now(),
      staff_member_id: person.id,
      role: 'user',
      content: text,
      created_at: new Date().toISOString(),
    };
    setMessages((current) => [...current, optimistic]);
    try {
      const result = await sendStaffChat(person.id, text);
      setMessages((current) => [
        ...current.filter((message) => message.id !== optimistic.id),
        result.user_message,
        result.assistant_message,
      ]);
      speak(result.assistant_message.content);
    } catch (err) {
      setMessages((current) => current.filter((message) => message.id !== optimistic.id));
      setDraft(text);
      setError(err instanceof Error ? err.message : 'Maya could not answer this turn.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <ModalShell onClose={onClose} maxWidth='max-w-3xl'>
      <div className='flex items-start justify-between gap-4 border-b border-border pb-4'>
        <div className='flex min-w-0 items-center gap-3'>
          <AvatarBadge asset={asset} name={person.display_name} size='lg' />
          <div className='min-w-0'>
            <div className='flex items-center gap-2'>
              <h2 className='text-lg font-semibold text-foreground'>{person.display_name}</h2>
              <StatusPill status={person.status} />
            </div>
            <p className='text-xs font-medium text-primary'>{person.title} · @{person.handle}</p>
            <p className='mt-1 text-[11px] text-muted-foreground'>
              Live staff conversation · persistent transcript · personality applied every turn
            </p>
          </div>
        </div>
        <div className='flex items-center gap-2'>
          <button
            type='button'
            onClick={() => {
              setReadAloud((value) => !value);
              window.speechSynthesis?.cancel();
            }}
            className='grid h-9 w-9 place-items-center rounded-xl border border-border text-muted-foreground hover:text-foreground'
            title={readAloud ? 'Turn read-aloud off' : 'Turn read-aloud on'}
          >
            {readAloud ? <Volume2 className='h-4 w-4' /> : <VolumeX className='h-4 w-4' />}
          </button>
          <button
            type='button'
            onClick={onClose}
            className='rounded-xl border border-border px-3 py-2 text-xs text-muted-foreground hover:text-foreground'
          >
            Close
          </button>
        </div>
      </div>

      <div className='mt-4 h-[430px] space-y-3 overflow-y-auto rounded-3xl border border-border bg-background/40 p-4'>
        {messages.length === 0 && !busy ? (
          <div className='grid h-full place-items-center text-center'>
            <div>
              <AvatarBadge asset={asset} name={person.display_name} size='lg' />
              <p className='mt-4 text-sm font-semibold text-foreground'>Talk to {person.display_name}</p>
              <p className='mx-auto mt-1 max-w-sm text-xs leading-5 text-muted-foreground'>
                This is the simplest place to observe her personality before the full Personality Lab is finished. Ask for advice, disagree with her, give her an ambiguous problem, or see what she prioritizes.
              </p>
            </div>
          </div>
        ) : (
          messages.map((message) => (
            <div
              key={message.id}
              className={cn(
                'flex',
                message.role === 'user' ? 'justify-end' : 'justify-start'
              )}
            >
              <div
                className={cn(
                  'max-w-[82%] rounded-3xl px-4 py-3 text-sm leading-6',
                  message.role === 'user'
                    ? 'rounded-br-lg bg-primary text-primary-foreground'
                    : 'rounded-bl-lg border border-border bg-card text-foreground'
                )}
              >
                {message.content}
              </div>
            </div>
          ))
        )}
        {busy && messages.length > 0 && (
          <div className='flex justify-start'>
            <div className='rounded-3xl rounded-bl-lg border border-border bg-card px-4 py-3 text-xs text-muted-foreground'>
              {person.display_name} is thinking...
            </div>
          </div>
        )}
      </div>

      {error && (
        <div className='mt-3 rounded-2xl border border-destructive/30 bg-destructive/10 p-3 text-xs text-destructive'>
          {error}
        </div>
      )}

      <div className='mt-4 flex items-end gap-2'>
        <button
          type='button'
          disabled={busy || listening}
          onClick={startListening}
          className={cn(
            'grid h-12 w-12 shrink-0 place-items-center rounded-2xl border transition',
            listening
              ? 'border-red-400/40 bg-red-500/15 text-red-300'
              : 'border-border bg-background text-muted-foreground hover:border-primary/40 hover:text-primary'
          )}
          title='Speak your message'
        >
          <Mic className='h-5 w-5' />
        </button>
        <textarea
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault();
              void send();
            }
          }}
          rows={2}
          placeholder={listening ? 'Listening...' : 'Message Maya...'}
          className='min-h-12 flex-1 resize-none rounded-2xl border border-border bg-background px-4 py-3 text-sm text-foreground outline-none focus:border-primary/60'
        />
        <button
          type='button'
          disabled={busy || !draft.trim()}
          onClick={() => void send()}
          className='grid h-12 w-12 shrink-0 place-items-center rounded-2xl bg-primary text-primary-foreground transition hover:brightness-110 disabled:opacity-50'
          title='Send'
        >
          <Send className='h-5 w-5' />
        </button>
      </div>
      <p className='mt-2 text-[10px] text-muted-foreground'>
        Enter sends · Shift+Enter adds a line · mic uses local browser dictation when available · read-aloud can be toggled above.
      </p>
    </ModalShell>
  );
}

function BriefingModal({
  briefing,
  onClose,
}: {
  briefing: StaffBriefing;
  onClose: () => void;
}): JSX.Element {
  return (
    <ModalShell onClose={onClose} maxWidth='max-w-4xl'>
      <div className='flex items-start justify-between gap-4'>
        <div>
          <div className='flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.16em] text-primary'>
            <Sparkles className='h-4 w-4' />
            Staff briefing
          </div>
          <h2 className='mt-2 text-xl font-semibold text-foreground'>What needs your attention</h2>
          <p className='mt-1 text-sm text-muted-foreground'>{briefing.suggested_owner_action}</p>
        </div>
        <button type='button' onClick={onClose} className='rounded-xl border border-border px-3 py-1.5 text-xs text-muted-foreground hover:text-foreground'>
          Close
        </button>
      </div>

      <div className='mt-5 grid gap-3 sm:grid-cols-5'>
        {[
          ['Staff', briefing.counts.staff],
          ['Working', briefing.counts.working],
          ['Waiting', briefing.counts.waiting_for_owner],
          ['Blocked', briefing.counts.blocked],
          ['Needs you', briefing.counts.attention_items],
        ].map(([label, value]) => (
          <div key={String(label)} className='rounded-2xl border border-border bg-background/45 p-3'>
            <p className='text-[10px] uppercase tracking-[0.14em] text-muted-foreground'>{label}</p>
            <p className='mt-1 text-xl font-semibold text-foreground'>{value}</p>
          </div>
        ))}
      </div>

      <div className='mt-5 grid gap-4 lg:grid-cols-[1.1fr_.9fr]'>
        <section className='rounded-3xl border border-border bg-background/35 p-4'>
          <p className='text-sm font-semibold text-foreground'>Attention queue</p>
          <div className='mt-3 space-y-2'>
            {briefing.attention.length === 0 ? (
              <div className='rounded-2xl border border-dashed border-border p-4 text-xs leading-5 text-muted-foreground'>
                No evidence-backed staff alert currently requires you. Unknown KPIs remain unknown rather than being treated as healthy.
              </div>
            ) : (
              briefing.attention.map((item, index) => (
                <div key={item.staff_id + item.title + index} className='rounded-2xl border border-border bg-card/60 p-3'>
                  <div className='flex items-center justify-between gap-3'>
                    <p className='text-xs font-semibold text-foreground'>{item.title}</p>
                    <span className='text-[10px] uppercase tracking-wide text-muted-foreground'>{item.severity}</span>
                  </div>
                  <p className='mt-1 text-xs leading-5 text-muted-foreground'>{item.detail}</p>
                </div>
              ))
            )}
          </div>
        </section>

        <section className='rounded-3xl border border-border bg-background/35 p-4'>
          <p className='text-sm font-semibold text-foreground'>Team pulse</p>
          <div className='mt-3 space-y-2'>
            {briefing.team.map((person) => (
              <div key={person.staff_id} className='rounded-2xl border border-border bg-card/60 p-3'>
                <div className='flex items-center justify-between gap-3'>
                  <div>
                    <p className='text-xs font-semibold text-foreground'>{person.display_name}</p>
                    <p className='text-[11px] text-muted-foreground'>{person.title}</p>
                  </div>
                  <StatusPill status={person.status} />
                </div>
                <div className='mt-2 flex gap-3 text-[10px] text-muted-foreground'>
                  <span>{person.kpis.on_track} on track</span>
                  <span>{person.kpis.watch} watch</span>
                  <span>{person.kpis.off_track} off track</span>
                  <span>{person.kpis.unknown} unknown</span>
                </div>
              </div>
            ))}
          </div>
        </section>
      </div>
    </ModalShell>
  );
}

function CouncilModal({
  projects,
  onClose,
  onCreated,
}: {
  projects: ProjectOption[];
  onClose: () => void;
  onCreated: () => void;
}): JSX.Element {
  const [projectId, setProjectId] = useState(projects[0]?.id ?? '');
  const [objective, setObjective] = useState('');
  const [maxMembers, setMaxMembers] = useState(4);
  const [launchNow, setLaunchNow] = useState(true);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState('');
  const [council, setCouncil] = useState<StaffCouncilResponse | null>(null);

  async function create(): Promise<void> {
    if (!projectId || !objective.trim() || busy) return;
    setBusy(true);
    setResult('');
    try {
      const created = await createStaffCouncil({
        project_id: projectId,
        objective: objective.trim(),
        max_members: maxMembers,
      });
      setCouncil(created);
      if (launchNow) {
        const outcomes: string[] = [];
        for (const member of created.members) {
          try {
            const launched = await launchAgentWorkItem(member.work_item.id, {
              execution_mode: 'automatic',
              authority: member.recommended_execution_authority,
              open_in_tab: true,
              timeout_seconds: 1800,
            });
            outcomes.push(member.display_name + ': ' + launched.runtime + ' launched');
          } catch (error) {
            outcomes.push(
              member.display_name +
                ': launch failed — ' +
                (error instanceof Error ? error.message : 'unknown error')
            );
          }
        }
        setResult(outcomes.join('\n'));
      } else {
        setResult('Council created and queued. No runtime was launched.');
      }
      onCreated();
    } catch (error) {
      setResult(error instanceof Error ? error.message : 'Could not create the staff council.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <ModalShell onClose={onClose} maxWidth='max-w-2xl'>
      <div className='flex items-start justify-between gap-4'>
        <div>
          <div className='flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.16em] text-primary'>
            <UsersRound className='h-4 w-4' />
            Staff Council
          </div>
          <h2 className='mt-2 text-lg font-semibold text-foreground'>Put several people on one decision</h2>
          <p className='mt-1 text-xs leading-5 text-muted-foreground'>
            Synapse routes the objective to relevant staff, gives each a non-overlapping domain brief, links every work item back to that person, and keeps their authority boundary intact.
          </p>
        </div>
        <button type='button' onClick={onClose} className='rounded-xl border border-border px-3 py-1.5 text-xs text-muted-foreground hover:text-foreground'>
          Close
        </button>
      </div>

      <div className='mt-5 space-y-4'>
        <label className='block text-xs font-medium text-foreground'>
          Project
          <select
            value={projectId}
            onChange={(event) => setProjectId(event.target.value)}
            className='mt-2 w-full rounded-2xl border border-border bg-background px-3 py-3 text-sm text-foreground'
          >
            {projects.map((project) => (
              <option key={project.id} value={project.id}>
                {project.name}
              </option>
            ))}
          </select>
        </label>

        <label className='block text-xs font-medium text-foreground'>
          Council objective
          <textarea
            value={objective}
            onChange={(event) => setObjective(event.target.value)}
            rows={4}
            placeholder='e.g. Decide which app has the strongest path to revenue this month and what each department should do next.'
            className='mt-2 w-full resize-none rounded-2xl border border-border bg-background px-3 py-3 text-sm text-foreground outline-none focus:border-primary/60'
          />
        </label>

        <div className='grid gap-3 sm:grid-cols-2'>
          <label className='text-xs font-medium text-foreground'>
            Max people
            <select
              value={maxMembers}
              onChange={(event) => setMaxMembers(Number(event.target.value))}
              className='mt-2 w-full rounded-2xl border border-border bg-background px-3 py-3 text-sm text-foreground'
            >
              {[2, 3, 4, 5, 6].map((count) => (
                <option key={count} value={count}>
                  {count}
                </option>
              ))}
            </select>
          </label>
          <label className='flex items-center gap-3 rounded-2xl border border-border bg-background/50 px-4 py-3 text-xs text-foreground sm:mt-6'>
            <input
              type='checkbox'
              checked={launchNow}
              onChange={(event) => setLaunchNow(event.target.checked)}
            />
            Launch the selected staff now
          </label>
        </div>

        {council && (
          <div className='rounded-2xl border border-primary/25 bg-primary/10 p-3'>
            <p className='text-xs font-semibold text-foreground'>Council created · {council.squad.id}</p>
            <p className='mt-1 text-[11px] text-muted-foreground'>
              {council.members.map((member) => member.display_name).join(' · ')}
            </p>
          </div>
        )}

        {result && (
          <pre className='whitespace-pre-wrap rounded-2xl border border-border bg-background/70 p-3 text-[11px] leading-5 text-muted-foreground'>
            {result}
          </pre>
        )}

        <button
          type='button'
          disabled={busy || !projectId || !objective.trim()}
          onClick={() => void create()}
          className='flex w-full items-center justify-center gap-2 rounded-2xl bg-primary px-4 py-3 text-sm font-semibold text-primary-foreground transition hover:brightness-110 disabled:opacity-50'
        >
          <UsersRound className='h-4 w-4' />
          {busy ? 'Building council...' : 'Create Staff Council'}
        </button>
      </div>
    </ModalShell>
  );
}

function QuickRouteBar({
  projects,
  onAssigned,
}: {
  projects: ProjectOption[];
  onAssigned: () => void;
}): JSX.Element {
  const [projectId, setProjectId] = useState(projects[0]?.id ?? '');
  const [task, setTask] = useState('');
  const [result, setResult] = useState<StaffRouteResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');

  useEffect(() => {
    if (!projectId && projects[0]) setProjectId(projects[0].id);
  }, [projectId, projects]);

  async function route(assign: boolean): Promise<void> {
    if (!task.trim() || busy) return;
    setBusy(true);
    setMessage('');
    try {
      const routed = await routeStaffTask({
        task: task.trim(),
        project_id: projectId || undefined,
        create_assignment: assign,
      });
      setResult(routed);
      if (assign && routed.assignment) {
        try {
          const launched = await launchAgentWorkItem(routed.assignment.work_item.id, {
            execution_mode: 'automatic',
            authority: routed.assignment.recommended_execution_authority,
            open_in_tab: true,
            timeout_seconds: 1800,
          });
          setMessage(
            routed.selected.display_name +
              ' was selected and ' +
              launched.runtime +
              ' is working now.'
          );
        } catch (error) {
          setMessage(
            routed.selected.display_name +
              ' was assigned, but runtime launch failed: ' +
              (error instanceof Error ? error.message : 'unknown error')
          );
        }
        onAssigned();
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Could not route this task.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className='rounded-[28px] border border-primary/20 bg-[radial-gradient(circle_at_15%_0%,rgba(59,130,246,.15),transparent_38%),rgba(15,23,42,.35)] p-4'>
      <div className='flex items-center gap-2 text-xs font-semibold text-foreground'>
        <Route className='h-4 w-4 text-primary' />
        Tell the staff what you need
      </div>
      <div className='mt-3 grid gap-2 lg:grid-cols-[minmax(0,1fr)_220px_auto]'>
        <input
          value={task}
          onChange={(event) => setTask(event.target.value)}
          placeholder='e.g. Figure out which app can make money fastest and what to do next'
          className='rounded-2xl border border-border bg-background/80 px-4 py-3 text-sm text-foreground outline-none focus:border-primary/60'
        />
        <select
          value={projectId}
          onChange={(event) => setProjectId(event.target.value)}
          className='rounded-2xl border border-border bg-background/80 px-3 py-3 text-sm text-foreground'
        >
          <option value=''>No project yet</option>
          {projects.map((project) => (
            <option key={project.id} value={project.id}>
              {project.name}
            </option>
          ))}
        </select>
        <div className='flex gap-2'>
          <button
            type='button'
            disabled={busy || !task.trim()}
            onClick={() => void route(false)}
            className='rounded-2xl border border-border px-4 py-3 text-xs font-semibold text-foreground hover:border-primary/40 disabled:opacity-50'
          >
            Route
          </button>
          <button
            type='button'
            disabled={busy || !task.trim() || !projectId}
            onClick={() => void route(true)}
            className='rounded-2xl bg-primary px-4 py-3 text-xs font-semibold text-primary-foreground hover:brightness-110 disabled:opacity-50'
          >
            Assign
          </button>
        </div>
      </div>
      {result && (
        <div className='mt-3 flex flex-wrap items-center gap-2 text-xs text-muted-foreground'>
          <span className='rounded-full border border-primary/25 bg-primary/10 px-3 py-1.5 font-medium text-foreground'>
            {result.selected.display_name} · {result.selected.title}
          </span>
          <span>{result.selected.reasons.join(' · ')}</span>
        </div>
      )}
      {message && <p className='mt-2 text-xs leading-5 text-muted-foreground'>{message}</p>}
    </div>
  );
}

function KpiCard({ kpi }: { kpi: StaffKpi }): JSX.Element {
  const tone =
    kpi.status === 'off_track'
      ? 'border-red-400/25 bg-red-500/5'
      : kpi.status === 'watch'
        ? 'border-amber-400/25 bg-amber-500/5'
        : kpi.status === 'on_track'
          ? 'border-emerald-400/25 bg-emerald-500/5'
          : 'border-border bg-background/45';

  return (
    <div className={cn('rounded-2xl border p-4', tone)}>
      <div className='flex items-start justify-between gap-3'>
        <div>
          <p className='text-xs font-semibold text-foreground'>{kpi.name}</p>
          <p className='mt-1 text-[11px] leading-5 text-muted-foreground'>{kpi.description}</p>
        </div>
        <span className='rounded-full border border-border px-2 py-1 text-[10px] capitalize text-muted-foreground'>
          {kpi.status.replaceAll('_', ' ')}
        </span>
      </div>
      <div className='mt-3 flex flex-wrap gap-x-5 gap-y-1 text-[10px] text-muted-foreground'>
        <span>Current: {kpi.current_value ?? 'unknown'} {kpi.current_value !== null ? kpi.unit : ''}</span>
        <span>Period: {kpi.period || 'not set'}</span>
        <span>Source: {kpi.source}</span>
      </div>
    </div>
  );
}

function PermissionRow({ permission }: { permission: StaffPermission }): JSX.Element {
  const tone =
    permission.decision === 'deny'
      ? 'text-red-300'
      : permission.decision === 'ask'
        ? 'text-amber-300'
        : 'text-emerald-300';
  return (
    <div className='rounded-2xl border border-border bg-background/45 p-3'>
      <div className='flex items-center justify-between gap-3'>
        <p className='text-xs font-medium text-foreground'>
          {permission.scope_type} / {permission.scope_id} / {permission.capability}
        </p>
        <span className={cn('text-[10px] font-semibold uppercase tracking-wide', tone)}>
          {permission.decision}
        </span>
      </div>
      {permission.reason && <p className='mt-1 text-[11px] leading-5 text-muted-foreground'>{permission.reason}</p>}
    </div>
  );
}

function TriggerRow({ trigger }: { trigger: StaffTrigger }): JSX.Element {
  return (
    <div className='rounded-2xl border border-border bg-background/45 p-3'>
      <div className='flex items-center justify-between gap-3'>
        <div>
          <p className='text-xs font-medium text-foreground'>{trigger.name}</p>
          <p className='mt-1 text-[11px] capitalize text-muted-foreground'>{trigger.trigger_type}</p>
        </div>
        <span
          className={cn(
            'rounded-full border px-2 py-1 text-[10px]',
            trigger.enabled
              ? 'border-emerald-400/25 bg-emerald-500/10 text-emerald-300'
              : 'border-border text-muted-foreground'
          )}
        >
          {trigger.enabled ? 'Enabled' : 'Stored · off'}
        </span>
      </div>
      <p className='mt-2 text-[11px] leading-5 text-muted-foreground'>{trigger.prompt_md}</p>
    </div>
  );
}

function ChannelRow({ channel }: { channel: StaffChannelConnection }): JSX.Element {
  return (
    <div className='flex items-center justify-between rounded-2xl border border-border bg-background/45 px-3 py-2.5 text-xs'>
      <div>
        <p className='capitalize text-foreground'>{channel.channel}</p>
        {channel.account_label && <p className='text-[10px] text-muted-foreground'>{channel.account_label}</p>}
      </div>
      <span
        className={cn(
          'text-[10px] font-medium capitalize',
          channel.status === 'connected'
            ? 'text-emerald-300'
            : channel.status === 'error'
              ? 'text-red-300'
              : 'text-muted-foreground'
        )}
      >
        {channel.status}
      </span>
    </div>
  );
}

function MemoryCard({ memory }: { memory: StaffMemory }): JSX.Element {
  return (
    <div className='rounded-2xl border border-border bg-background/45 p-4'>
      <div className='flex items-start justify-between gap-3'>
        <div>
          <div className='flex items-center gap-2'>
            <p className='text-xs font-semibold text-foreground'>{memory.title}</p>
            {memory.pinned && <BadgeCheck className='h-3.5 w-3.5 text-primary' />}
          </div>
          <p className='mt-1 text-[10px] uppercase tracking-[0.12em] text-muted-foreground'>
            {memory.kind} · importance {memory.importance}/5
          </p>
        </div>
        <span className='text-[10px] text-muted-foreground'>{memory.source}</span>
      </div>
      <p className='mt-3 text-xs leading-6 text-muted-foreground'>{memory.body_md}</p>
      {memory.tags.length > 0 && (
        <div className='mt-3 flex flex-wrap gap-1.5'>
          {memory.tags.map((tag) => (
            <span key={tag} className='rounded-full bg-accent px-2 py-1 text-[10px] text-foreground'>
              {tag}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function EventRow({ event }: { event: StaffEvent }): JSX.Element {
  const icon =
    event.severity === 'success' ? (
      <CheckCircle2 className='h-4 w-4 text-emerald-300' />
    ) : event.action_required ? (
      <BellRing className='h-4 w-4 text-amber-300' />
    ) : (
      <Activity className='h-4 w-4 text-primary' />
    );

  return (
    <div className='flex gap-3 rounded-2xl border border-border bg-background/45 p-3'>
      <div className='mt-0.5'>{icon}</div>
      <div className='min-w-0 flex-1'>
        <div className='flex items-center justify-between gap-3'>
          <p className='text-xs font-medium text-foreground'>{event.title}</p>
          <span className='text-[10px] uppercase tracking-wide text-muted-foreground'>{event.severity}</span>
        </div>
        {event.body_md && <p className='mt-1 text-[11px] leading-5 text-muted-foreground'>{event.body_md}</p>}
      </div>
    </div>
  );
}

function ProfilePanel({
  profile,
  dashboard,
  assets,
  staff,
  projects,
  onAvatarChanged,
  onChanged,
}: {
  profile: StaffProfile;
  dashboard: StaffDashboard;
  assets: StaffAvatarAsset[];
  staff: StaffMember[];
  projects: ProjectOption[];
  onAvatarChanged: (asset: StaffAvatarAsset) => void;
  onChanged: () => void;
}): JSX.Element {
  const [pickerOpen, setPickerOpen] = useState(false);
  const [callOpen, setCallOpen] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);
  const [section, setSection] = useState<StaffSection>('overview');
  const [memoryOpen, setMemoryOpen] = useState(false);
  const [memoryTitle, setMemoryTitle] = useState('');
  const [memoryBody, setMemoryBody] = useState('');
  const [savingMemory, setSavingMemory] = useState(false);

  const person = profile.staff;
  const personality = profile.personality as
    | { name?: string; blurb?: string; traits?: string[] }
    | null;
  const staffById = useMemo(() => new Map(staff.map((member) => [member.id, member])), [staff]);

  async function pickAvatar(asset: StaffAvatarAsset): Promise<void> {
    await updateStaff(person.id, { avatar_asset_id: asset.id } as Partial<StaffMember>);
    setPickerOpen(false);
    onAvatarChanged(asset);
  }

  async function saveMemory(): Promise<void> {
    if (!memoryTitle.trim() || savingMemory) return;
    setSavingMemory(true);
    try {
      await createStaffMemory(person.id, {
        kind: 'observation',
        title: memoryTitle.trim(),
        body_md: memoryBody.trim(),
        importance: 3,
        source: 'owner',
      });
      setMemoryTitle('');
      setMemoryBody('');
      setMemoryOpen(false);
      onChanged();
    } finally {
      setSavingMemory(false);
    }
  }

  const knownKpis = dashboard.kpis.filter((item) => item.status !== 'unknown').length;
  const enabledTriggers = dashboard.triggers.filter((item) => item.enabled).length;

  return (
    <>
      <article className='overflow-hidden rounded-[32px] border border-border bg-card/75 shadow-[0_26px_90px_rgba(0,0,0,.22)]'>
        <div className='relative border-b border-border bg-[radial-gradient(circle_at_20%_0%,rgba(88,101,242,.24),transparent_38%),radial-gradient(circle_at_90%_15%,rgba(14,165,233,.18),transparent_34%)] px-5 pb-6 pt-7 sm:px-7'>
          <div className='absolute right-5 top-5'>
            <StatusPill status={person.status} />
          </div>

          <div className='flex flex-col gap-5 sm:flex-row sm:items-end'>
            <AvatarBadge asset={profile.avatar} name={person.display_name} size='xl' onClick={() => setPickerOpen(true)} />
            <div className='min-w-0 pb-1'>
              <p className='text-xs font-medium uppercase tracking-[0.22em] text-primary'>My AI staff</p>
              <h1 className='mt-1 text-3xl font-semibold tracking-tight text-foreground'>{person.display_name}</h1>
              <p className='mt-1 text-sm font-medium text-primary'>
                @{person.handle} · {person.title}
              </p>
              <p className='mt-3 max-w-2xl text-sm leading-6 text-muted-foreground'>{person.status_line}</p>
              <div className='mt-4 flex flex-wrap gap-2'>
                <button
                  type='button'
                  onClick={() => setChatOpen(true)}
                  className='inline-flex items-center gap-2 rounded-2xl bg-emerald-500/15 px-4 py-2.5 text-sm font-semibold text-emerald-300 ring-1 ring-inset ring-emerald-400/25 hover:bg-emerald-500/20'
                >
                  <MessageCircle className='h-4 w-4' />
                  Talk to {person.display_name}
                </button>
                <button
                  type='button'
                  onClick={() => setCallOpen(true)}
                  className='inline-flex items-center gap-2 rounded-2xl bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground shadow-[0_12px_35px_rgba(59,130,246,.22)] hover:brightness-110'
                >
                  <BriefcaseBusiness className='h-4 w-4' />
                  Call in {person.display_name}
                </button>
                <button
                  type='button'
                  onClick={() => setPickerOpen(true)}
                  className='inline-flex items-center gap-2 rounded-2xl border border-border bg-background/45 px-4 py-2.5 text-sm font-medium text-foreground hover:border-primary/40'
                >
                  <WandSparkles className='h-4 w-4 text-primary' />
                  Change badge
                </button>
              </div>
            </div>
          </div>

          <div className='mt-6 grid gap-2 sm:grid-cols-4'>
            {[
              ['Responsibilities', dashboard.responsibilities.length],
              ['KPIs with evidence', knownKpis + '/' + dashboard.kpis.length],
              ['Memories', dashboard.memories.length],
              ['Live triggers', enabledTriggers],
            ].map(([label, value]) => (
              <div key={String(label)} className='rounded-2xl border border-white/10 bg-black/15 px-3 py-2.5 backdrop-blur'>
                <p className='text-[10px] uppercase tracking-[0.12em] text-muted-foreground'>{label}</p>
                <p className='mt-1 text-sm font-semibold text-foreground'>{value}</p>
              </div>
            ))}
          </div>
        </div>

        <div className='border-b border-border px-4 py-3 sm:px-6'>
          <div className='flex gap-2 overflow-x-auto'>
            {([
              ['overview', 'Profile'],
              ['kpis', 'KPIs'],
              ['memory', 'Memory'],
              ['permissions', 'Permissions'],
              ['automation', 'Automation'],
              ['activity', 'Activity'],
            ] as Array<[StaffSection, string]>).map(([id, label]) => (
              <button
                key={id}
                type='button'
                onClick={() => setSection(id)}
                className={cn(
                  'shrink-0 rounded-xl px-3 py-2 text-xs font-medium transition',
                  section === id
                    ? 'bg-primary/15 text-primary'
                    : 'text-muted-foreground hover:bg-accent hover:text-foreground'
                )}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        <div className='p-5 sm:p-7'>
          {section === 'overview' && (
            <div className='grid gap-5 xl:grid-cols-[1.15fr_.85fr]'>
              <div className='space-y-5'>
                <section className='rounded-3xl border border-border bg-background/40 p-5'>
                  <div className='flex items-center gap-2 text-sm font-semibold text-foreground'>
                    <Bot className='h-4 w-4 text-primary' />
                    About {person.display_name}
                  </div>
                  <p className='mt-3 text-sm leading-7 text-muted-foreground'>{person.about_md || person.bio}</p>
                </section>

                {person.handle === 'maya' && (
                  <MayaGrowthReviewPanel onRecorded={onChanged} />
                )}
                {person.handle === 'maya' && <MayaExecutionPanel />}

                <section className='rounded-3xl border border-border bg-background/40 p-5'>
                  <div className='flex items-center gap-2 text-sm font-semibold text-foreground'>
                    <BriefcaseBusiness className='h-4 w-4 text-primary' />
                    Responsibilities
                  </div>
                  <div className='mt-3 grid gap-2'>
                    {dashboard.responsibilities.map((item) => (
                      <div key={item.id} className='rounded-2xl border border-border/70 bg-card/50 p-3'>
                        <div className='flex items-center justify-between gap-3'>
                          <p className='text-xs font-semibold text-foreground'>{item.title}</p>
                          <span className='text-[10px] capitalize text-muted-foreground'>
                            {item.priority} · {item.cadence || 'ongoing'}
                          </span>
                        </div>
                        <p className='mt-1 text-[11px] leading-5 text-muted-foreground'>{item.description}</p>
                      </div>
                    ))}
                  </div>
                </section>

                <section className='rounded-3xl border border-border bg-background/40 p-5'>
                  <div className='flex items-center gap-2 text-sm font-semibold text-foreground'>
                    <Goal className='h-4 w-4 text-primary' />
                    Goals
                  </div>
                  <div className='mt-3 space-y-2'>
                    {person.goals.map((goal) => (
                      <div key={goal} className='flex gap-3 rounded-2xl border border-border/70 bg-card/50 p-3'>
                        <Target className='mt-0.5 h-4 w-4 shrink-0 text-primary' />
                        <p className='text-xs leading-5 text-muted-foreground'>{goal}</p>
                      </div>
                    ))}
                  </div>
                </section>

                <section className='rounded-3xl border border-border bg-background/40 p-5'>
                  <div className='flex items-center gap-2 text-sm font-semibold text-foreground'>
                    <Activity className='h-4 w-4 text-primary' />
                    Recent work
                  </div>
                  <div className='mt-3 space-y-2'>
                    {profile.recent_work.length === 0 ? (
                      <p className='rounded-2xl border border-dashed border-border p-4 text-xs text-muted-foreground'>
                        No assignments yet. Staff-owned work will appear here with its persistent identity.
                      </p>
                    ) : (
                      profile.recent_work.slice(0, 6).map((item) => (
                        <div key={item.id} className='rounded-2xl border border-border/70 bg-card/50 p-3'>
                          <div className='flex items-center justify-between gap-3'>
                            <p className='text-xs font-medium text-foreground'>{item.title}</p>
                            <span className='text-[10px] uppercase tracking-wide text-muted-foreground'>{item.status}</span>
                          </div>
                          {item.summary_md && <p className='mt-1 line-clamp-2 text-xs leading-5 text-muted-foreground'>{item.summary_md}</p>}
                        </div>
                      ))
                    )}
                  </div>
                </section>
              </div>

              <aside className='space-y-4'>
                <section className='rounded-3xl border border-border bg-background/45 p-4'>
                  <p className='text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground'>Profile</p>
                  <div className='mt-3 space-y-3 text-xs'>
                    <div className='flex items-start gap-3'>
                      <BriefcaseBusiness className='mt-0.5 h-4 w-4 text-primary' />
                      <div>
                        <p className='font-medium text-foreground'>{person.title}</p>
                        <p className='text-muted-foreground'>Role: {person.role_template_id}</p>
                      </div>
                    </div>
                    <div className='flex items-start gap-3'>
                      <WandSparkles className='mt-0.5 h-4 w-4 text-primary' />
                      <div>
                        <p className='font-medium text-foreground'>{personality?.name ?? 'Balanced default'}</p>
                        <p className='text-muted-foreground'>{personality?.blurb ?? 'No special personality layer.'}</p>
                      </div>
                    </div>
                    <div className='flex items-start gap-3'>
                      <ShieldCheck className='mt-0.5 h-4 w-4 text-primary' />
                      <div>
                        <p className='font-medium capitalize text-foreground'>{person.authority_policy.replaceAll('_', ' ')}</p>
                        <p className='text-muted-foreground'>The worker launcher enforces this boundary.</p>
                      </div>
                    </div>
                  </div>
                </section>

                <section className='rounded-3xl border border-border bg-background/45 p-4'>
                  <p className='text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground'>Personality</p>
                  <div className='mt-3 flex flex-wrap gap-2'>
                    {(personality?.traits ?? []).map((trait) => (
                      <span key={trait} className='rounded-full bg-accent px-2.5 py-1 text-[11px] text-foreground'>
                        {trait}
                      </span>
                    ))}
                  </div>
                  <div className='mt-3 flex flex-wrap gap-2'>
                    {person.specialties.map((specialty) => (
                      <span key={specialty} className='rounded-full border border-primary/20 bg-primary/10 px-2.5 py-1 text-[11px] text-foreground'>
                        {specialty}
                      </span>
                    ))}
                  </div>
                </section>

                <section className='rounded-3xl border border-border bg-background/45 p-4'>
                  <div className='flex items-center gap-2 text-sm font-semibold text-foreground'>
                    <Network className='h-4 w-4 text-primary' />
                    Top people
                  </div>
                  <p className='mt-1 text-[11px] text-muted-foreground'>Who this person collaborates with or delegates to.</p>
                  <div className='mt-3 grid grid-cols-2 gap-2'>
                    {dashboard.relationships.length === 0 ? (
                      <p className='col-span-2 text-xs text-muted-foreground'>No staff relationships yet.</p>
                    ) : (
                      dashboard.relationships.slice(0, 6).map((relation) => {
                        const otherId =
                          relation.from_staff_id === person.id
                            ? relation.to_staff_id
                            : relation.from_staff_id;
                        const other = staffById.get(otherId);
                        return (
                          <div key={relation.from_staff_id + relation.to_staff_id + relation.relationship} className='rounded-2xl border border-border bg-card/50 p-3'>
                            <p className='text-xs font-medium text-foreground'>{other?.display_name ?? 'Staff'}</p>
                            <p className='mt-1 text-[10px] capitalize text-primary'>{relation.relationship.replaceAll('_', ' ')}</p>
                          </div>
                        );
                      })
                    )}
                  </div>
                </section>

                <section className='rounded-3xl border border-border bg-background/45 p-4'>
                  <div className='flex items-center gap-2 text-sm font-semibold text-foreground'>
                    <MessageCircle className='h-4 w-4 text-primary' />
                    Contact
                  </div>
                  <div className='mt-3 space-y-2'>
                    {dashboard.channels.map((channel) => (
                      <ChannelRow key={channel.id} channel={channel} />
                    ))}
                  </div>
                </section>

                <section className='rounded-3xl border border-primary/25 bg-primary/10 p-4'>
                  <div className='flex items-center gap-2 text-sm font-semibold text-foreground'>
                    <BadgeCheck className='h-4 w-4 text-primary' />
                    Persistent identity
                  </div>
                  <p className='mt-2 text-xs leading-5 text-muted-foreground'>
                    Work launched through this profile keeps {person.display_name}'s role, personality, staff ID, permissions, authority policy, and event history attached.
                  </p>
                </section>
              </aside>
            </div>
          )}

          {section === 'kpis' && (
            <section>
              <div className='flex items-start justify-between gap-4'>
                <div>
                  <div className='flex items-center gap-2 text-sm font-semibold text-foreground'>
                    <Gauge className='h-4 w-4 text-primary' />
                    Performance & KPIs
                  </div>
                  <p className='mt-1 text-xs text-muted-foreground'>
                    Unknown stays unknown until a real source or owner update provides evidence.
                  </p>
                </div>
              </div>
              <div className='mt-4 grid gap-3 lg:grid-cols-2'>
                {dashboard.kpis.map((kpi) => (
                  <KpiCard key={kpi.id} kpi={kpi} />
                ))}
              </div>
            </section>
          )}

          {section === 'memory' && (
            <section>
              <div className='flex items-center justify-between gap-4'>
                <div>
                  <div className='flex items-center gap-2 text-sm font-semibold text-foreground'>
                    <NotebookPen className='h-4 w-4 text-primary' />
                    Staff memory
                  </div>
                  <p className='mt-1 text-xs text-muted-foreground'>
                    Durable decisions, lessons, preferences, and observations specific to this person.
                  </p>
                </div>
                <button
                  type='button'
                  onClick={() => setMemoryOpen((value) => !value)}
                  className='rounded-xl border border-border px-3 py-2 text-xs font-medium text-foreground hover:border-primary/40'
                >
                  Add memory
                </button>
              </div>

              {memoryOpen && (
                <div className='mt-4 rounded-3xl border border-primary/20 bg-primary/5 p-4'>
                  <input
                    value={memoryTitle}
                    onChange={(event) => setMemoryTitle(event.target.value)}
                    placeholder='Memory title'
                    className='w-full rounded-2xl border border-border bg-background px-3 py-2.5 text-sm text-foreground outline-none focus:border-primary/50'
                  />
                  <textarea
                    value={memoryBody}
                    onChange={(event) => setMemoryBody(event.target.value)}
                    rows={3}
                    placeholder='What should this staff member remember?'
                    className='mt-2 w-full resize-none rounded-2xl border border-border bg-background px-3 py-2.5 text-sm text-foreground outline-none focus:border-primary/50'
                  />
                  <button
                    type='button'
                    disabled={!memoryTitle.trim() || savingMemory}
                    onClick={() => void saveMemory()}
                    className='mt-2 rounded-xl bg-primary px-4 py-2 text-xs font-semibold text-primary-foreground disabled:opacity-50'
                  >
                    {savingMemory ? 'Saving...' : 'Save to staff memory'}
                  </button>
                </div>
              )}

              <div className='mt-4 grid gap-3 lg:grid-cols-2'>
                {dashboard.memories.length === 0 ? (
                  <div className='rounded-2xl border border-dashed border-border p-5 text-xs text-muted-foreground'>
                    No durable memories yet.
                  </div>
                ) : (
                  dashboard.memories.map((memory) => <MemoryCard key={memory.id} memory={memory} />)
                )}
              </div>
            </section>
          )}

          {section === 'permissions' && (
            <section>
              <div className='flex items-center gap-2 text-sm font-semibold text-foreground'>
                <ShieldCheck className='h-4 w-4 text-primary' />
                Authority & permissions
              </div>
              <p className='mt-1 text-xs text-muted-foreground'>
                These rules are separate from personality. They define what this staff identity may do, must ask for, or is denied.
              </p>
              <div className='mt-4 grid gap-3 lg:grid-cols-2'>
                {dashboard.permissions.map((permission) => (
                  <PermissionRow key={permission.id} permission={permission} />
                ))}
              </div>
            </section>
          )}

          {section === 'automation' && (
            <div className='grid gap-5 lg:grid-cols-[1.2fr_.8fr]'>
              <section>
                <div className='flex items-center gap-2 text-sm font-semibold text-foreground'>
                  <Zap className='h-4 w-4 text-primary' />
                  Schedules & triggers
                </div>
                <p className='mt-1 text-xs text-muted-foreground'>
                  Seeded automation ideas remain off until a real scheduler owns execution. No fake background work.
                </p>
                <div className='mt-4 space-y-3'>
                  {dashboard.triggers.map((trigger) => (
                    <TriggerRow key={trigger.id} trigger={trigger} />
                  ))}
                </div>
              </section>
              <section>
                <div className='flex items-center gap-2 text-sm font-semibold text-foreground'>
                  <Link2 className='h-4 w-4 text-primary' />
                  Communication channels
                </div>
                <p className='mt-1 text-xs text-muted-foreground'>
                  Connection state is shown exactly as it exists.
                </p>
                <div className='mt-4 space-y-2'>
                  {dashboard.channels.map((channel) => (
                    <ChannelRow key={channel.id} channel={channel} />
                  ))}
                </div>
              </section>
            </div>
          )}

          {section === 'activity' && (
            <section>
              <div className='flex items-center gap-2 text-sm font-semibold text-foreground'>
                <Activity className='h-4 w-4 text-primary' />
                Evidence & activity
              </div>
              <p className='mt-1 text-xs text-muted-foreground'>
                Owner-visible staff events and assignment receipts accumulate here.
              </p>
              <div className='mt-4 space-y-2'>
                {dashboard.events.length === 0 ? (
                  <div className='rounded-2xl border border-dashed border-border p-5 text-xs text-muted-foreground'>
                    No staff events recorded yet.
                  </div>
                ) : (
                  dashboard.events.map((event) => <EventRow key={event.id} event={event} />)
                )}
              </div>
            </section>
          )}
        </div>
      </article>

      {pickerOpen && (
        <AvatarPicker
          assets={assets}
          selectedId={person.avatar_asset_id}
          onPick={(asset) => void pickAvatar(asset)}
          onClose={() => setPickerOpen(false)}
        />
      )}
      {callOpen && (
        <CallInModal
          person={person}
          projects={projects}
          onClose={() => setCallOpen(false)}
          onAssigned={onChanged}
        />
      )}
      {chatOpen && (
        <StaffChatModal
          person={person}
          asset={profile.avatar}
          onClose={() => setChatOpen(false)}
        />
      )}
    </>
  );
}

export function StaffPage(): JSX.Element {
  const [staff, setStaff] = useState<StaffMember[]>([]);
  const [assets, setAssets] = useState<StaffAvatarAsset[]>([]);
  const [projects, setProjects] = useState<ProjectOption[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [profile, setProfile] = useState<StaffProfile | null>(null);
  const [dashboard, setDashboard] = useState<StaffDashboard | null>(null);
  const [briefing, setBriefing] = useState<StaffBriefing | null>(null);
  const [briefingOpen, setBriefingOpen] = useState(false);
  const [councilOpen, setCouncilOpen] = useState(false);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState('');

  const assetsById = useMemo(
    () => new Map(assets.map((asset) => [asset.id, asset])),
    [assets]
  );

  async function loadRoster(): Promise<void> {
    const [staffResult, projectRows] = await Promise.all([listStaff(), listProjects()]);
    setStaff(staffResult.staff);
    setAssets(staffResult.avatar_assets);
    setProjects(projectRows.map((project) => ({ id: project.id, name: project.name })));
    if (!selectedId && staffResult.staff[0]) setSelectedId(staffResult.staff[0].id);
  }

  async function loadSelected(id: string): Promise<void> {
    const [profileResult, dashboardResult] = await Promise.all([
      getStaff(id),
      getStaffDashboard(id),
    ]);
    setProfile(profileResult);
    setDashboard(dashboardResult);
  }

  async function refreshAll(): Promise<void> {
    await loadRoster();
    if (selectedId) await loadSelected(selectedId);
  }

  useEffect(() => {
    let active = true;
    void Promise.all([listStaff(), listProjects()])
      .then(([staffResult, projectRows]) => {
        if (!active) return;
        setStaff(staffResult.staff);
        setAssets(staffResult.avatar_assets);
        setProjects(projectRows.map((project) => ({ id: project.id, name: project.name })));
        setSelectedId(staffResult.staff[0]?.id ?? null);
      })
      .catch((err: unknown) => {
        if (active) setError(err instanceof Error ? err.message : 'Could not load AI staff.');
      })
      .finally(() => {
        if (active) setBusy(false);
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!selectedId) {
      setProfile(null);
      setDashboard(null);
      return;
    }
    let active = true;
    void Promise.all([getStaff(selectedId), getStaffDashboard(selectedId)])
      .then(([profileResult, dashboardResult]) => {
        if (!active) return;
        setProfile(profileResult);
        setDashboard(dashboardResult);
      })
      .catch((err: unknown) => {
        if (active) setError(err instanceof Error ? err.message : 'Could not open staff profile.');
      });
    return () => {
      active = false;
    };
  }, [selectedId]);

  async function openBriefing(): Promise<void> {
    try {
      const result = await getStaffBriefing();
      setBriefing(result);
      setBriefingOpen(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load staff briefing.');
    }
  }

  function onAvatarChanged(asset: StaffAvatarAsset): void {
    if (!profile) return;
    setProfile({
      ...profile,
      staff: { ...profile.staff, avatar_asset_id: asset.id },
      avatar: asset,
    });
    setStaff((current) =>
      current.map((member) =>
        member.id === profile.staff.id ? { ...member, avatar_asset_id: asset.id } : member
      )
    );
  }

  return (
    <div className='mx-auto w-full max-w-[1500px] px-4 py-5 sm:px-6 sm:py-7'>
      <header className='mb-5 flex flex-col justify-between gap-4 xl:flex-row xl:items-end'>
        <div>
          <div className='flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.2em] text-primary'>
            <Sparkles className='h-4 w-4' />
            Your people
          </div>
          <h1 className='mt-2 text-2xl font-semibold tracking-tight text-foreground'>My AI Staff</h1>
          <p className='mt-1 max-w-3xl text-sm text-muted-foreground'>
            Persistent people with roles, personalities, badges, goals, memory, permissions, KPIs, evidence, and their own work history.
          </p>
        </div>
        <div className='flex flex-wrap gap-2'>
          <button
            type='button'
            onClick={() => void openBriefing()}
            className='inline-flex items-center gap-2 rounded-2xl border border-border bg-card/70 px-4 py-2.5 text-xs font-semibold text-foreground hover:border-primary/35'
          >
            <Gauge className='h-4 w-4 text-primary' />
            What should I do?
          </button>
          <button
            type='button'
            onClick={() => setCouncilOpen(true)}
            className='inline-flex items-center gap-2 rounded-2xl bg-primary px-4 py-2.5 text-xs font-semibold text-primary-foreground hover:brightness-110'
          >
            <UsersRound className='h-4 w-4' />
            Ask the team
          </button>
          <div className='rounded-2xl border border-border bg-card/60 px-4 py-2.5 text-xs text-muted-foreground'>
            {staff.length} staff profile{staff.length === 1 ? '' : 's'}
          </div>
        </div>
      </header>

      <QuickRouteBar projects={projects} onAssigned={() => void refreshAll()} />

      {profile && (
        <div className='mt-5'>
          <div className='mb-2 flex items-center justify-between gap-3'>
            <div>
              <p className='text-sm font-semibold text-foreground'>Live staff chat</p>
              <p className='text-xs text-muted-foreground'>Talk directly to the selected person while the rest of their staff system keeps evolving.</p>
            </div>
          </div>
          <StaffChatPanel
            staffId={profile.staff.id}
            name={profile.staff.display_name}
            title={profile.staff.title}
            avatar={profile.avatar}
          />
        </div>
      )}

      {error && (
        <div className='my-4 rounded-2xl border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive'>
          {error}
        </div>
      )}

      {busy ? (
        <div className='mt-5 rounded-3xl border border-border bg-card/60 p-8 text-sm text-muted-foreground'>
          Loading your staff...
        </div>
      ) : (
        <div className='mt-5 grid gap-5 lg:grid-cols-[300px_minmax(0,1fr)]'>
          <aside className='space-y-3'>
            <div className='rounded-3xl border border-border bg-card/70 p-3'>
              <div className='mb-3 flex items-center justify-between px-1'>
                <p className='text-xs font-semibold text-foreground'>People</p>
                <span className='text-[10px] text-muted-foreground'>Click a profile</span>
              </div>
              <div className='space-y-2'>
                {staff.map((member) => (
                  <StaffCard
                    key={member.id}
                    member={member}
                    asset={
                      member.avatar_asset_id
                        ? assetsById.get(member.avatar_asset_id)
                        : undefined
                    }
                    selected={selectedId === member.id}
                    onClick={() => setSelectedId(member.id)}
                  />
                ))}
              </div>
            </div>

            <div className='rounded-3xl border border-dashed border-border bg-card/30 p-4 text-xs leading-5 text-muted-foreground'>
              <p className='font-medium text-foreground'>Profile badges</p>
              <p className='mt-1'>
                Click a person's big badge to choose from the Synapse asset catalog. The asset layer is separate from role and personality, so appearance can change without changing how the person works.
              </p>
            </div>
          </aside>

          <main className='min-w-0'>
            {profile && dashboard ? (
              <ProfilePanel
                profile={profile}
                dashboard={dashboard}
                assets={assets}
                staff={staff}
                projects={projects}
                onAvatarChanged={onAvatarChanged}
                onChanged={() => void refreshAll()}
              />
            ) : (
              <div className='grid min-h-[480px] place-items-center rounded-3xl border border-dashed border-border text-sm text-muted-foreground'>
                <span>
                  <ChevronLeft className='mr-2 inline h-4 w-4' />
                  Choose a staff profile.
                </span>
              </div>
            )}
          </main>
        </div>
      )}

      {briefingOpen && briefing && (
        <BriefingModal briefing={briefing} onClose={() => setBriefingOpen(false)} />
      )}
      {councilOpen && (
        <CouncilModal
          projects={projects}
          onClose={() => setCouncilOpen(false)}
          onCreated={() => void refreshAll()}
        />
      )}
    </div>
  );
}
