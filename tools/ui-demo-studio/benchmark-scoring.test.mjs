import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import { buildScorecard, compareScorecards } from './benchmark-scoring.mjs';

const fixtureFile = new URL('./fixtures/scoring-adversarial.json', import.meta.url);
const fixture = JSON.parse(await readFile(fixtureFile, 'utf8'));

function audit(overrides = {}) {
  return {
    title: 'Fixture App',
    url: 'http://fixture/',
    horizontal_overflow_px: 0,
    offscreen_element_count: 0,
    visible_interactive_count: 8,
    usable_interactive_count: 8,
    disabled_interactive_count: 0,
    visible_button_count: 3,
    visible_link_count: 5,
    visible_dialog_count: 0,
    dialogs_without_dismiss_count: 0,
    unnamed_interactive_count: 0,
    unlabeled_input_count: 0,
    wcag_small_target_count: 0,
    enhanced_small_target_count: 0,
    visible_image_count: 0,
    missing_alt_count: 0,
    duplicate_id_count: 0,
    heading_count: 3,
    heading_jump_count: 0,
    contrast_failure_count: 0,
    contrast_checked_count: 20,
    tiny_text_count: 0,
    visible_text_element_count: 20,
    button_consistency_score: 100,
    spacing_consistency_score: 100,
    navigation_landmark_count: 1,
    visible_navigation_link_count: 5,
    visible_menu_button_count: 0,
    explicit_return_control_count: 1,
    feedback_element_count: 1,
    has_return_affordance: true,
    dom_content_loaded_ms: 100,
    load_ms: 120,
    ttfb_ms: 40,
    vitals: { cls: 0, lcp: 150, inp: 50, longTaskMs: 0, mutations: 1 },
    ...overrides
  };
}

function materialize(spec) {
  const sceneUrls = spec.scene_urls || ['http://fixture/'];
  const data = {
    target_input: 'Fixture App',
    target_url: 'http://fixture/',
    viewport: '1280x720',
    journey_mode: spec.mode,
    journey: spec.journey || [],
    findings: spec.findings || [],
    scenes: sceneUrls.map((url, index) => ({ index, url, label: index ? `Scene ${index}` : 'Opening view' }))
  };
  if (!spec.omit_runtime_capture) {
    data.page_errors = [];
    data.console_errors = [];
    data.request_failures = [];
    data.bad_responses = [];
  }
  if (spec.probe_failure) {
    return { data, desktop: [{ url: data.target_url, error: 'connection refused' }], mobile: [{ url: data.target_url, error: 'connection refused' }], interaction: null };
  }
  const base = audit();
  if (spec.strip_performance) {
    delete base.load_ms;
    delete base.ttfb_ms;
    delete base.dom_content_loaded_ms;
    base.vitals = {};
  }
  if (spec.strip_contrast) {
    base.contrast_failure_count = 0;
    base.contrast_checked_count = 0;
  }
  const desktop = sceneUrls.map((url) => ({ url, audit: { ...base, url } }));
  const mobile = sceneUrls.map((url) => ({ url, audit: { ...base, url } }));
  const interaction = spec.strip_performance ? null : { success: true, response_signal_ms: 80, explicit_return_affordance: true };
  return { data, desktop, mobile, interaction };
}

function findMetric(score, id) {
  return Object.values(score.metrics).flat().find((item) => item.id === id);
}

for (const spec of fixture.cases) {
  test(spec.name, () => {
    const input = materialize(spec);
    const score = buildScorecard(input.data, input.desktop, input.mobile, input.interaction, { status: 'verified', expected: 'Fixture App', observed_titles: ['Fixture App'] });

    if (spec.expected_gate) assert(score.gates.some((gate) => gate.id === spec.expected_gate), `missing gate ${spec.expected_gate}`);
    if (Number.isFinite(spec.max_overall)) assert(score.overall_score <= spec.max_overall, `overall ${score.overall_score} > ${spec.max_overall}`);
    if (Object.hasOwn(spec, 'expect_performance')) assert.equal(score.scores.performance, spec.expect_performance);
    if (Object.hasOwn(spec, 'expect_reliability')) assert.equal(score.scores.reliability, spec.expect_reliability);
    if (spec.expect_task_status) assert.equal(findMetric(score, 'ux.task_success')?.status, spec.expect_task_status);
    if (spec.expect_tour_status) assert.equal(findMetric(score, 'ux.tour_coverage')?.status, spec.expect_tour_status);
    if (spec.expect_contrast_status) {
      const contrast = findMetric(score, 'a11y.contrast');
      assert.equal(contrast?.status, spec.expect_contrast_status);
      assert.equal(contrast?.score, null, 'unmeasured contrast must not become a perfect score');
    }
    if (spec.name.includes('guided-single-step')) assert.notEqual(score.grade, 'A');
  });
}

