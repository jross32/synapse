import assert from 'node:assert/strict';
import { buildAiRemediation, buildHumanMarkdown, buildHtmlReport, reportingInternals } from './reporting.mjs';

const data = {
  target_input: 'demo-<unsafe>',
  target_url: 'http://127.0.0.1:9999/',
  duration_seconds: 12,
  recording_elapsed_seconds: 12.1,
  video_finalize_seconds: 0.7,
  journey_mode: 'guided',
  journey: ['Dashboard', 'Settings'],
  findings: [{ code: 'journey.step_missing', occurrences: 1 }],
  video_path: 'C:/tmp/demo.mp4',
  scenes: [
    { label: 'Opening view', url: 'http://127.0.0.1:9999/', screenshot: 'C:/tmp/scene-0.png' },
    { label: 'Dashboard', url: 'http://127.0.0.1:9999/dashboard', screenshot: 'C:/tmp/scene-1.png' },
  ],
};

const score = {
  overall_score: 58,
  grade: 'F',
  target_duration_seconds: 12,
  video_duration_seconds: 12.42,
  video_duration_delta_seconds: 0.42,
  validity: { status: 'verified', expected: 'Demo' },
  scores: { ui: 82, ux: 49, performance: 77, accessibility: 73, reliability: 91 },
  gates: [{ id: 'ux.task_failure', effect: 'UX capped at 49', reason: 'Fewer than half of requested journey steps completed.' }],
  metrics: {
    ui: [{ id: 'ui.hierarchy', label: 'Information hierarchy', score: 82, observed: { heading_jumps: 1 }, target: 'Logical heading structure', source: 'heuristic' }],
    ux: [{ id: 'ux.task_success', label: 'Task / journey success', score: 49, observed: { requested: 2, failed: 1 }, target: 'Requested journey completes', source: 'heuristic' }],
    performance: [{ id: 'perf.inp', label: 'Interaction responsiveness', score: 61, observed: 420, target: 'Good INP <=200ms', source: 'Core Web Vitals / response proxy' }],
    accessibility: [{ id: 'a11y.names', label: 'Accessible names & labels', score: 73, observed: { unnamed: 2 }, target: 'Every control has a useful accessible name', source: 'heuristic' }, { id: 'a11y.images', label: 'Image alternatives', score: 0, status: 'not_applicable', observed: { images: 0 }, target: 'Images have alternatives', source: 'heuristic' }],
    reliability: [{ id: 'reliability.runtime', label: 'Runtime correctness', score: 91, observed: { page_errors: 0 }, target: 'Zero unhandled errors', source: 'heuristic' }],
  },
};

const comparison = {
  previous_overall: 53,
  current_overall: 58,
  overall_delta: 5,
  score_deltas: { ui: 2, ux: -1, performance: 7, accessibility: 0, reliability: 1 },
};

const markdown = buildHumanMarkdown(data, score, comparison);
const remediation = buildAiRemediation(score, data, comparison);
const html = buildHtmlReport(data, score, comparison);

assert.match(markdown, /Decision summary/);
assert.match(markdown, /previous 53 -> current 58 \(\+5\)/);
assert.match(markdown, /Measured \/ proxy/);
assert.match(markdown, /UNMEASURED visual review/);
assert.match(markdown, /Encoded video duration: 12\.42s/);
assert.match(markdown, /Video finalization overhead: 0\.7s/);
assert.match(markdown, /Captured evidence: \*\*2 scenes\*\*/);
assert.match(markdown, /BLOCKER - UX capped at 49/);
assert.ok(markdown.indexOf('Task / journey success') < markdown.indexOf('Information hierarchy'), 'lowest-score priority should appear first');

assert.match(remediation, /Hard gates - fix before cosmetic work/);
assert.match(remediation, /High impact - UX - Task \/ journey success: 49\/100/);
assert.match(remediation, /Evidence: \*\*Measured \/ proxy\*\*/);
assert.match(remediation, /Visual review checklist - UNMEASURED/);
assert.doesNotMatch(remediation, /High impact - ACCESSIBILITY - Image alternatives/);

assert.match(html, /UI Demo Studio · evidence report/);
assert.match(html, /demo-&lt;unsafe&gt;/);
assert.doesNotMatch(html, /demo-<unsafe>/);
assert.match(html, /\+5 vs previous/);
assert.match(html, /UNMEASURED visual review kept separate/);
assert.match(html, /alt="Scene 1: Opening view"/);
assert.match(html, /12\.42s/);
assert.match(html, /0\.7s/);
assert.match(html, /BLOCKER/);

for (const output of [markdown, remediation, html]) {
  assert.ok(!output.includes('\uFFFD'), 'report output must not contain Unicode replacement characters');
  assert.ok(!output.includes('\x1a'), 'report output must not contain SUB/control-arrow corruption');
}

assert.equal(reportingInternals.evidenceType(score.metrics.performance[0]), 'Measured / proxy');
assert.equal(reportingInternals.impact(49), 'High');
assert.equal(reportingInternals.sceneEvidence(data).distinct, 2);

console.log('reporting.test.mjs: PASS');
