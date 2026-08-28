import { useCallback, useEffect, useMemo, useState } from 'react';
import { CheckCircle2, Lightbulb, Loader2, PlayCircle, RefreshCw, RotateCcw, XCircle } from 'lucide-react';
import { approveProposal, listProposals, promoteProposal, reconcileProposals, rejectProposal, updateProposalLifecycle, type Proposal, type ProposalStatus } from '@shared/review-client';
import { useDaemon } from '@shared/daemon-context';
import { Button } from './ui/button';
import { Card } from './ui/card';

const LABEL: Record<string,string> = { bug:'Bugs & errors', improvement:'Improvements', 'ui-ux':'UI & UX', backend:'Backend', frontend:'Frontend', performance:'Performance', reliability:'Reliability', security:'Security', testing:'Testing', docs:'Documentation', 'developer-experience':'Developer experience', architecture:'Architecture', data:'Data', automation:'Automation', measurement:'Measurement', 'design-decision':'Design decisions', maintenance:'Maintenance', other:'Other' };
type View = 'active' | ProposalStatus | 'declined' | 'all';
const statusLabel = (s: ProposalStatus) => s === 'in_progress' ? 'In progress' : s === 'done' ? 'Done' : 'Proposed';

export function ProposalBacklog(): JSX.Element | null {
  const { subscribeRaw } = useDaemon();
  const [items,setItems] = useState<Proposal[]>([]);
  const [view,setView] = useState<View>('active');
  const [loading,setLoading] = useState(true);
  const [busy,setBusy] = useState(false);
  const [error,setError] = useState<string|null>(null);
  const refresh = useCallback(async () => { try { setItems(await listProposals({sort_by:'updated_at',sort_dir:'desc'})); setError(null); } catch(e) { setError((e as Error).message); } finally { setLoading(false); } },[]);
  useEffect(() => { void refresh(); },[refresh]);
  useEffect(() => subscribeRaw((e) => { if (e.name === 'v1.review.proposal_filed' || e.name === 'v1.review.proposal_updated') void refresh(); }),[subscribeRaw,refresh]);
  const visible = useMemo(() => items.filter((p) => view === 'all' || view === 'active' ? (view === 'all' || (p.decision !== 'declined' && p.status !== 'done')) : view === 'declined' ? p.decision === 'declined' : p.status === view && p.decision !== 'declined'),[items,view]);
  const groups = useMemo(() => { const m = new Map<string,Proposal[]>(); for (const p of visible) { const k=LABEL[p.kind] ?? p.kind.replace(/-/g,' '); m.set(k,[...(m.get(k)??[]),p]); } return [...m.entries()].sort((a,b)=>a[0].localeCompare(b[0])); },[visible]);
  const count = (key: View) => key === 'all' ? items.length : key === 'active' ? items.filter(p=>p.decision!=='declined'&&p.status!=='done').length : key === 'declined' ? items.filter(p=>p.decision==='declined').length : items.filter(p=>p.status===key&&p.decision!=='declined').length;
  async function reconcile() { setBusy(true); try { await reconcileProposals(); await refresh(); } catch(e) { setError((e as Error).message); } finally { setBusy(false); } }
  if (loading) return <Card className='p-4 text-sm text-muted-foreground'><Loader2 className='mr-2 inline h-4 w-4 animate-spin'/>Loading improvement backlog…</Card>;
  if (!items.length && !error) return null;
  return <section className='flex flex-col gap-3'>
    <div className='flex flex-wrap items-center gap-2'><Lightbulb className='h-4 w-4 text-primary'/><div className='mr-auto'><h2 className='text-sm font-semibold'>Improvement backlog</h2><p className='text-xs text-muted-foreground'>Decision and implementation progress are tracked separately.</p></div><Button size='sm' variant='outline' disabled={busy} onClick={()=>void reconcile()}>{busy?<Loader2 className='h-4 w-4 animate-spin'/>:<RefreshCw className='h-4 w-4'/>} Reconcile signals</Button></div>
    {error && <p role='alert' className='text-xs text-destructive'>{error}</p>}
    <div className='flex flex-wrap gap-1.5'>{([['active','Active'],['proposed','Proposed'],['in_progress','In progress'],['done','Done'],['declined','Declined'],['all','All']] as [View,string][]).map(([k,l])=><Button key={k} size='sm' variant={view===k?'default':'outline'} onClick={()=>setView(k)}>{l} <span className='text-[10px]'>{count(k)}</span></Button>)}</div>
    {!groups.length ? <Card className='p-5 text-center text-sm text-muted-foreground'>No proposals in this view.</Card> : groups.map(([name,ps])=><div key={name} className='flex flex-col gap-2'><div className='text-sm font-semibold'>{name} <span className='text-xs font-normal text-muted-foreground'>({ps.length})</span></div>{ps.map(p=><ProposalRow key={p.id} proposal={p} refresh={refresh}/>)}</div>)}
  </section>;
}