test('comparison requires identical scoring version and benchmark fingerprint', () => {
  const spec = fixture.cases.find((item) => item.name === 'automatic-tour-is-not-guided-task-success');
  const input = materialize(spec);
  const before = buildScorecard(input.data, input.desktop, input.mobile, input.interaction, { status: 'verified' });
  const after = structuredClone(before);
  after.overall_score = Math.max(0, before.overall_score - 2);
  after.scores.ui = Math.max(0, before.scores.ui - 3);
  const comparison = compareScorecards(before, after);
  assert(comparison, 'same benchmark context should be comparable');
  assert.equal(comparison.overall_delta, -2);
  assert.equal(comparison.score_deltas.ui, -3);

  const incompatible = structuredClone(after);
  incompatible.benchmark_context = { ...incompatible.benchmark_context, fingerprint: incompatible.benchmark_context.fingerprint + ':different-journey' };
  assert.equal(compareScorecards(before, incompatible), null, 'different benchmark context must not emit a delta');

  const oldMethod = structuredClone(before);
  oldMethod.version = '2.1';
  assert.equal(compareScorecards(oldMethod, after), null, 'different scorecard methodology must not emit a delta');
});


test('explicit null performance evidence stays unmeasured', () => {
  const base = audit({ load_ms: null, ttfb_ms: null, dom_content_loaded_ms: null, vitals: { cls: null, lcp: null, inp: null, longTaskMs: null, mutations: 0 } });
  const data = { target_input: 'Fixture App', target_url: 'http://fixture/', viewport: '1280x720', journey_mode: 'automatic-safe-tour', journey: [], findings: [], scenes: [{ index: 0, url: 'http://fixture/', label: 'Opening view' }], page_errors: [], console_errors: [], request_failures: [], bad_responses: [] };
  const desktop = [{ url: data.target_url, audit: base }];
  const mobile = [{ url: data.target_url, audit: { ...base } }];
  const score = buildScorecard(data, desktop, mobile, { success: true, response_signal_ms: null, explicit_return_affordance: true }, { status: 'verified' });
  for (const id of ['perf.lcp','perf.inp','perf.cls','perf.long_tasks','perf.ttfb','ux.feedback']) assert.equal(findMetric(score, id)?.score, null, id + ' should remain unmeasured');
  assert.notEqual(score.scores.performance, 100, 'explicit null performance evidence must not become perfect telemetry');
});


test('failed benchmark interaction probe stays unmeasured instead of punishing product UX', () => {
  const base = audit();
  const data = { target_input: 'Fixture App', target_url: 'http://fixture/', viewport: '1280x720', journey_mode: 'automatic-safe-tour', journey: [], findings: [], scenes: [{ index: 0, url: 'http://fixture/', label: 'Opening view' }, { index: 1, url: 'http://fixture/details', label: 'Details' }], page_errors: [], console_errors: [], request_failures: [], bad_responses: [] };
  const desktop = data.scenes.map((scene) => ({ url: scene.url, audit: { ...base, url: scene.url } }));
  const mobile = data.scenes.map((scene) => ({ url: scene.url, audit: { ...base, url: scene.url } }));
  const score = buildScorecard(data, desktop, mobile, { success: false, label: 'Stocks', response_signal_ms: null }, { status: 'verified' });
  assert.equal(findMetric(score, 'ux.feedback')?.score, null);
  assert.equal(findMetric(score, 'ux.feedback')?.status, 'not_measured');
  assert.equal(findMetric(score, 'ux.reversibility')?.score, null);
  assert.equal(findMetric(score, 'ux.reversibility')?.status, 'not_measured');
  assert.equal(score.measurement.dimensions.ux.status, 'partial');
  assert(score.measurement.dimensions.ux.coverage < 100);
});


