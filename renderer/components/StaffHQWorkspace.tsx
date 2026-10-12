import { useCallback, useEffect, useRef, useState } from 'react';
import {
  ArrowRight, Camera, CameraOff, CheckCircle2, CircleAlert, Clapperboard,
  DollarSign, ExternalLink, Lightbulb, MessageCircle, Mic, MonitorUp,
  ShieldCheck, Sparkles, Square, UsersRound, Video, Wallet,
} from 'lucide-react';
import {
  createStaffCouncil, createStaffMemory, getStaffBriefing, getStaffDashboard,
  listStaff, sendStaffChat, setStaffTriggerEnabled, summonStaff, updateStaff, type StaffBriefing, type StaffDashboard,
  type StaffMember,
} from '../lib/staff-client';
import { listProjects } from '../lib/projects-client';
import { ObsScenePanel } from './StaffHQObs';

type Area = 'team' | 'creator' | 'money' | 'coordination';
const ROLES: Record<string, string> = {
  maya: 'Revenue', lena: 'Money', adrian: 'Money', jordan: 'Revenue',
  riley: 'Revenue', eli: 'Creator', nova: 'Creator', zoe: 'Creator',
  iris: 'Creator', sofia: 'Creator', felix: 'Revenue',
  tess: 'Operations', marcus: 'Operations', sam: 'Revenue',
};
const classPanel = 'rounded-3xl border border-border bg-card/80 p-4 sm:p-5';
const classButton = 'rounded-xl border border-border bg-background/60 px-3 py-2 text-sm font-medium transition hover:border-primary/40 hover:bg-primary/10 disabled:cursor-not-allowed disabled:opacity-50';