function ProposalRow({proposal:p,refresh}:{proposal:Proposal;refresh:()=>Promise<void>}):JSX.Element {
  const [busy,setBusy]=useState(false); const [open,setOpen]=useState(false); const [error,setError]=useState<string|null>(null); const ev=p.lifecycle_evidence.at(-1); const promoted=p.lifecycle_evidence.some(e=>e.source==='backlog')||p.resolution_note.startsWith('Promoted to backlog item ');
  async function run(fn:()=>Promise<unknown>){setBusy(true);setError(null);try{await fn();await refresh();}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
  return <Card className='p-4'><button type='button' className='flex w-full items-center gap-2 text-left' onClick={()=>setOpen(v=>!v)}><span className='min-w-0 flex-1 font-semibold'>{p.title}</span><span className='rounded bg-secondary/70 px-1.5 py-0.5 text-[10px]'>{statusLabel(p.status)}</span>{p.decision==='pending'&&<span className='text-[10px] text-primary'>needs decision</span>}{p.decision==='declined'&&<span className='text-[10px] text-destructive'>declined</span>}</button>{open&&<div className='mt-3 flex flex-col gap-2 border-t pt-3 text-sm'><p className='whitespace-pre-wrap text-muted-foreground'>{p.rationale_md||'No rationale supplied.'}</p><p className='text-xs text-muted-foreground'><span className='font-mono'>{p.id}</span>{p.project_id?` · ${p.project_id}`:''}</p>{ev&&<p className='rounded bg-secondary/30 p-2 text-xs text-muted-foreground'>Evidence · {ev.source}{ev.ref_id?` · ${ev.ref_id}`:''}: {ev.detail}</p>}{error&&<p className='text-xs text-destructive'>{error}</p>}<div className='flex flex-wrap gap-2'>{p.project_id&&p.status==='proposed'&&p.decision!=='declined'&&!promoted&&<Button size='sm' disabled={busy} onClick={()=>void run(()=>promoteProposal(p.id))}><PlayCircle className='h-4 w-4'/>Accept + backlog</Button>}{p.decision!=='accepted'&&<Button size='sm' variant='outline' disabled={busy} onClick={()=>void run(()=>approveProposal(p.id))}><CheckCircle2 className='h-4 w-4'/>Accept</Button>}{p.status==='proposed'&&p.decision!=='declined'&&<Button size='sm' variant='outline' disabled={busy} onClick={()=>void run(()=>updateProposalLifecycle(p.id,'in_progress','Started from Review'))}><PlayCircle className='h-4 w-4'/>Start</Button>}{p.status==='in_progress'&&p.decision!=='declined'&&<Button size='sm' variant='outline' disabled={busy} onClick={()=>void run(()=>updateProposalLifecycle(p.id,'done','Marked done from Review'))}><CheckCircle2 className='h-4 w-4'/>Done</Button>}{p.status==='done'&&<Button size='sm' variant='outline' disabled={busy} onClick={()=>void run(()=>updateProposalLifecycle(p.id,'proposed','Reopened from Review'))}><RotateCcw className='h-4 w-4'/>Reopen</Button>}{p.decision!=='declined'&&p.status!=='done'&&<Button size='sm' variant='ghost' className='text-destructive' disabled={busy} onClick={()=>void run(()=>rejectProposal(p.id))}><XCircle className='h-4 w-4'/>Decline</Button>}</div></div>}</Card>;
}