test('keyboard focus probe changes accessibility score without faking conformance', () => {
  const spec = fixture.cases.find((item) => item.name === 'automatic-tour-is-not-guided-task-success');
  const input = materialize(spec);
  const goodKeyboard = { focusable_count: 3, expected_sample: 3, reached_count: 3, tested_focus_steps: 3, visible_focus_count: 3, not_obscured_count: 3, dialog_count: 0, dialog_focus_contained: null, dialog_escape_dismissed: null };
  const badKeyboard = { ...goodKeyboard, visible_focus_count: 0 };
  const good = buildScorecard(input.data, input.desktop, input.mobile, input.interaction, { status: 'verified' }, goodKeyboard);
  const bad = buildScorecard(input.data, input.desktop, input.mobile, input.interaction, { status: 'verified' }, badKeyboard);
  assert.equal(findMetric(good, 'a11y.keyboard_focus')?.score, 100);
  assert.equal(findMetric(bad, 'a11y.keyboard_focus')?.score, 65);
  assert(good.scores.accessibility > bad.scores.accessibility, 'missing focus indication should lower accessibility');
});

test('modal Escape and focus containment contribute to reversibility without replacing trapped-dialog gate', () => {
  const spec = fixture.cases.find((item) => item.name === 'automatic-tour-is-not-guided-task-success');
  const input = materialize(spec);
  for (const row of [...input.desktop, ...input.mobile]) {
    row.audit.visible_dialog_count = 1;
    row.audit.dialogs_without_dismiss_count = 0;
  }
  const goodKeyboard = { focusable_count: 2, expected_sample: 2, reached_count: 2, tested_focus_steps: 2, visible_focus_count: 2, not_obscured_count: 2, dialog_count: 1, dialog_focus_escape_count: 0, dialog_focus_contained: true, dialog_escape_dismissed: true };
  const badKeyboard = { ...goodKeyboard, dialog_focus_escape_count: 1, dialog_focus_contained: false, dialog_escape_dismissed: false };
  const good = buildScorecard(input.data, input.desktop, input.mobile, input.interaction, { status: 'verified' }, goodKeyboard);
  const bad = buildScorecard(input.data, input.desktop, input.mobile, input.interaction, { status: 'verified' }, badKeyboard);
  assert.equal(findMetric(good, 'ux.dialog_keyboard')?.score, 100);
  assert.equal(findMetric(bad, 'ux.dialog_keyboard')?.score, 0);
  assert(good.scores.ux > bad.scores.ux, 'keyboard-trapping modal should lower UX reversibility');
  assert.equal(bad.gates.some((gate) => gate.id === 'ux.trapped_dialog'), false, 'keyboard weakness alone should not impersonate the no-dismiss hard gate');
});


test('desktop navigation hidden on mobile without a menu control scores zero', () => {
  const spec = fixture.cases.find((item) => item.name === 'automatic-tour-is-not-guided-task-success');
  const input = materialize(spec);
  for (const row of input.desktop) { row.audit.visible_navigation_link_count = 4; row.audit.visible_menu_button_count = 0; }
  for (const row of input.mobile) { row.audit.visible_navigation_link_count = 0; row.audit.visible_menu_button_count = 0; }
  const broken = buildScorecard(input.data, input.desktop, input.mobile, input.interaction, { status: 'verified' });
  assert.equal(findMetric(broken, 'ui.mobile_navigation')?.score, 0);
  for (const row of input.mobile) row.audit.visible_menu_button_count = 1;
  const fixed = buildScorecard(input.data, input.desktop, input.mobile, input.interaction, { status: 'verified' });
  assert.equal(findMetric(fixed, 'ui.mobile_navigation')?.score, 100);
  assert(fixed.scores.ui > broken.scores.ui, 'restoring a mobile menu should raise UI score');
});