function readError(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function CameraWorkspace(): JSX.Element {
  const camera = useRef<HTMLVideoElement>(null);
  const screen = useRef<HTMLVideoElement>(null);
  const cameraStream = useRef<MediaStream | null>(null);
  const screenStream = useRef<MediaStream | null>(null);
  const [cameraOn, setCameraOn] = useState(false);
  const [screenOn, setScreenOn] = useState(false);
  const [error, setError] = useState('');

  const stopCamera = useCallback(() => {
    cameraStream.current?.getTracks().forEach(track => track.stop());
    cameraStream.current = null;
    if (camera.current) camera.current.srcObject = null;
    setCameraOn(false);
  }, []);
  const stopScreen = useCallback(() => {
    screenStream.current?.getTracks().forEach(track => track.stop());
    screenStream.current = null;
    if (screen.current) screen.current.srcObject = null;
    setScreenOn(false);
  }, []);

  useEffect(() => () => {
    cameraStream.current?.getTracks().forEach(track => track.stop());
    screenStream.current?.getTracks().forEach(track => track.stop());
  }, []);

  async function toggleCamera(): Promise<void> {
    setError('');
    if (cameraStream.current) { stopCamera(); return; }
    if (!navigator.mediaDevices?.getUserMedia) { setError('This browser does not support camera capture in this context.'); return; }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
      cameraStream.current = stream;
      if (camera.current) { camera.current.srcObject = stream; void camera.current.play().catch(() => undefined); }
      stream.getVideoTracks().forEach(track => { track.onended = stopCamera; });
      setCameraOn(true);
    } catch (e) { setError('Camera permission was not granted: ' + readError(e)); }
  }

  async function toggleScreen(): Promise<void> {
    setError('');
    if (screenStream.current) { stopScreen(); return; }
    if (!navigator.mediaDevices?.getDisplayMedia) { setError('Screen sharing is not available in this browser.'); return; }
    try {
      const stream = await navigator.mediaDevices.getDisplayMedia({ video: true, audio: false });
      screenStream.current = stream;
      if (screen.current) { screen.current.srcObject = stream; void screen.current.play().catch(() => undefined); }
      stream.getVideoTracks().forEach(track => { track.onended = stopScreen; });
      setScreenOn(true);
    } catch (e) { setError('Screen sharing was not started: ' + readError(e)); }
  }

  return (
    <section className={classPanel}>
      <div className='mb-4 flex flex-wrap items-start justify-between gap-3'>
        <div>
          <h3 className='flex items-center gap-2 text-base font-semibold'><Video className='h-4 w-4 text-primary'/> Eli's Creator Cockpit</h3>
          <p className='mt-1 max-w-xl text-xs leading-5 text-muted-foreground'>Permission-controlled previews for planning a stream. Video stays on this device. Eli cannot analyze these feeds yet; connecting AI vision, OBS and streaming controls requires a separate verified integration.</p>
        </div>
        <span className='rounded-lg border border-amber-500/30 bg-amber-500/10 px-2 py-1 text-[11px] text-amber-300'>Local preview only</span>
      </div>
      <div className='grid gap-3 sm:grid-cols-2'>
        <div className='overflow-hidden rounded-2xl border border-border bg-black/80'>
          <div className='relative aspect-video'>
            <video ref={camera} muted playsInline autoPlay className='h-full w-full object-contain'/>
            {!cameraOn && <div className='absolute inset-0 grid place-content-center text-center text-sm text-slate-400'><CameraOff className='mx-auto mb-2 h-7 w-7'/>Camera off</div>}
          </div>
          <div className='flex items-center justify-between bg-card p-3'>
            <span className='text-xs text-muted-foreground'>Camera · {cameraOn ? 'sharing locally' : 'off'}</span>
            <button type='button' className={classButton} onClick={() => void toggleCamera()}>{cameraOn ? 'Stop camera' : 'Enable camera'}</button>
          </div>
        </div>
        <div className='overflow-hidden rounded-2xl border border-border bg-black/80'>
          <div className='relative aspect-video'>
            <video ref={screen} muted playsInline autoPlay className='h-full w-full object-contain'/>
            {!screenOn && <div className='absolute inset-0 grid place-content-center text-center text-sm text-slate-400'><MonitorUp className='mx-auto mb-2 h-7 w-7'/>Screen not shared</div>}
          </div>
          <div className='flex items-center justify-between bg-card p-3'>
            <span className='text-xs text-muted-foreground'>Screen · {screenOn ? 'sharing locally' : 'off'}</span>
            <button type='button' className={classButton} onClick={() => void toggleScreen()}>{screenOn ? 'Stop sharing' : 'Share screen'}</button>
          </div>
        </div>
      </div>
      <div className='mt-3 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-background/50 p-3'>
        <p className='text-xs text-muted-foreground'><ShieldCheck className='mr-1 inline h-3.5 w-3.5'/> Microphone is never started by these previews. No recording, streaming or AI upload occurs here.</p>
        {(cameraOn || screenOn) && <button type='button' onClick={() => { stopCamera(); stopScreen(); }} className={classButton}><Square className='mr-1 inline h-3 w-3'/>Stop all capture</button>}
      </div>
      {error && <p role='alert' className='mt-2 text-sm text-red-400'>{error}</p>}
      <div className='mt-4 grid gap-2 text-xs text-muted-foreground sm:grid-cols-3'>
        {['OBS scenes · connect below','AI live vision/voice · not connected','Clip marking and edit queue · planned'].map(text => <div key={text} className='rounded-xl border border-dashed border-border p-3'>{text}</div>)}
      </div>
    </section>
  );
}

