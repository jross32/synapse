import { useEffect, useMemo, useState } from 'react';
import { Activity, BellRing, ChevronDown, ChevronUp, CircleDollarSign, Coins, Download, Image as ImageIcon, RefreshCcw, Sparkles, Zap } from 'lucide-react';
import { apiFetch } from '../lib/api-client';
import './usage-costs.css';

type UsageObservation = { total_tokens: number | null; cost_usd: number | null; input_tokens: number | null; output_tokens: number | null; source: string };
type Execution = { id: string; runtime_id: string; model: string | null; project_id: string | null; kind: string; started_at: string | null; created_at: string; state: string; usage: UsageObservation[] };
type Capacity = { runtime_id: string; state: string; usable_now: boolean };
type RuntimeData = { executions: Execution[]; capacity: Capacity[]; measurement_note: string };
type ImageUsage = { provider: string; model: string; operation: string; image_count: number; reported_cost_usd: number | null; at?: string };
const providers = ['claude', 'codex', 'copilot', 'gemini', 'local', 'images'];
const colors: Record<string, string> = { claude: '#bb74f7', codex: '#39adf4', copilot: '#36d69c', gemini: '#ffbd5a', local: '#8fa3ff', images: '#f46ac9' };
const money = (value: number) => '$' + value.toFixed(2);
const fmt = (value: number) => value.toLocaleString();
const dayKey = (value: string) => value.slice(0, 10);
const safeDate = (e: Execution) => e.started_at || e.created_at;
const firstUsage = (e: Execution): UsageObservation | undefined => e.usage.find((u) => u.source && (u.cost_usd != null || u.total_tokens != null)) || e.usage[0];
const panel = 'usage-panel';
function Sparkline({ values, color, height = 120 }: { values: number[]; color: string; height?: number }) {
  const peak = Math.max(1, ...values);
  const step = 100 / Math.max(1, values.length - 1);
  const points = values.map((v, i) => `${i * step},${93 - v / peak * 82}`).join(' ');
  return <svg aria-label='Daily measured cost trend' role='img' preserveAspectRatio='none' viewBox='0 0 100 100' width='100%' height={height} className='usage-graph'><defs><linearGradient id={'costGrad' + color.slice(1)} x1='0' y1='0' x2='0' y2='1'><stop offset='0' stopColor={color} stopOpacity='.44'/><stop offset='1' stopColor={color} stopOpacity='0'/></linearGradient></defs><path d={`M0 100 L ${points.replaceAll(' ', ' L ')} L100 100 Z`} fill={`url(#costGrad${color.slice(1)})`}/><polyline points={points} fill='none' stroke={color} strokeWidth='1.9' vectorEffect='non-scaling-stroke' strokeLinejoin='round' strokeLinecap='round'/></svg>;
}
export function UsageCostsPage(): JSX.Element {
  const [data, setData] = useState<RuntimeData | null>(null);
  const [imageData, setImageData] = useState<ImageUsage[]>([]);
  const [alerts, setAlerts] = useState<Array<{metric?: string; runtime?: string; image_model?: string; change_pct?: number}>>([]);
  const [error, setError] = useState('');
  const [range, setRange] = useState(7);
  const [activityOpen, setActivityOpen] = useState(false);
  const [updating, setUpdating] = useState(false);
  async function reload() {
    setUpdating(true);
    const [runtime, images, alertResult] = await Promise.allSettled([apiFetch<RuntimeData>('/ai/runtimes?execution_limit=500'), apiFetch<{items: ImageUsage[]}>('/ai/usage-images'), apiFetch<{items: Array<{metric?: string; runtime?: string; image_model?: string; change_pct?: number}>}>('/ai/usage-alerts')]);
    if (runtime.status === 'fulfilled') { setData(runtime.value); setError(''); } else { setError('AI runtime metrics could not be loaded. ' + String(runtime.reason)); }
    if (images.status === 'fulfilled') setImageData(images.value.items);
    if (alertResult.status === 'fulfilled') setAlerts(alertResult.value.items);
    setUpdating(false);
  }
  useEffect(() => { void reload(); const id = setInterval(() => { void reload(); }, 60000); return () => clearInterval(id); }, []);
  const active = useMemo(() => {
    const cutoff = Date.now() - range * 86400000;
    return (data?.executions || []).filter((e) => Date.parse(safeDate(e)) >= cutoff);
  }, [data, range]);
  const imageActive = useMemo(() => imageData.filter((entry) => !entry.at || Date.parse(entry.at) >= Date.now() - range * 86400000), [imageData, range]);
  const summary = useMemo(() => {
    const groups: Record<string, { calls: number; cost: number; tokens: number; priced: number; unknown: number; daily: Record<string, number> }> = {};
    let totalCost = 0, totalTokens = 0, known = 0, unknown = 0;
    for (const e of active) {
      const group = groups[e.runtime_id] ||= { calls: 0, cost: 0, tokens: 0, priced: 0, unknown: 0, daily: {} };
      group.calls++;
      const u = firstUsage(e);
      if (u?.cost_usd != null) { group.cost += u.cost_usd; group.priced++; totalCost += u.cost_usd; known++; group.daily[dayKey(safeDate(e))] = (group.daily[dayKey(safeDate(e))] || 0) + u.cost_usd; }
      else { group.unknown++; unknown++; }
      const tokens = u?.total_tokens ?? (u?.input_tokens != null || u?.output_tokens != null ? (u.input_tokens || 0) + (u.output_tokens || 0) : 0);
      group.tokens += tokens; totalTokens += tokens;
    }
    const imageCount = imageActive.reduce((s, r) => s + r.image_count, 0);
    const imageCost = imageActive.reduce((s, r) => s + (r.reported_cost_usd ?? 0), 0);
    return { groups, totalCost, totalTokens, known, unknown, imageCount, imageCost };
  }, [active, imageActive]);
  const dates = Array.from({length: range}, (_, i) => dayKey(new Date(Date.now() - (range - 1 - i) * 86400000).toISOString()));
  const daily = dates.map((date) => Object.values(summary.groups).reduce((v, g) => v + (g.daily[date] || 0), 0));
  const providerEntries = Object.entries(summary.groups).sort((a,b) => b[1].cost - a[1].cost);
  const totalReported = summary.totalCost + summary.imageCost;
  const donutParts = [...providerEntries.filter(([,v]) => v.cost > 0).map(([name, v]) => ({name, cost: v.cost})), ...(summary.imageCost > 0 ? [{name: 'images', cost: summary.imageCost}] : [])];
  let donutOffset = 0;
  const donutGradient = totalReported > 0 ? 'conic-gradient(' + donutParts.map(({name, cost}) => { const from = donutOffset; donutOffset += cost / totalReported * 100; return `${colors[name] || '#8fa3ff'} ${from}% ${donutOffset}%`; }).join(',') + ')' : undefined;
  const exportRows = () => {
    const rows = [['time', 'provider', 'model', 'project', 'kind', 'tokens', 'reported_cost_usd', 'measurement_status'], ...active.map((e) => { const u = firstUsage(e); return [safeDate(e),e.runtime_id,e.model || '',e.project_id || '',e.kind,u?.total_tokens == null ? '' : String(u.total_tokens),u?.cost_usd == null ? '' : String(u.cost_usd),u?.cost_usd == null ? 'unknown' : 'reported']; })];
    const csv = rows.map((row) => row.map((cell) => '"' + cell.replaceAll('"','""') + '"').join(',')).join('\r\n');
    const url = URL.createObjectURL(new Blob([csv], {type:'text/csv'})); const anchor=document.createElement('a');anchor.href=url;anchor.download='synapse-ai-usage.csv';anchor.click();URL.revokeObjectURL(url);
  };
  return <section className='usage-dashboard'>
    <header className='usage-header'><div><div className='usage-eyebrow'><Sparkles size={14}/> AI WORKFORCE / ANALYTICS</div><h1>AI Usage &amp; Costs</h1><p>Live AI spending, model activity, image generation and performance</p></div><div className='usage-header-actions'><select aria-label='Reporting period' value={range} onChange={(e) => setRange(Number(e.target.value))}><option value={7}>Last 7 Days</option><option value={30}>Last 30 Days</option><option value={90}>Last 90 Days</option></select><button disabled={updating} onClick={() => void reload()} aria-label='Refresh usage'><RefreshCcw size={16}/></button><button onClick={exportRows}><Download size={16}/> Export</button></div></header>
    {error && <div className='usage-warning' role='alert'>{error}</div>}
    <div className='usage-metrics'><div className={panel}><CircleDollarSign/><span>Reported cost</span><strong>{money(totalReported)}</strong><small>{summary.unknown ? `${summary.unknown} AI calls with unknown cost` : 'Measured calls only'}</small></div><div className={panel}><Zap/><span>Requests tracked</span><strong>{fmt(active.length)}</strong><small>Latest 500 execution records</small></div><div className={panel}><Coins/><span>Measured tokens</span><strong>{fmt(summary.totalTokens)}</strong><small>Missing values excluded</small></div><div className={panel}><ImageIcon/><span>Images captured</span><strong>{fmt(summary.imageCount)}</strong><small>{imageActive.some((r) => r.reported_cost_usd == null) ? 'Some image costs unknown' : `${money(summary.imageCost)} reported image cost`}</small></div></div>
    <div className='usage-main-grid'><article className={panel}><div className='usage-section-title'><h2>Daily Cost Trend</h2><span>Measured USD â€¢ {range} days</span></div><div className='usage-chart-area'><div className='usage-chart-labels'><span>{money(Math.max(0,...daily))}</span><span>{money(Math.max(0,...daily)/2)}</span><span>$0.00</span></div><div className='usage-chart'><Sparkline values={daily} color='#b97aff' height={220}/><div className='usage-dates'><span>{dates[0]?.slice(5)}</span><span>{dates[Math.floor(dates.length/2)]?.slice(5)}</span><span>{dates[dates.length-1]?.slice(5)}</span></div></div></div><div className='usage-legend'>{providerEntries.map(([name]) => <span key={name}><i style={{background:colors[name]||'#8fa3ff'}}/>{name}</span>)}</div></article><article className={panel}><div className='usage-section-title'><h2>Provider Breakdown</h2><span>Reported values</span></div><div className='usage-donut-wrap'><div className='usage-donut' style={{background: donutGradient}}><div><strong>{money(totalReported)}</strong><small>Reported</small></div></div><div className='usage-donut-list'>{providerEntries.map(([name,v])=><div key={name}><i style={{background:colors[name]||'#8fa3ff'}}/><span>{name}</span><strong>{money(v.cost)}</strong></div>)}{summary.imageCount>0 && <div><i style={{background:colors.images}}/><span>Images</span><strong>{money(summary.imageCost)}</strong></div>}</div></div></article></div>
    <h2 className='usage-outside-heading'>Provider Details</h2><div className='usage-providers'>{providers.filter((name)=>name!=='images').map((name)=>{const g=summary.groups[name];const capacity=data?.capacity.find((c)=>c.runtime_id===name);return <div key={name} className={panel}><div className='usage-provider-head'><span className='usage-provider-avatar' style={{background:colors[name]||'#8fa3ff'}}>{name.slice(0,1).toUpperCase()}</span><strong>{name}</strong><b>{g ? money(g.cost) : 'â€”'}</b></div><small>{capacity?.state || 'Not measured'} â€¢ {g?.calls ?? 0} calls</small><div className='usage-progress'><i style={{width:totalReported ? `${(g?.cost||0)/totalReported*100}%` : '0%',background:colors[name]}}/></div><small>{g?.unknown ?? 0} unpriced â€¢ {fmt(g?.tokens ?? 0)} tokens</small></div>})}</div>
    <div className='usage-lower-grid'><article className={panel}><button className='usage-collapse' onClick={()=>setActivityOpen((v)=>!v)} aria-expanded={activityOpen} aria-controls='usage-recent-activity'><span><Activity size={18}/> Recent Activity <small>({active.length} calls)</small></span>{activityOpen?<ChevronUp size={18}/>:<ChevronDown size={18}/>}</button>{activityOpen && <div id='usage-recent-activity' className='usage-scroll'><table><thead><tr><th>Time</th><th>Provider</th><th>Model</th><th>Tokens</th><th>Cost</th><th>Project</th></tr></thead><tbody>{active.length ? active.map((e)=>{const u=firstUsage(e);return <tr key={e.id}><td>{new Date(safeDate(e)).toLocaleString()}</td><td>{e.runtime_id}</td><td>{e.model||'â€”'}</td><td>{u?.total_tokens == null ? 'â€”' : fmt(u.total_tokens)}</td><td>{u?.cost_usd == null ? 'Unknown' : money(u.cost_usd)}</td><td>{e.project_id||'â€”'}</td></tr>}) : <tr><td colSpan={6}>No AI executions recorded in this period.</td></tr>}</tbody></table></div>}</article><article className={panel}><div className='usage-section-title'><h2><BellRing size={17}/> Cost Alerts</h2><small>Measurements only</small></div><p className='usage-muted'>Cost-drift alerts are recorded by Synapse's benchmark monitor. Provider prices and subscription charges are not inferred.</p>{alerts.map((alert,index)=><div key={index} className='usage-alert' role='status'><BellRing size={15}/> {alert.runtime || alert.image_model || 'Provider'} {alert.metric || 'cost'} changed by {alert.change_pct ?? '?'}% from the benchmark.</div>)}<div className='usage-alert'><span className='usage-status-dot'/> {summary.unknown ? `${summary.unknown} execution(s) have no provider-reported dollar cost.` : 'No missing cost data in the current execution sample.'}</div></article></div>
    <div className='usage-bottom-grid'><article className={panel}><h2>Image Generation Costs</h2>{imageActive.length ? <table><thead><tr><th>Model</th><th>Images</th><th>Cost / image</th></tr></thead><tbody>{imageActive.map((i,index)=><tr key={index}><td>{i.model}</td><td>{i.image_count}</td><td>{i.reported_cost_usd == null || !i.image_count ? 'Unknown' : money(i.reported_cost_usd/i.image_count)}</td></tr>)}</tbody></table> : <p className='usage-muted'>No image price observations have been captured yet.</p>}</article><article className={panel}><h2>Task Cost Comparison</h2><p className='usage-muted'>Task-level comparisons require provider usage tagged to an execution and its project. Unmeasured costs are never shown as free.</p><div className='usage-efficiency'><span>Priced executions</span><strong>{summary.known}</strong></div><div className='usage-efficiency'><span>Unknown-cost executions</span><strong>{summary.unknown}</strong></div></article><article className={panel}><h2>Efficiency Metrics</h2><div className='usage-efficiency'><span>Recorded requests</span><strong>{fmt(active.length)}</strong></div><div className='usage-efficiency'><span>Measured tokens</span><strong>{fmt(summary.totalTokens)}</strong></div><div className='usage-efficiency'><span>Reported dollar spend</span><strong>{money(totalReported)}</strong></div></article></div>
    <p className='usage-footnote'>Synapse AI execution ledger â€¢ latest 500 calls available â€¢ costs reflect provider-reported values, not confirmed subscription charges. Metrics with incomplete coverage are explicitly labeled.</p>
  </section>;
}

