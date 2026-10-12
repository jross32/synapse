import { useEffect, useId, useMemo, useRef, useState } from 'react';
import { Activity, ArrowRight, Boxes, ChevronDown, ChevronUp, GripVertical, LayoutGrid, Monitor, RotateCcw, Search, Settings2, ShieldCheck, Sparkles, Users, Zap } from 'lucide-react';
import { useDaemon } from '@shared/daemon-context';
import type { NavigationIntent } from '@shared/nav';
import { formatLocal } from '@shared/format-time';
import { getAiHealthReport, type AiHealthReport } from '@shared/ai-client';
import { listAgentSquads } from '@shared/agent-squads-client';
import { getActiveTaskSummary, type ActiveTaskSummary } from '@shared/active-tasks-client';
import type { AgentSquad } from '@shared/generated-types';
import { getReviewInbox, type ReviewInbox } from '@shared/review-client';
import { getProject, launchProject } from '@shared/projects-client';
import type { Project } from '@shared/generated-types';
import { Brain3D } from '../components/Brain3D';
import { DeviceSyncOnboarding } from '../components/DeviceSyncOnboarding';
import { getProfilePreferences, updateProfilePreferences } from '@shared/profile-client';
import './home-redesign.css';

type PanelId='working'|'apps'|'agents'|'devices'|'activity'|'realm'|'health';
type PanelState={order:PanelId[];hidden:PanelId[];collapsed:PanelId[];preset:string};
const ALL:PanelId[]=['working','apps','agents','devices','activity','realm','health'];
const LABELS:Record<PanelId,string>={working:'Currently Working',apps:'My Apps',agents:'AI Workforce',devices:'Connected Devices',activity:'Recent Activity',realm:'Shared Realm',health:'System Health'};
const KEY='synapse.home.dashboard.v2';
const PANEL_DRAG_TYPE = 'application/x-synapse-dashboard-panel';
function loadLayout():PanelState {try{const raw=JSON.parse(localStorage.getItem(KEY)||'null');if(raw&&Array.isArray(raw.order)){const order=[...new Set((raw.order as string[]).filter((x):x is PanelId=>ALL.includes(x as PanelId))),...ALL.filter(x=>!raw.order.includes(x))];return {order,hidden:Array.isArray(raw.hidden)?raw.hidden.filter((x:string)=>ALL.includes(x as PanelId)):[],collapsed:[],preset:typeof raw.preset==='string'?raw.preset:'Balanced'};}}catch{} return{order:[...ALL],hidden:[],collapsed:[],preset:'Balanced'};}
interface Props{onNavigate:(intent:NavigationIntent)=>void}
export function SynapseDashboard({onNavigate}:Props):JSX.Element {
 const {projects,projectsLoaded,projectsError,recentEvents,health,profile,connState,refreshProjects,upsertProjectLocal}=useDaemon();
 const [layout,setLayout]=useState<PanelState>(loadLayout);
 const [customize,setCustomize]=useState(false);
 const [query,setQuery]=useState('');
 const [busy,setBusy]=useState<string|null>(null);
 const [launchError,setLaunchError]=useState<string|null>(null);
 const [report,setReport]=useState<AiHealthReport|null>(null);
 const [inbox,setInbox]=useState<ReviewInbox|null>(null);
 const [squads,setSquads]=useState<AgentSquad[]|null>(null);
 const [taskSummary,setTaskSummary]=useState<ActiveTaskSummary|null>(null);
 const [dragging,setDragging]=useState<PanelId|null>(null);
 const [dropTarget,setDropTarget]=useState<PanelId|null>(null);
 const [reorderMessage,setReorderMessage]=useState('');
 const dragSource=useRef<PanelId|null>(null);
 const reorderFocus=useRef<HTMLButtonElement|null>(null);
 const reorderInstructions=useId();
 const [layoutLoaded,setLayoutLoaded]=useState(false);
 const [layoutSyncError,setLayoutSyncError]=useState(false);
 const [dataRefreshError,setDataRefreshError]=useState(false);
 const initialLayout=useRef(layout);
 useEffect(()=>{let alive=true; if(!profile?.signed_in){setLayoutLoaded(true);return;} void getProfilePreferences().then(p=>{if(!alive)return;const remote=p.dashboard_layout;if(remote&&Array.isArray(remote.order)){localStorage.setItem(KEY,JSON.stringify(remote));const safe=loadLayout();initialLayout.current=safe;setLayout(safe);}setLayoutLoaded(true);}).catch(()=>{if(alive){setLayoutLoaded(true);setLayoutSyncError(true);}});return()=>{alive=false};},[profile?.signed_in,profile?.user_id]);
 useEffect(()=>{if(!layoutLoaded)return;localStorage.setItem(KEY,JSON.stringify(layout));if(!profile?.signed_in)return;if(JSON.stringify(layout)===JSON.stringify(initialLayout.current))return;const timer=window.setTimeout(()=>{void updateProfilePreferences({dashboard_layout:layout}).then(()=>{initialLayout.current=layout;setLayoutSyncError(false)}).catch(()=>setLayoutSyncError(true));},700);return()=>window.clearTimeout(timer);},[layout,layoutLoaded,profile?.signed_in]);
 useEffect(()=>{let mounted=true;async function load(){const values=await Promise.allSettled([getAiHealthReport(),getReviewInbox(),listAgentSquads(),getActiveTaskSummary()]);if(!mounted)return;if(values[0].status==='fulfilled')setReport(values[0].value);if(values[1].status==='fulfilled')setInbox(values[1].value);if(values[2].status==='fulfilled')setSquads(values[2].value);if(values[3].status==='fulfilled')setTaskSummary(values[3].value);setDataRefreshError(values.every(result=>result.status==='rejected'));}void load();const id=window.setInterval(()=>void load(),30000);return()=>{mounted=false;window.clearInterval(id)};},[]);
 const active=projects.filter(p=>p.status==='launched');
 const alerts=projects.filter(p=>p.status==='error');
 const ordered=useMemo(()=>layout.order.filter(id=>!layout.hidden.includes(id)),[layout]);
 useEffect(()=>{
  const handle=reorderFocus.current;
  if(handle?.isConnected){handle.focus({preventScroll:true});handle.scrollIntoView({block:'nearest',inline:'nearest'});}
  reorderFocus.current=null;
 },[layout]);
 function endDrag(){dragSource.current=null;setDragging(null);setDropTarget(null);}
 function movePanel(source:PanelId,target:PanelId){
  if(source===target||!ordered.includes(source)||!ordered.includes(target))return;
  change(previous=>{
   const from=previous.order.indexOf(source),to=previous.order.indexOf(target);
   if(from<0||to<0||previous.hidden.includes(source)||previous.hidden.includes(target))return previous;
   const order=[...previous.order];
   order.splice(from,1);
   // Use the original destination index: forward drops go after the target.
   order.splice(to,0,source);
   return {...previous,order,preset:'Custom'};
  });
  setReorderMessage(`${LABELS[source]} moved to position ${ordered.indexOf(target)+1} of ${ordered.length}.`);
 }
 const events=useMemo(()=>{const seen=new Set<number>();return recentEvents.filter(e=>{if(seen.has(e.id))return false;seen.add(e.id);return true;}).slice(0,8)},[recentEvents]);
 function change(update:(previous:PanelState)=>PanelState){setLayout(update);}
 function toggle(id:PanelId,field:'hidden'|'collapsed'){change(p=>({...p,[field]:p[field].includes(id)?p[field].filter(x=>x!==id):[...p[field],id]}));}
 function preset(name:string){setLayout({order:name==='Focus'?['working','apps','agents','devices','activity','realm','health']:name==='Workspace'?['realm','apps','devices','working','agents','activity','health']:[...ALL],hidden:name==='Focus'?['activity','realm','health']:[],collapsed:[],preset:name});}
 async function launch(p:Project){setBusy(p.id);setLaunchError(null);try{upsertProjectLocal(await launchProject(p.id));}catch(err){setLaunchError((err as Error).message);try{upsertProjectLocal(await getProject(p.id))}catch{}}finally{setBusy(null);}}
 function searchAction(){const value=query.trim().toLowerCase();if(!value)return;const actions:[string[],NavigationIntent][]=[[['settings','device','computer','connect'],{page:'settings'}],[['worker','agent','ai','session','claude','codex','copilot'],{page:'ai-coding',section:'sessions'}],[['workspace','memory','file','shared'],{page:'apps',section:'memory'}],[['activity','trace','logs','history'],{page:'trace'}],[['app','project','launch'],{page:'apps',section:'projects'}]];const action=actions.find(([terms])=>terms.some(term=>value===term||value.startsWith(term+' ')));if(action){onNavigate(action[1]);setQuery('');return;}if(projects.some(p=>p.name.toLowerCase().includes(value))){onNavigate({page:'apps',section:'projects'});setQuery('');return;}onNavigate({page:'tools'});setQuery('');}
 const firstName=profile?.signed_in ? ('Welcome back' + (profile.display_name ? ', '+profile.display_name.split(' ')[0] : '')) : 'Welcome to Synapse';
 const panel=(id:PanelId)=>{
  if(id==='working')return active.length?<div className='syn-dash-list'>{active.slice(0,6).map(p=><button className='syn-dash-task' key={p.id} onClick={()=>onNavigate({page:'apps',section:'running'})}><span className='syn-dash-avatar'><Zap size={15}/></span><span><strong>{p.name}</strong><small>Running on Synapse</small></span><em>Live</em></button>)}</div>:<p className='syn-dash-empty'>No active projects right now. Launch an app to see it here.</p>;
  if(id==='apps')return <div className='syn-dash-appgrid'>{projects.slice(0,9).map((p,i)=><button type='button' key={p.id} className='syn-dash-app' disabled={busy===p.id} onClick={()=>p.status==='launched'?onNavigate({page:'apps',section:'running'}):void launch(p)} title={p.status==='launched'? 'Open running app details':'Launch '+p.name}><span className={'syn-dash-appicon syn-dash-color-'+i%5}><Boxes size={20}/></span><strong>{p.name}</strong><small>{p.status==='launched'?'Running':p.status==='error'?'Error':'Launch'}</small></button>)}<button className='syn-dash-app' onClick={()=>onNavigate({page:'apps',section:'projects'})}><span className='syn-dash-appicon'><ArrowRight/></span><strong>All apps</strong></button></div>;
  if(id==='agents')return <div className='syn-dash-list'>{dataRefreshError&&<p role='status' className='syn-dash-muted'>Live workforce data is temporarily unavailable.</p>}<div className='syn-dash-healthstats' aria-label='Live AI workforce summary'><span><strong>{squads?squads.filter(s=>s.status==='active').length:'—'}</strong> Active squads</span><span><strong>{taskSummary?.running_or_dispatched??'—'}</strong> Running tasks</span><span><strong>{taskSummary?.enabled??'—'}</strong> Scheduled</span></div><button className='syn-dash-task' onClick={()=>onNavigate({page:'ai-coding',section:'sessions'})}><span className='syn-dash-avatar'><Users size={16}/></span><span><strong>AI sessions</strong><small>View live workers and conversations</small></span><ArrowRight size={15}/></button><button className='syn-dash-task' onClick={()=>onNavigate({page:'ai-coding',section:'squads'})}><span className='syn-dash-avatar'><Sparkles size={16}/></span><span><strong>Agent squads</strong><small>Coordinate AI teammates</small></span><ArrowRight size={15}/></button><button className='syn-dash-task' onClick={()=>onNavigate({page:'ai-coding',section:'active-tasks'})}><span className='syn-dash-avatar'><Activity size={16}/></span><span><strong>Active tasks</strong><small>Scheduled automated work</small></span><ArrowRight size={15}/></button></div>;
  if(id==='devices')return <div className='syn-dash-list'><button className='syn-dash-task' onClick={()=>onNavigate({page:'settings'})}><span className='syn-dash-avatar'><Monitor size={18}/></span><span><strong>{profile?.current_host?.name || 'This computer'}</strong><small>{connState==='open'?'Connected to Synapse daemon':'Disconnected'}</small></span><em>{connState==='open'?'Online':'Offline'}</em></button><p className='syn-dash-muted'>{profile?.signed_in ? (profile.sync_enabled ? 'Account sync enabled' : 'Account sync not enabled') : 'Sign in to pair devices'} � {profile?.portable_connection_count ?? 0} portable connections. Other devices are not counted until verified.</p></div>;
  if(id==='activity')return events.length?<div className='syn-dash-list'>{events.map(e=><div key={e.id} className='syn-dash-event'><Activity size={14}/><span>{e.name}</span><time>{formatLocal(e.timestamp_utc,'time')}</time></div>)}</div>:<p className='syn-dash-empty'>No recent activity. Live events appear when Synapse reports them.</p>;
  if(id==='realm')return <div className='syn-dash-realm'><div className='syn-dash-chips'><span>Projects</span><span>Files</span><span>Memory</span><span>Devices</span></div><p>{projects.length} projects currently registered in this Synapse connection.</p><button onClick={()=>onNavigate({page:'apps',section:'memory'})}>Open shared workspace <ArrowRight size={14}/></button></div>;
  return <div className='syn-dash-health'><div className='syn-dash-healthstatus'><ShieldCheck size={20}/><strong>{connState==='open'?'Daemon connected':'Daemon disconnected'}</strong></div><div className='syn-dash-healthstats'><span><strong>{projects.length}</strong> Projects</span><span><strong>{active.length}</strong> Running</span><span><strong>{alerts.length}</strong> Errors</span></div><p>Quality gates: {report?.quality?.open_count??'Unknown'} · Review items: {inbox?.count??'Unknown'}</p><small>{health?'Daemon v'+health.version:'Waiting for health data'}</small></div>;
 };
 return <div className='syn-dash'>
 <DeviceSyncOnboarding signedIn={Boolean(profile?.signed_in && !profile?.sync_enabled)} accountId={profile?.user_id} currentHostId={profile?.current_host?.id} />
 <div className='syn-dash-command'><Search size={20}/><input value={query} onChange={e=>setQuery(e.target.value)} onKeyDown={e=>{if(e.key==='Enter')searchAction()}} placeholder='Find a project or open tools…' aria-label='Search projects and actions'/><button onClick={searchAction} aria-label='Run search'><ArrowRight size={20}/></button></div>
 <div className='syn-dash-shortcuts'><button onClick={()=>onNavigate({page:'apps',section:'projects'})}><Boxes size={15}/> Launch an app</button><button onClick={()=>onNavigate({page:'apps',section:'memory'})}><Search size={15}/> Find a file</button><button onClick={()=>onNavigate({page:'ai-coding',section:'sessions'})}><Sparkles size={15}/> Work on a project</button><button onClick={()=>onNavigate({page:'tools'})}><Activity size={15}/> Analyze this</button><button onClick={()=>onNavigate({page:'settings'})}><Monitor size={15}/> Connect a device</button><button onClick={()=>onNavigate({page:'settings'})}><ShieldCheck size={15}/> Help me</button></div>
 <div className='syn-dash-toolbar'><span><LayoutGrid size={17}/> My dashboard <small>{projectsLoaded?projects.length+' projects connected':'Loading…'}</small></span><button onClick={()=>{endDrag();setReorderMessage('');setCustomize(p=>!p)}}><Settings2 size={15}/>{customize?'Done customizing':'Customize dashboard'}</button></div>
 {customize&&<div className='syn-dash-custom'><strong>Customize panels</strong><div className='syn-dash-presets'>{['Balanced','Focus','Workspace'].map(x=><button key={x} aria-pressed={layout.preset===x} onClick={()=>preset(x)}>{x}</button>)}<button onClick={()=>setLayout({order:[...ALL],hidden:[],collapsed:[],preset:'Balanced'})}><RotateCcw size={14}/> Reset</button></div><div className='syn-dash-pick'>{ALL.map(id=><label key={id}><input type='checkbox' checked={!layout.hidden.includes(id)} onChange={()=>toggle(id,'hidden')}/>{LABELS[id]}</label>)}</div><p id={reorderInstructions}>Drag a panel handle to reorder. Or focus its handle and use Up/Down to move, Home/End for first/last. Collapse each panel with the chevron.</p><p role='status' aria-live='polite' aria-atomic='true'>{reorderMessage}</p></div>}
 {layoutSyncError&&profile?.signed_in&&<div role='status' className='syn-dash-warning'>Dashboard layout saved locally. Account synchronization is temporarily unavailable.</div>}
 {projectsError&&<div role='alert' className='syn-dash-warning'>Projects unavailable: {projectsError}<button onClick={()=>void refreshProjects()}>Retry</button></div>}
 {launchError&&<p role='alert' className='syn-dash-warning'>Launch failed: {launchError}</p>}
 <section className='syn-dash-hero'><div className='syn-dash-greeting'><span>YOUR CONNECTED WORKSPACE</span><h1>{firstName}</h1><p>Build, organize, and automate from one command center. See your connected projects and activity in one place.</p><div className='syn-dash-metrics'><div><Monitor size={18}/><strong>{connState==='open'?'Online':'Offline'}</strong><small>Synapse connection</small></div><div><Users size={18}/><strong>{active.length}</strong><small>Projects running</small></div><div><Boxes size={18}/><strong>{projects.length}</strong><small>Registered apps</small></div></div></div><div className='syn-dash-brain'><Brain3D activeCount={active.length} onNavigate={onNavigate}/></div><div className='syn-dash-ai'><div><Sparkles size={17}/> Synapse AI <span>{connState==='open'?'Connected':'Offline'}</span></div><p>Choose an action to work with your connected tools and projects.</p><button onClick={()=>onNavigate({page:'ai-coding',section:'sessions'})}>Work on my projects <ArrowRight size={14}/></button><button onClick={()=>onNavigate({page:'updates'})}>Check for updates <ArrowRight size={14}/></button><button onClick={()=>onNavigate({page:'apps',section:'memory'})}>Find something in files <ArrowRight size={14}/></button><button onClick={()=>onNavigate({page:'settings'})}>Help me set something up <ArrowRight size={14}/></button></div></section>
 <div className='syn-dash-panels'>{ordered.map((id,index)=><section
  key={id}
  data-panel-id={id}
  data-dragging={dragging===id||undefined}
  data-drop-target={dropTarget===id||undefined}
  className={'syn-dash-panel syn-dash-panel--'+id+(layout.collapsed.includes(id)?' is-collapsed':'')}
  style={dropTarget===id?{borderColor:'var(--synapse-accent)'}:undefined}
  onDragOver={e=>{
   if(!customize||!dragSource.current||!e.dataTransfer.types.includes(PANEL_DRAG_TYPE))return;
   e.preventDefault();
   e.dataTransfer.dropEffect='move';
   setDropTarget(dragSource.current===id?null:id);
  }}
  onDragLeave={e=>{if(!(e.relatedTarget instanceof Node)||!e.currentTarget.contains(e.relatedTarget))setDropTarget(p=>p===id?null:p)}}
  onDrop={e=>{
   const source=dragSource.current;
   if(!customize||!source)return;
   e.preventDefault();
   if(e.dataTransfer.getData(PANEL_DRAG_TYPE)===source)movePanel(source,id);
   endDrag();
  }}
 ><header>{customize&&<button
  type='button'
  className='syn-dash-panel-collapse'
  aria-label={'Reorder '+LABELS[id]}
  aria-describedby={reorderInstructions}
  aria-keyshortcuts='ArrowUp ArrowDown Home End'
  title={'Reorder '+LABELS[id]+' (Up/Down, Home/End)'}
  style={{cursor:dragging===id?'grabbing':'grab'}}
  draggable
  onDragStart={e=>{
   dragSource.current=id;
   e.dataTransfer.effectAllowed='move';
   e.dataTransfer.setData(PANEL_DRAG_TYPE,id);
   e.dataTransfer.setData('text/plain',LABELS[id]);
   setDragging(id);
   setDropTarget(null);
  }}
  onDragEnd={endDrag}
  onKeyDown={e=>{
   if(e.key==='Escape'){endDrag();return;}
   if(e.altKey||e.ctrlKey||e.metaKey||e.shiftKey)return;
   const destination=e.key==='ArrowUp'?index-1:e.key==='ArrowDown'?index+1:e.key==='Home'?0:e.key==='End'?ordered.length-1:null;
   if(destination===null)return;
   e.preventDefault();
   const target=ordered[destination];
   if(target&&target!==id){reorderFocus.current=e.currentTarget;movePanel(id,target);}
  }}
 ><GripVertical size={15} aria-hidden='true'/></button>}<h2>{LABELS[id]}</h2><button className='syn-dash-panel-collapse' aria-label={(layout.collapsed.includes(id)?'Expand ':'Collapse ')+LABELS[id]} onClick={()=>toggle(id,'collapsed')}>{layout.collapsed.includes(id)?<ChevronDown size={16}/>:<ChevronUp size={16}/>}</button><button className='syn-dash-view' onClick={()=>onNavigate(id==='apps'?{page:'apps',section:'projects'}:id==='agents'?{page:'ai-coding',section:'sessions'}:id==='activity'||id==='health'?{page:'trace'}:id==='realm'?{page:'apps',section:'memory'}:id==='devices'?{page:'settings'}:{page:'apps',section:'running'})}>View all <ArrowRight size={13}/></button></header>{!layout.collapsed.includes(id)&&<div className='syn-dash-panel-body'>{panel(id)}</div>}</section>)}</div>
 </div>;
}