function CreatorMomentsPanel(): JSX.Element {
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [note, setNote] = useState('');
  const [moments, setMoments] = useState<Array<{ at: string; note: string }>>([]);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState('');

  function startSession(): void {
    setStartedAt(Date.now());
    setMoments([]);
    setNote('');
    setResult('Session clock started. This does not start OBS recording or capture media.');
  }

  async function markMoment(): Promise<void> {
    if (busy || !startedAt || !note.trim()) return;
    const elapsedSeconds = Math.floor((Date.now() - startedAt) / 1000);
    const at = [Math.floor(elapsedSeconds / 3600), Math.floor(elapsedSeconds % 3600 / 60), elapsedSeconds % 60]
      .map(n => String(n).padStart(2, '0')).join(':');
    const details = note.trim();
    setBusy(true); setResult('');
    try {
      await createStaffMemory('nova', {
        kind: 'observation',
        title: 'Creator moment at ' + at,
        body_md: 'Owner-marked content candidate. Relative session timestamp: ' + at +
          '. Note: ' + details + '. This is not proof of a recording, existing clip or an uploaded video.',
        tags: ['creator-session', 'clip-candidate'],
        importance: 5,
        source: 'staff-hq-owner',
      });
      setMoments(current => [...current, { at, note: details }]);
      setNote('');
      setResult('Moment saved to Nova’s Synapse memory. No footage was uploaded.');
    } catch (e) { setResult('Could not save this moment: ' + readError(e)); }
    finally { setBusy(false); }
  }

  function exportNotes(): void {
    const text = [
      'Synapse Staff HQ — creator session markers',
      'Timecodes are relative to Start session clock, not OBS recording.',
      ...moments.map(item => item.at + ' — ' + item.note),
    ].join('\n');
    const url = URL.createObjectURL(new Blob([text], { type: 'text/plain' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = 'synapse-creator-moments.txt';
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 10_000);
  }

  return <section className={classPanel}>
    <h3 className='flex items-center gap-2 font-semibold'><Clapperboard className='h-4 w-4 text-primary'/> Moments for Nova</h3>
    <p className='mt-1 text-xs leading-5 text-muted-foreground'>Keep a lightweight session clock and flag interesting moments while OBS or another recorder runs separately. Saved notes go into Nova’s real Synapse memory. This does not record video or send a stream.</p>
    <div className='mt-3 flex flex-wrap gap-2'>
      <button type='button' className={classButton} onClick={startSession}>{startedAt ? 'Restart session clock' : 'Start session clock'}</button>
      {startedAt && <span className='rounded-xl border border-border px-3 py-2 text-xs text-muted-foreground'>Started {new Date(startedAt).toLocaleTimeString()}</span>}
      {moments.length > 0 && <button type='button' className={classButton} onClick={exportNotes}>Download moment notes</button>}
    </div>
    <label className='mt-3 block text-xs text-muted-foreground'>What happened?
      <textarea value={note} onChange={e => setNote(e.target.value)} rows={2} maxLength={500}
        placeholder='Example: Finished an impressive AI feature, demonstrate the before-and-after…'
        className='mt-1 w-full rounded-xl border border-border bg-background p-3 text-sm text-foreground'/>
    </label>
    <button type='button' disabled={!startedAt || !note.trim() || busy} onClick={() => void markMoment()}
      className='mt-2 rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground disabled:opacity-50'>
      {busy ? 'Saving…' : 'Save moment for Nova'}
    </button>
    {result && <p role='status' className='mt-2 text-xs text-muted-foreground'>{result}</p>}
    {moments.length > 0 && <div className='mt-3 space-y-1'>{moments.map((moment, i) =>
      <p key={i} className='text-xs'><span className='mr-2 font-mono text-primary'>{moment.at}</span>{moment.note}</p>
    )}</div>}
  </section>;
}

export function StaffHQWorkspace({ onClassic }: { onClassic?: () => void }): JSX.Element {
  const [area, setArea] = useState<Area>('team');
  const [people, setPeople] = useState<StaffMember[]>([]);
  const [brief, setBrief] = useState<StaffBriefing | null>(null);
  const [selected, setSelected] = useState<string>('maya');
  const [dashboard, setDashboard] = useState<StaffDashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [conversation, setConversation] = useState('');
  const [objective, setObjective] = useState('Make a realistic 30-day plan to earn money from my current businesses.');
  const [project, setProject] = useState('synapse');
  const [projects, setProjects] = useState<Array<{ id: string; name: string }>>([]);
  const [actionResult, setActionResult] = useState('');
  const [staffTask, setStaffTask] = useState('');
  const [staffTaskResult, setStaffTaskResult] = useState('');
  const [voiceAlerts, setVoiceAlerts] = useState(false);
  const seenAlerts = useRef<Set<string> | null>(null);

  const refresh = useCallback(async () => {
    setError('');
    try {
      const [roster, briefing, entries] = await Promise.all([listStaff(), getStaffBriefing(), listProjects()]);
      setPeople(roster.staff); setBrief(briefing);
      setProjects(entries.map(x => ({ id: x.id, name: x.name })));
      setSelected(value => roster.staff.some(p => p.handle === value || p.id === value) ? value : (roster.staff[0]?.id ?? ''));
    } catch (e) { setError(readError(e)); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);
  useEffect(() => {
    const timer = window.setInterval(() => {
      if (document.visibilityState !== 'visible') return;
      void getStaffBriefing().then(setBrief).catch(() => undefined);
    }, 60_000);
    return () => { window.clearInterval(timer); window.speechSynthesis?.cancel(); };
  }, []);

  useEffect(() => {
    if (!brief) return;
    const key = (item: StaffBriefing['attention'][number]) =>
      item.event_id ?? (item.staff_id + ':' + item.title + ':' + item.severity);
    const current = new Set(brief.attention.map(key));
    if (seenAlerts.current !== null && voiceAlerts &&
        document.visibilityState === 'visible' &&
        'speechSynthesis' in window && 'SpeechSynthesisUtterance' in window) {
      const fresh = brief.attention.find(item => !seenAlerts.current?.has(key(item)));
      if (fresh) {
        window.speechSynthesis.cancel();
        const spoken = new SpeechSynthesisUtterance(
          'Synapse staff update: ' + fresh.title.slice(0, 140)
        );
        spoken.rate = 1.04;
        window.speechSynthesis.speak(spoken);
      }
    }
    seenAlerts.current = current;
  }, [brief, voiceAlerts]);
  useEffect(() => {
    let alive = true;
    if (!selected) { setDashboard(null); return; }
    void getStaffDashboard(selected).then(value => { if (alive) setDashboard(value); }).catch(e => { if (alive) setError(readError(e)); });
    return () => { alive = false; };
  }, [selected]);

  const active = people.find(p => p.id === selected || p.handle === selected);
  const filtered = area === 'creator' ? people.filter(p => ROLES[p.handle] === 'Creator')
    : area === 'money' ? people.filter(p => ROLES[p.handle] === 'Money' || p.handle === 'maya')
    : people;

  async function toggleReminder(triggerId: string, enabled: boolean): Promise<void> {
    if (!selected || busy) return;
    setBusy(true); setError('');
    try {
      await setStaffTriggerEnabled(selected, triggerId, enabled);
      setDashboard(await getStaffDashboard(selected));
      await refresh();
    } catch (e) { setError('Could not update review reminder: ' + readError(e)); }
    finally { setBusy(false); }
  }

  async function changeAuthority(value: StaffMember['authority_policy']): Promise<void> {
    if (!active || busy || active.authority_policy === value) return;
    if (value === 'act_within_limits' && !window.confirm(
      'Allow this employee to act in approved project workspaces? This does not grant posting, account, spending or broadcast permissions.'
    )) return;
    setBusy(true); setError('');
    try {
      await updateStaff(active.id, { authority_policy: value });
      await refresh();
      setDashboard(await getStaffDashboard(active.id));
    } catch (e) { setError('Could not change employee authority: ' + readError(e)); }
    finally { setBusy(false); }
  }

  async function assignIndividual(): Promise<void> {
    if (!active || busy || !staffTask.trim() || !project) return;
    setBusy(true); setError(''); setStaffTaskResult('');
    try {
      const created = await summonStaff(active.id, { project_id: project, task: staffTask.trim() });
      setStaffTaskResult('Assignment ' + created.work_item.id + ' prepared under Synapse squad ' + created.squad.id + '. Worker has not been launched.');
      setStaffTask('');
    } catch (e) { setError('Could not prepare staff assignment: ' + readError(e)); }
    finally { setBusy(false); }
  }

  async function chat(): Promise<void> {
    if (!selected || !message.trim() || busy) return;
    setBusy(true); setError('');
    try {
      const reply = await sendStaffChat(selected, message.trim());
      setConversation([conversation, 'You: ' + message.trim(), (active?.display_name ?? 'Staff') + ': ' + reply.assistant_message.content].filter(Boolean).join('\n\n'));
      setMessage('');
    } catch (e) { setError('Staff conversation unavailable: ' + readError(e)); }
    finally { setBusy(false); }
  }

  async function assembleTeam(): Promise<void> {
    if (busy || !objective.trim() || !project) return;
    setBusy(true); setError(''); setActionResult('');
    try {
      const council = await createStaffCouncil({ project_id: project, objective: objective.trim(), max_members: 4 });
      setActionResult('Council created with ' + council.members.map(m => m.display_name).join(', ') + '. Work items are prepared, not launched. Open My AI Staff to supervise or launch them.');
      void refresh();
    } catch (e) { setError('Could not create staff council: ' + readError(e)); }
    finally { setBusy(false); }
  }

  return (
    <div className='mx-auto w-full max-w-[1500px] space-y-5 px-3 py-4 text-foreground sm:px-5 sm:py-6'>
      <header className='flex flex-wrap items-start justify-between gap-3'>
        <div>
          <p className='flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.2em] text-primary'><Sparkles className='h-4 w-4'/> Synapse · Staff Headquarters</p>
          <h1 className='mt-2 text-3xl font-semibold tracking-tight'>Your AI company</h1>
          <p className='mt-2 max-w-2xl text-sm text-muted-foreground'>One shared team for revenue, production and business operations. Profiles, work and memory are backed by Synapse; this view never runs an independent staff database.</p>
        </div>
        <div className='flex flex-wrap items-center gap-2'>
          <button type='button' className={classButton} onClick={() => void refresh()}>Refresh</button>
          <button type='button' className={classButton} onClick={() => {
            setVoiceAlerts(current => !current);
            if ('speechSynthesis' in window) window.speechSynthesis.cancel();
          }} aria-pressed={voiceAlerts} title='Read new in-app staff alerts aloud only while Staff HQ is visible'>
            {voiceAlerts ? 'Voice alerts on' : 'Voice alerts off'}
          </button>
          {onClassic && <button type='button' className={classButton} onClick={onClassic}>Original Staff view</button>}
          <button type='button' className={classButton} onClick={() => {
            const url = new URL(window.location.href);
            url.searchParams.set('staff_hq', '1');
            const popup = window.open(url.toString(), 'synapse-staff-hq', 'width=1360,height=900');
            if (!popup) setError('Pop-out was blocked; open the Staff HQ link from your regular browser instead.');
          }}><ExternalLink className='mr-1 inline h-4 w-4'/>Pop out</button>
        </div>
      </header>

      <div className='grid gap-3 sm:grid-cols-3'>
        <div className={classPanel}><p className='text-xs text-muted-foreground'>AI staff registered</p><p className='mt-1 text-3xl font-bold'>{loading ? '…' : people.length}</p><p className='mt-1 text-xs text-muted-foreground'>Source-backed profiles only</p></div>
        <div className={classPanel}><p className='text-xs text-muted-foreground'>Needs your input</p><p className='mt-1 text-3xl font-bold'>{brief?.counts.attention_items ?? '—'}</p><p className='mt-1 text-xs text-muted-foreground'>Verified alerts / decisions</p></div>
        <div className={classPanel}><p className='text-xs text-muted-foreground'>Active staff work</p><p className='mt-1 text-3xl font-bold'>{brief?.counts.working ?? '—'}</p><p className='mt-1 text-xs text-muted-foreground'>Not estimated or simulated</p></div>
      </div>

      <nav aria-label='Staff HQ areas' className='flex flex-wrap gap-2'>
        {([['team','All staff',UsersRound],['creator','Creator cockpit',Clapperboard],['money','Money desk',Wallet],['coordination','Staff meeting',MessageCircle]] as const).map(([id,label,Icon]) =>
          <button key={id} type='button' onClick={() => setArea(id)} className={area === id ? 'rounded-xl bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground' : classButton}><Icon className='mr-2 inline h-4 w-4'/>{label}</button>
        )}
      </nav>
      {error && <p role='alert' className='rounded-xl border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-300'>{error}</p>}

      {area === 'creator' && (
        <div className='space-y-4'>
          <CameraWorkspace />
          <ObsScenePanel />
          <CreatorMomentsPanel />
        </div>
      )}
      {area === 'money' && <section className={classPanel}>
        <h3 className='flex items-center gap-2 font-semibold'><DollarSign className='h-4 w-4 text-primary'/> Money desk · Lena, Adrian and Maya</h3>
        <p className='mt-2 text-sm text-muted-foreground'>Lena helps with personal finances; Adrian handles business unit economics; Maya identifies growth opportunities. Until approved accounts are connected, balances, income and forecasts stay unknown—not zero.</p>
        <div className='mt-4 grid gap-3 sm:grid-cols-3'>
          {['Personal spending & bill review','Business costs & margins','30-day income opportunities'].map(label =>
            <div key={label} className='rounded-xl border border-dashed border-border p-4 text-sm'>{label}<p className='mt-2 text-xs text-muted-foreground'>Awaiting verified data or assigned work</p></div>)}
        </div>
      </section>}

      {area === 'coordination' && <section className={classPanel}>
        <h3 className='flex items-center gap-2 font-semibold'><UsersRound className='h-4 w-4 text-primary'/> Convene a staff council</h3>
        <p className='mt-1 text-sm text-muted-foreground'>Creates real Synapse squad work items with specialists. Does not automatically start AI runtimes, send messages, publish or spend money.</p>
        <div className='mt-4 grid gap-3'>
          <label className='text-xs text-muted-foreground'>Objective
            <textarea className='mt-1 min-h-[88px] w-full rounded-xl border border-border bg-background p-3 text-sm text-foreground' value={objective} onChange={e => setObjective(e.target.value)} maxLength={1000}/>
          </label>
          <label className='text-xs text-muted-foreground'>Associated project
            <select className='mt-1 w-full rounded-xl border border-border bg-background p-3 text-sm text-foreground' value={project} onChange={e => setProject(e.target.value)}>{projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select>
          </label>
          <button type='button' className='w-fit rounded-xl bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground disabled:opacity-50' onClick={() => void assembleTeam()} disabled={busy || !objective.trim() || !project}>{busy ? 'Preparing…' : 'Create staff meeting'} <ArrowRight className='ml-1 inline h-4 w-4'/></button>
          {actionResult && <p role='status' className='rounded-xl border border-emerald-500/30 p-3 text-sm text-emerald-300'>{actionResult}</p>}
        </div>
      </section>}

      {brief && brief.attention.length > 0 && <section className={classPanel}>
        <h3 className='flex items-center gap-2 font-semibold'><CircleAlert className='h-4 w-4 text-amber-400'/> Staff attention inbox</h3>
        <div className='mt-3 grid gap-2 md:grid-cols-2'>{brief.attention.slice(0,8).map((item, i) => <button type='button' key={item.title+i} className='rounded-xl border border-border bg-background/50 p-3 text-left hover:border-primary/30' onClick={() => setSelected(item.staff_id)}><p className='text-sm font-medium'>{item.title}</p><p className='mt-1 text-xs text-muted-foreground'>{item.detail}</p></button>)}</div>
      </section>}

      <div className='grid gap-4 lg:grid-cols-[minmax(0,1.45fr)_minmax(300px,1fr)]'>
        <section className={classPanel}>
          <div className='mb-3 flex items-center justify-between gap-3'><h3 className='font-semibold'>People</h3><span className='text-xs text-muted-foreground'>{filtered.length} shown</span></div>
          <div className='grid gap-2 sm:grid-cols-2'>
            {filtered.map(person => <button key={person.id} type='button' onClick={() => setSelected(person.id)} className={selected === person.id || selected === person.handle ? 'rounded-2xl border border-primary/50 bg-primary/10 p-3 text-left' : 'rounded-2xl border border-border bg-background/40 p-3 text-left hover:border-primary/30'}>
              <div className='flex items-center gap-3'><div className='grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-primary/10 font-semibold text-primary'>{person.display_name.slice(0,1)}</div><div className='min-w-0'><p className='truncate text-sm font-semibold'>{person.display_name}<span className='ml-2 text-[10px] font-normal text-muted-foreground'>@{person.handle}</span></p><p className='truncate text-xs text-muted-foreground'>{person.title}</p></div></div>
              <div className='mt-2 flex items-center justify-between gap-2 text-[11px] text-muted-foreground'><span>{ROLES[person.handle] ?? 'Other'}</span><span className='capitalize'>{person.status.replaceAll('_',' ')}</span></div>
            </button>)}
            {!loading && filtered.length === 0 && <p className='text-sm text-muted-foreground'>No staff profiles from the service.</p>}
          </div>
        </section>
        <section className={classPanel}>
          {active ? <>
            <p className='text-xs font-semibold uppercase tracking-[0.18em] text-primary'>Selected employee</p>
            <h3 className='mt-2 text-2xl font-semibold'>{active.display_name}</h3>
            <p className='mt-1 text-sm text-muted-foreground'>{active.title}</p>
            <p className='mt-3 text-sm leading-6'>{active.bio}</p>
            <p className='mt-4 text-xs font-medium uppercase tracking-wide text-muted-foreground'>Current goals</p>
            <div className='mt-2 space-y-2'>{active.goals.map(goal => <div key={goal} className='flex gap-2 text-xs leading-5'><CheckCircle2 className='mt-0.5 h-3.5 w-3.5 shrink-0 text-primary'/>{goal}</div>)}</div>
            <p className='mt-4 text-xs font-medium uppercase tracking-wide text-muted-foreground'>Control & capability</p>
            <p className='mt-2 text-xs text-muted-foreground'>Policy: {active.authority_policy.replaceAll('_',' ')} · {dashboard?.permissions.length ?? 0} permission entries · {dashboard?.triggers.filter(t => t.enabled).length ?? 0} enabled triggers</p>
            <label className='mt-3 block text-xs text-muted-foreground'>Employee autonomy level
              <select className='mt-1 w-full rounded-xl border border-border bg-background px-3 py-2 text-sm text-foreground'
                value={active.authority_policy} disabled={busy} onChange={event =>
                  void changeAuthority(event.target.value as StaffMember['authority_policy'])}>
                <option value='advise_only'>Advise only</option>
                <option value='prepare_for_approval'>Prepare tasks for approval</option>
                <option value='act_within_limits'>Act in approved workspaces</option>
              </select>
            </label>
            <p className='mt-1 text-[11px] text-muted-foreground'>Sensitive external permissions stay approval-first even if you allow workspace actions.</p>
            <div className='mt-4 rounded-xl border border-border bg-background/40 p-3'>
              <p className='text-sm font-semibold'>Prepare an assignment for {active.display_name}</p>
              <textarea value={staffTask} onChange={e => setStaffTask(e.target.value)}
                className='mt-2 w-full rounded-xl border border-border bg-background p-3 text-sm'
                rows={2} maxLength={1000} placeholder='Describe the job and the expected result'/>
              <label className='mt-2 block text-xs text-muted-foreground'>Project
                <select value={project} onChange={e => setProject(e.target.value)}
                  className='mt-1 w-full rounded-xl border border-border bg-background px-3 py-2 text-sm text-foreground'>
                  {projects.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
                </select>
              </label>
              <button type='button' disabled={busy || !staffTask.trim() || !project} onClick={() => void assignIndividual()}
                className='mt-3 rounded-xl bg-primary px-3 py-2 text-sm font-semibold text-primary-foreground disabled:opacity-50'>
                Prepare task
              </button>
              {staffTaskResult && <p role='status' className='mt-2 break-all text-xs text-emerald-300'>{staffTaskResult}</p>}
            </div>
            <div className='mt-4 border-t border-border pt-4'>
              <p className='mb-2 flex items-center gap-2 text-sm font-semibold'><ShieldCheck className='h-4 w-4'/> Proactive review reminders</p>
              {dashboard?.triggers.length ? dashboard.triggers.map(trigger => (
                <div key={trigger.id} className='mb-2 flex flex-wrap items-center justify-between gap-2 rounded-xl border border-border bg-background/40 p-3'>
                  <div><p className='text-xs font-semibold'>{trigger.name}</p>
                    <p className='mt-1 text-[11px] text-muted-foreground'>{trigger.enabled ? 'Enabled · daily review nudge only' : 'Off · no background work'}</p>
                  </div>
                  <button type='button' disabled={busy || trigger.trigger_type !== 'schedule'}
                    onClick={() => void toggleReminder(trigger.id, !trigger.enabled)}
                    className={classButton}>{trigger.enabled ? 'Pause reminder' : 'Enable reminder'}</button>
                </div>
              )) : <p className='text-xs text-muted-foreground'>No scheduled reminders for this staff member.</p>}
              <p className='text-[11px] leading-5 text-muted-foreground'>Reminder notifications do not activate microphones, access accounts, launch AI tasks or send public messages.</p>
            </div>
            <div className='mt-4 border-t border-border pt-4'>
              <p className='mb-2 flex items-center gap-2 text-sm font-semibold'><MessageCircle className='h-4 w-4'/> Talk to {active.display_name}</p>
              {conversation && <div aria-live='polite' className='mb-3 max-h-52 overflow-y-auto whitespace-pre-wrap rounded-xl bg-background/60 p-3 text-xs leading-6'>{conversation}</div>}
              <label htmlFor='staff-hq-message' className='sr-only'>Message</label>
              <textarea id='staff-hq-message' value={message} onChange={e => setMessage(e.target.value)} placeholder='Ask a question or assign a specific task…' className='w-full rounded-xl border border-border bg-background p-3 text-sm' rows={3} maxLength={4000}/>
              <button type='button' className='mt-2 rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground disabled:opacity-50' onClick={() => void chat()} disabled={!message.trim() || busy}>{busy ? 'Sending…' : 'Send message'}</button>
              <p className='mt-2 text-xs text-muted-foreground'>Real replies require a working Synapse AI runtime. Failures are reported instead of simulated.</p>
            </div>
          </> : <p className='text-sm text-muted-foreground'>Select an employee to view their actual profile and responsibilities.</p>}
        </section>
      </div>
      <footer className='rounded-2xl border border-border bg-background/40 p-4 text-xs leading-5 text-muted-foreground'>
        <Lightbulb className='mr-1 inline h-3.5 w-3.5 text-primary'/> Proposed staff automations are seeded OFF until a connected runtime and approved triggers are tested. Actual content posting, OBS control, sponsorship outreach, account sync, and AI vision are not active by default.
      </footer>
    </div>
  );
}
