import { existsSync } from 'node:fs';
import { copyFile } from 'node:fs/promises';
import path from 'node:path';

const SCORE_AREAS = ['ui', 'ux', 'performance', 'accessibility', 'reliability'];
const AREA_TIE_BREAK = new Map([
  ['reliability', 0],
  ['ux', 1],
  ['accessibility', 2],
  ['ui', 3],
  ['performance', 4],
]);
const VISUAL_CHECKLIST = [
  'Visual hierarchy: the primary job and primary action are obvious at first glance.',
  'Spacing and alignment: rhythm is intentional; dense and sparse regions both feel controlled.',
  'Typography and density: type scale, line length, emphasis, and information density support scanning.',
  'Color and brand polish: color has a semantic job and the surface feels product-specific rather than generic.',
  'Perceived affordance: interactive controls look interactive before hover or trial-and-error.',
  'First-time-user clarity: labels and sequencing make the next useful action understandable without prior knowledge.',
  'Motion quality: transitions explain state change without adding delay, distraction, or ambiguity.',
  'Empty, loading, error, and success states: state changes remain understandable and recoverable.',
];

function esc(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function finite(value) {
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function signed(value, digits = 0) {
  const n = finite(value);
  if (n === null) return 'n/a';
  const rounded = digits ? n.toFixed(digits) : String(Math.round(n * 10) / 10);
  return `${n >= 0 ? '+' : ''}${rounded}`;
}

function scoreValue(value) {
  const n = finite(value);
  return n === null ? 'n/a' : String(Math.round(n * 10) / 10);
}

function objectHasMeasuredValue(value) {
  if (value === null || value === undefined) return false;
  if (typeof value !== 'object') return true;
  const values = Object.values(value);
  return values.length > 0 && values.some((item) => item !== null && item !== undefined);
}

function evidenceType(metric) {
  const source = String(metric?.source || 'heuristic').toLowerCase();
  if (!objectHasMeasuredValue(metric?.observed)) return 'Derived / fallback';
  if (source.includes('proxy') || source.includes('fallback')) return 'Measured / proxy';
  return 'Measured / derived';
}

function impact(score) {
  const n = finite(score);
  if (n === null) return 'Review';
  if (n < 60) return 'High';
  if (n < 75) return 'Medium';
  return 'Low';
}

function priorities(score) {
  return Object.entries(score?.metrics || {})
    .flatMap(([area, items]) => (items || []).map((metric) => ({ area, metric })))
    .filter(({ metric }) => !['not_measured', 'not_applicable'].includes(String(metric?.status || '')) && finite(metric?.score) !== null && Number(metric.score) < 85)
    .sort((a, b) => {
      const scoreDelta = Number(a.metric.score) - Number(b.metric.score);
      if (scoreDelta) return scoreDelta;
      return (AREA_TIE_BREAK.get(a.area) ?? 99) - (AREA_TIE_BREAK.get(b.area) ?? 99);
    });
}

function failedJourneyCount(data) {
  return (data?.findings || [])
    .filter((finding) => String(finding?.code || '').startsWith('journey.') && /missing|failed/.test(String(finding?.code || '')))
    .reduce((total, finding) => total + (Number(finding?.occurrences) || 1), 0);
}

function sceneEvidence(data) {
  const scenes = Array.isArray(data?.scenes) ? data.scenes : [];
  const requested = Array.isArray(data?.journey) ? data.journey.length : 0;
  const distinct = new Set(scenes.map((scene) => String(scene?.url || '').replace(/#.*$/, ''))).size;
  return {
    mode: data?.journey_mode || (requested ? 'guided' : 'automatic-safe-tour'),
    captured: scenes.length,
    distinct,
    requested,
    failed: failedJourneyCount(data),
    screenshots: scenes.filter((scene) => Boolean(scene?.screenshot)).length,
  };
}

function timingEvidence(data, score) {
  const target = finite(score?.target_duration_seconds ?? data?.duration_seconds);
  const video = finite(score?.video_duration_seconds);
  const delta = finite(score?.video_duration_delta_seconds);
  const recording = finite(data?.recording_elapsed_seconds);
  const finalize = finite(data?.video_finalize_seconds);
  return { target, video, delta, recording, finalize };
}

function gateWhy(gate) {
  switch (gate?.id) {
    case 'ux.no_interaction':
      return 'The opening state does not expose a usable path forward, so visual polish cannot compensate for task failure.';
    case 'ux.trapped_dialog':
      return 'A user can become stuck in a visible modal or dialog without an in-product escape path.';
    case 'ux.task_failure':
      return 'The requested journey was not completed often enough to prove the core task is usable.';
    case 'ui.mobile_overflow':
      return 'Important content or controls may be clipped or require unintended horizontal scrolling on mobile.';
    case 'target.identity_mismatch':
      return 'The evidence appears to describe a different application, so the assessment must not be used for this target.';
    default:
      return 'This gate caps the aggregate score because a severe product-experience failure should outweigh cosmetic quality.';
  }
}

function decisionSummary(score) {
  if (score?.validity?.status === 'mismatch') {
    return 'Assessment invalid: target identity mismatch. Do not use this score as product evidence.';
  }
  const gates = Array.isArray(score?.gates) ? score.gates : [];
  if (gates.length) {
    return `${gates.length} hard gate${gates.length === 1 ? '' : 's'} active. Resolve gate failures before treating the aggregate score as readiness evidence.`;
  }
  return 'No hard score gate is active. Prioritize the lowest measured scores, then complete the explicitly unmeasured visual review before claiming improvement.';
}

function markdownJson(value) {
  return JSON.stringify(value ?? null).replaceAll('|', '\\|');
}

function deltaFor(comparison, area) {
  if (!comparison?.score_deltas) return null;
  return finite(comparison.score_deltas[area]);
}

function scoreRowsMarkdown(score, comparison) {
  const lines = ['| Area | Score | Delta vs previous |', '| --- | ---: | ---: |'];
  for (const area of SCORE_AREAS) {
    const current = score?.scores?.[area];
    if (current === undefined) continue;
    const delta = deltaFor(comparison, area);
    lines.push(`| ${area.toUpperCase()} | ${scoreValue(current)} | ${delta === null ? 'n/a' : signed(delta)} |`);
  }
  return lines;
}

function priorityRowsMarkdown(score) {
  const rows = priorities(score);
  if (!rows.length) return ['No measured benchmark item is below 85. Use the unmeasured visual-review checklist and product-specific acceptance criteria for the next decision.'];
  const lines = ['| Impact | Area | Benchmark | Score | Evidence type | Observed | Target |', '| --- | --- | --- | ---: | --- | --- | --- |'];
  for (const { area, metric } of rows) {
    lines.push(`| ${impact(metric.score)} | ${area.toUpperCase()} | ${metric.label} | ${scoreValue(metric.score)} | ${evidenceType(metric)} | \`${markdownJson(metric.observed)}\` | ${String(metric.target || '').replaceAll('|', '\\|')} |`);
  }
  return lines;
}

export async function prepareReportData(data, runDir) {
  const root = path.resolve(runDir || '.');
  const scenes = [];
  for (const scene of data?.scenes || []) {
    const source = scene?.screenshot ? path.resolve(String(scene.screenshot)) : null;
    const basename = source ? path.basename(source) : null;
    const local = basename ? path.join(root, basename) : null;
    let available = Boolean(local && existsSync(local));
    let copied = false;
    if (!available && source && local && existsSync(source) && source !== local) {
      try {
        await copyFile(source, local);
        available = true;
        copied = true;
      } catch {
        available = false;
      }
    }
    scenes.push({
      ...scene,
      screenshot: available ? local : null,
      screenshot_available: available,
      screenshot_copied_for_report: copied,
    });
  }
  return { ...data, scenes };
}

export function buildHumanMarkdown(data, score, comparison) {
  const timing = timingEvidence(data, score);
  const scenes = sceneEvidence(data);
  const lines = [
    `# UI Demo Studio report - ${data?.target_input || data?.target_url || 'target'}`,
    '',
    `> **Decision summary:** ${decisionSummary(score)}`,
    '',
    '## Score summary',
    '',
    `**Overall:** ${scoreValue(score?.overall_score)}/100 (${score?.grade || 'n/a'})${comparison ? ` - previous ${scoreValue(comparison.previous_overall)} -> current ${scoreValue(comparison.current_overall)} (${signed(comparison.overall_delta)})` : ''}`,
    '',
    ...scoreRowsMarkdown(score, comparison),
    '',
    '## Evidence labels',
    '',
    '- **Measured / derived:** browser-observed evidence transformed by the deterministic benchmark rubric.',
    '- **Measured / proxy:** browser evidence is available, but the metric used a documented proxy or fallback rather than the preferred direct signal.',
    '- **Derived / fallback:** the preferred observation was unavailable; interpret the score with lower confidence.',
    '- **UNMEASURED visual review:** requires a human or vision-capable AI to inspect the captured video/screenshots. It is not included as if it were deterministic telemetry.',
    '',
    '## Timing evidence',
    '',
    `- Configured target duration: ${timing.target === null ? 'not recorded' : `${timing.target}s`} (**target/configuration**).`,
    `- Encoded video duration: ${timing.video === null ? 'not measured' : `${timing.video}s`} (**measured from video metadata**).`,
    `- Video vs target delta: ${timing.delta === null ? 'not measured' : `${signed(timing.delta, 2)}s`} (positive means the encoded video is longer).`,
    `- Recorder elapsed window: ${timing.recording === null ? 'not recorded' : `${timing.recording}s`} (**measured recorder window**).`,
    `- Video finalization overhead: ${timing.finalize === null ? 'not recorded' : `${timing.finalize}s`} (**post-record processing; not video duration**).`,
    '',
    '## Scene coverage',
    '',
    `- Journey mode: **${scenes.mode}**.`,
    `- Captured evidence: **${scenes.captured} scene${scenes.captured === 1 ? '' : 's'}** across **${scenes.distinct} distinct URL state${scenes.distinct === 1 ? '' : 's'}**; **${scenes.screenshots} screenshot asset${scenes.screenshots === 1 ? '' : 's'} available** in the report bundle.`,
    `- Requested guided labels: **${scenes.requested}**; recorded missing/failed journey events: **${scenes.failed}**.`,
    '- Scene count is evidence coverage, not proof that every task succeeded. Use the measured Task / journey success benchmark for completion evidence.',
    '',
    '## Hard gates',
    '',
  ];
  if (!score?.gates?.length) {
    lines.push('No hard gate was triggered in this benchmark run.', '');
  } else {
    for (const gate of score.gates) {
      lines.push(`### BLOCKER - ${gate.effect}`, '', gate.reason, '', `**Why it matters:** ${gateWhy(gate)}`, '');
    }
  }
  lines.push('## Highest-impact measured fixes', '', ...priorityRowsMarkdown(score), '', '## Visual review checklist - UNMEASURED', '', 'These checks require visual judgment. Do not present them as measured scores until a reviewer inspects the evidence.', '');
  for (const item of VISUAL_CHECKLIST) lines.push(`- [ ] ${item}`);
  lines.push('', '## Journey evidence', '');
  for (const scene of data?.scenes || []) lines.push(`- **${scene.label || 'Scene'}** - ${scene.url || 'URL unavailable'} - ${scene.screenshot ? path.basename(scene.screenshot) : 'screenshot unavailable'}`);
  if (!(data?.scenes || []).length) lines.push('No scene screenshots were captured.');
  lines.push('', '## Next proof run', '', '1. Resolve hard gates first, then the lowest-scoring measured items.', '2. Complete the unmeasured visual-review checklist against the video and screenshots.', '3. Re-run the same target and journey after fixes.', '4. Use new measured score deltas plus new visual evidence; do not claim improvement from code changes alone.', '');
  return lines.join('\n');
}

export function buildAiRemediation(score, data, comparison) {
  const timing = timingEvidence(data, score);
  const scenes = sceneEvidence(data);
  const rows = priorities(score);
  const lines = [
    '# UI Demo Studio - AI remediation brief',
    '',
    `**Decision:** ${decisionSummary(score)}`,
    '',
    `Overall: **${scoreValue(score?.overall_score)}/100 (${score?.grade || 'n/a'})**${comparison ? ` - previous ${scoreValue(comparison.previous_overall)} -> current ${scoreValue(comparison.current_overall)} (${signed(comparison.overall_delta)})` : ''}`,
    ...SCORE_AREAS.filter((area) => score?.scores?.[area] !== undefined).map((area) => `- ${area.toUpperCase()}: **${scoreValue(score.scores[area])}**${comparison ? ` (${signed(deltaFor(comparison, area))})` : ''}`),
    '',
    '## Evidence confidence',
    '',
    `- Video timing: ${timing.video === null ? 'encoded duration not measured' : `${timing.video}s measured`} / ${timing.target === null ? 'target unavailable' : `${timing.target}s target`}${timing.delta === null ? '' : ` (${signed(timing.delta, 2)}s delta)`}. Recorder window: ${timing.recording === null ? 'unavailable' : `${timing.recording}s`}; finalization overhead: ${timing.finalize === null ? 'unavailable' : `${timing.finalize}s`}.`,
    `- Scene coverage: ${scenes.captured} captured, ${scenes.distinct} distinct URL states, ${scenes.screenshots} screenshot assets available, ${scenes.requested} requested guided labels, ${scenes.failed} recorded missing/failed journey events.`,
    '- Deterministic benchmark rows below are **measured/derived or measured/proxy** and include their evidence type.',
    '- The visual-review checklist is **UNMEASURED** until the video/screenshots are actually inspected.',
    '',
    '## Hard gates - fix before cosmetic work',
    '',
  ];
  if (!score?.gates?.length) lines.push('No hard gate was triggered.', '');
  else {
    for (const gate of score.gates) lines.push(`- **BLOCKER - ${gate.effect}**: ${gate.reason} Why it matters: ${gateWhy(gate)}`);
    lines.push('');
  }
  lines.push('## Ordered remediation priorities', '');
  if (!rows.length) lines.push('No measured benchmark item is below 85. Move to the unmeasured visual review and product-specific acceptance checks.', '');
  else {
    rows.forEach(({ area, metric }, index) => {
      lines.push(`${index + 1}. **${impact(metric.score)} impact - ${area.toUpperCase()} - ${metric.label}: ${scoreValue(metric.score)}/100**`, `   - Evidence: **${evidenceType(metric)}** (${metric.source || 'heuristic'})`, `   - Observed: \`${JSON.stringify(metric.observed ?? null)}\``, `   - Target: ${metric.target}`, '');
    });
  }
  lines.push('## Visual review checklist - UNMEASURED', '', 'Inspect the actual video and scene screenshots before checking these off. Give concise visual evidence for each judgment; do not manufacture a numeric score from DOM telemetry.', '');
  for (const item of VISUAL_CHECKLIST) lines.push(`- [ ] ${item}`);
  lines.push('', '## Required next proof', '', 'Fix blockers first, then the highest-impact measured root causes. Re-run the same target and journey. Improvement requires new measured deltas plus visual evidence; a code diff by itself is not proof.', '');
  return lines.join('\n');
}

function deltaMarkup(comparison, area) {
  const delta = deltaFor(comparison, area);
  if (delta === null) return '<span class="muted">no baseline</span>';
  const cls = delta > 0 ? 'up' : delta < 0 ? 'down' : 'flat';
  return `<span class="delta ${cls}">${esc(signed(delta))}</span>`;
}

function priorityTableHtml(score) {
  const rows = priorities(score);
  if (!rows.length) return '<p class="empty">No measured benchmark item is below 85. Continue with the unmeasured visual review and product-specific acceptance checks.</p>';
  return `<div class="table-wrap"><table><thead><tr><th>Impact</th><th>Area</th><th>Benchmark</th><th>Score</th><th>Evidence</th><th>Observed</th><th>Target</th></tr></thead><tbody>${rows.map(({ area, metric }) => `<tr><td><span class="impact ${impact(metric.score).toLowerCase()}">${impact(metric.score)}</span></td><td>${esc(area.toUpperCase())}</td><td><b>${esc(metric.label)}</b></td><td class="number">${esc(scoreValue(metric.score))}</td><td><span class="evidence">${esc(evidenceType(metric))}</span><small>${esc(metric.source || 'heuristic')}</small></td><td><code>${esc(JSON.stringify(metric.observed ?? null))}</code></td><td>${esc(metric.target)}</td></tr>`).join('')}</tbody></table></div>`;
}

export function buildHtmlReport(data, score, comparison) {
  const video = data?.video_path ? path.basename(data.video_path) : '';
  const timing = timingEvidence(data, score);
  const scenes = sceneEvidence(data);
  const gateCount = Array.isArray(score?.gates) ? score.gates.length : 0;
  const validity = score?.validity?.status || 'not_applicable';
  const scoreTiles = SCORE_AREAS.filter((area) => score?.scores?.[area] !== undefined).map((area) => `<div class="tile"><small>${esc(area)}</small><div><b>${esc(scoreValue(score.scores[area]))}</b>${comparison ? deltaMarkup(comparison, area) : '<span class="muted">first run</span>'}</div></div>`).join('');
  const gates = gateCount ? score.gates.map((gate) => `<article class="gate"><div class="eyebrow">BLOCKER</div><h3>${esc(gate.effect)}</h3><p>${esc(gate.reason)}</p><p><b>Why it matters:</b> ${esc(gateWhy(gate))}</p><code>${esc(gate.id)}</code></article>`).join('') : '<div class="ok-card"><b>No hard score gate triggered.</b><p>Continue with the lowest measured scores and the unmeasured visual-review checklist.</p></div>';
  const shots = (data?.scenes || []).map((scene, index) => scene?.screenshot ? `<figure><img loading="lazy" src="./${esc(path.basename(scene.screenshot))}" alt="Scene ${index + 1}: ${esc(scene.label || 'captured UI state')}"><figcaption><b>${esc(scene.label || `Scene ${index + 1}`)}</b><small>${esc(scene.url || '')}</small></figcaption></figure>` : `<figure class="missing-shot"><div class="empty"><b>Screenshot unavailable</b><p>This scene remains in coverage counts, but its image asset is not present in the report bundle.</p></div><figcaption><b>${esc(scene.label || `Scene ${index + 1}`)}</b><small>${esc(scene.url || '')}</small></figcaption></figure>`).join('') || '<p class="empty">No scene screenshots were captured.</p>';
  const checklist = VISUAL_CHECKLIST.map((item) => `<li><span aria-hidden="true">□</span>${esc(item)}</li>`).join('');
  const overallDelta = comparison ? `<span class="overall-delta">${esc(signed(comparison.overall_delta))} vs previous</span>` : '<span class="overall-delta muted">first scored run</span>';
  const timingDelta = timing.delta === null ? 'not measured' : `${signed(timing.delta, 2)}s`;
  return `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>UI Demo Studio report</title>
<style>
:root{color-scheme:dark;--bg:#080b14;--surface:#111625;--surface2:#171d2e;--line:#2a344d;--text:#eef2fb;--muted:#aab6cb;--accent:#a78bfa;--good:#72d6a5;--warn:#f0bd69;--bad:#ff8d9a}*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 80% -20%,#29214c 0,transparent 34%),var(--bg);color:var(--text);font:14px/1.55 system-ui,-apple-system,Segoe UI,sans-serif}main{max-width:1240px;margin:auto;padding:30px}.hero{display:grid;grid-template-columns:minmax(0,1.45fr) minmax(310px,.55fr);gap:18px}.card,.tile,figure,.gate,.ok-card{background:color-mix(in srgb,var(--surface) 94%,transparent);border:1px solid var(--line);border-radius:18px}.card{padding:20px}.eyebrow{font-size:11px;font-weight:800;letter-spacing:.12em;text-transform:uppercase;color:var(--accent)}h1{font-size:clamp(28px,4vw,44px);line-height:1.05;margin:8px 0 10px}h2{margin:34px 0 12px;font-size:22px}h3{margin:5px 0 6px}p,small{color:var(--muted)}.decision{font-size:16px;color:var(--text);max-width:72ch}.score-box{display:flex;align-items:flex-end;gap:12px}.score{font-size:64px;line-height:.9;font-weight:850;color:var(--accent)}.score small{font-size:14px}.overall-delta{font-weight:750}.tiles{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px;margin-top:16px}.tile{padding:12px}.tile small{display:block;text-transform:uppercase;letter-spacing:.08em}.tile b{font-size:27px}.delta{margin-left:8px;font-weight:750}.up{color:var(--good)}.down{color:var(--bad)}.flat,.muted{color:var(--muted)}video,img{display:block;width:100%;border-radius:13px}.video-wrap{margin-top:14px}.evidence-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}.evidence-card{background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:14px}.evidence-card small{display:block;text-transform:uppercase;letter-spacing:.07em}.evidence-card b{display:block;font-size:18px;margin-top:3px}.gate{padding:16px;margin:10px 0;border-color:#713541;background:#301820}.gate .eyebrow{color:var(--bad)}.ok-card{padding:16px;border-color:#315d4b;background:#11271f}.ok-card b{color:var(--good)}.legend{display:flex;flex-wrap:wrap;gap:8px}.legend span,.evidence,.impact{display:inline-flex;border:1px solid var(--line);border-radius:999px;padding:3px 8px;font-size:12px}.legend .unmeasured{border-color:#7a6338;color:#f0cf8d}.table-wrap{overflow:auto;border:1px solid var(--line);border-radius:16px}table{width:100%;border-collapse:collapse;min-width:900px;background:var(--surface)}td,th{padding:11px 12px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}th{font-size:11px;text-transform:uppercase;letter-spacing:.07em;color:var(--muted)}td small{display:block}.number{font-weight:800;font-size:17px}.impact.high{border-color:#713541;color:var(--bad)}.impact.medium{border-color:#7a6338;color:var(--warn)}.impact.low{color:var(--muted)}code{font:12px/1.4 ui-monospace,SFMono-Regular,Consolas,monospace;white-space:normal;overflow-wrap:anywhere;color:#d8ddec}.checklist{margin:0;padding:0;list-style:none;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px}.checklist li{display:flex;gap:9px;background:var(--surface);border:1px solid var(--line);border-radius:13px;padding:12px}.checklist li span{color:var(--warn);font-size:18px}.shots{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px}.shots figure{margin:0;padding:10px}.shots figcaption{display:grid;gap:4px;padding:8px 2px 2px;overflow-wrap:anywhere}.empty{background:var(--surface);border:1px dashed var(--line);border-radius:14px;padding:16px}.next{border-left:3px solid var(--accent);padding-left:15px}.next li{margin:5px 0}@media(max-width:900px){main{padding:16px}.hero{grid-template-columns:1fr}.evidence-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:560px){main{padding:11px}.card{padding:15px}.tiles,.evidence-grid,.checklist{grid-template-columns:1fr}.score{font-size:54px}}
</style></head><body><main>
<section class="hero"><div class="card"><div class="eyebrow">UI Demo Studio · evidence report</div><h1>${esc(data?.target_input || data?.target_url || 'Target')}</h1><p class="decision"><b>Decision:</b> ${esc(decisionSummary(score))}</p><p>${esc(data?.target_url || '')}</p><div class="video-wrap">${video ? `<video controls playsinline preload="metadata" src="./${esc(video)}"></video>` : '<p class="empty">Video not produced for this run.</p>'}</div></div><aside class="card"><div class="eyebrow">Overall benchmark</div><div class="score-box"><div class="score">${esc(scoreValue(score?.overall_score))}<small>/100 · ${esc(score?.grade || 'n/a')}</small></div></div>${overallDelta}<div class="tiles">${scoreTiles}</div></aside></section>
<h2>Evidence at a glance</h2><section class="evidence-grid"><div class="evidence-card"><small>Hard gates</small><b>${gateCount}</b><span>${gateCount ? 'resolve first' : 'none active'}</span></div><div class="evidence-card"><small>Video duration</small><b>${timing.video === null ? 'Not measured' : `${timing.video}s`}</b><span>${timing.target === null ? 'target unavailable' : `${timing.target}s target · ${timingDelta} delta`}</span></div><div class="evidence-card"><small>Scene coverage</small><b>${scenes.captured} captured</b><span>${scenes.distinct} distinct URL states · ${scenes.screenshots} screenshots · ${scenes.mode}</span></div><div class="evidence-card"><small>Assessment validity</small><b>${esc(validity)}</b><span>${esc(score?.validity?.reason || score?.validity?.expected || 'No project-identity exception reported.')}</span></div></section>
<p><b>Timing semantics:</b> target duration is configuration; encoded video duration is measured from video metadata; recorder elapsed window (${timing.recording === null ? 'unavailable' : `${timing.recording}s`}) measures the recording window; finalization overhead (${timing.finalize === null ? 'unavailable' : `${timing.finalize}s`}) is post-record processing and is not part of video duration.</p>
<p><b>Scene coverage:</b> ${scenes.captured} captured scene(s), ${scenes.distinct} distinct URL state(s), ${scenes.screenshots} screenshot asset(s) available in this report bundle, ${scenes.requested} requested guided label(s), ${scenes.failed} recorded missing/failed journey event(s). Scene count is evidence coverage, not task-success proof.</p>
<h2>Hard gates</h2>${gates}
<h2>Highest-impact measured fixes</h2><div class="legend"><span>Measured / derived</span><span>Measured / proxy</span><span>Derived / fallback</span><span class="unmeasured">UNMEASURED visual review kept separate</span></div>${priorityTableHtml(score)}
<h2>Visual review checklist <span class="eyebrow">UNMEASURED</span></h2><p>Inspect the actual video and screenshots. These judgments are intentionally not presented as deterministic benchmark measurements.</p><ul class="checklist">${checklist}</ul>
<h2>Journey evidence</h2><div class="shots">${shots}</div>
<h2>Next proof run</h2><ol class="next"><li>Resolve hard gates before cosmetic polish.</li><li>Fix the lowest-scoring measured root causes, not just symptoms.</li><li>Complete the unmeasured visual-review checklist against this run's evidence.</li><li>Re-run the same target and journey and compare measured deltas plus new video/screenshots.</li></ol>
</main></body></html>`;
}

export const reportingInternals = { evidenceType, impact, priorities, sceneEvidence, timingEvidence, gateWhy, decisionSummary };
