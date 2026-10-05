const SCORECARD_VERSION = '3.4';

const clamp = (value) => Number.isFinite(value) ? Math.max(0, Math.min(100, value)) : null;
const roundScore = (value) => {
  const n = clamp(value);
  return n === null ? null : Math.round(n);
};

function weighted(parts) {
  let sum = 0;
  let measuredWeight = 0;
  let totalWeight = 0;
  for (const [score, weight] of parts) {
    if (!Number.isFinite(weight) || weight <= 0) continue;
    totalWeight += weight;
    if (!Number.isFinite(score)) continue;
    sum += score * weight;
    measuredWeight += weight;
  }
  return {
    score: measuredWeight ? roundScore(sum / measuredWeight) : null,
    measured_weight: measuredWeight,
    total_weight: totalWeight,
    coverage: totalWeight ? Math.round((measuredWeight / totalWeight) * 100) : 0
  };
}

function linear(value, good, poor) {
  if (!Number.isFinite(value)) return null;
  if (value <= good) return 100;
  if (value >= poor) return 0;
  return roundScore(((poor - value) / (poor - good)) * 100);
}

function passRate(failures, total) {
  if (!Number.isFinite(failures) || !Number.isFinite(total) || total <= 0) return null;
  return roundScore((1 - Math.min(total, Math.max(0, failures)) / total) * 100);
}

function successfulRows(rows) {
  return (Array.isArray(rows) ? rows : []).filter((row) => row && row.audit && !row.error);
}

function measuredNumbers(rows, getter) {
  return successfulRows(rows).map(getter).filter((value) => typeof value === 'number' && Number.isFinite(value));
}

function maxMetric(rows, key) {
  const vals = measuredNumbers(rows, (row) => row.audit?.[key]);
  return vals.length ? Math.max(...vals) : null;
}

function sumMetric(rows, key) {
  const vals = measuredNumbers(rows, (row) => row.audit?.[key]);
  return vals.length ? vals.reduce((a, b) => a + b, 0) : null;
}

function avgMetric(rows, key) {
  const vals = measuredNumbers(rows, (row) => row.audit?.[key]);
  return vals.length ? roundScore(vals.reduce((a, b) => a + b, 0) / vals.length) : null;
}

function vitalMax(rows, key) {
  const vals = measuredNumbers(rows, (row) => row.audit?.vitals?.[key]);
  return vals.length ? Math.max(...vals) : null;
}

function countFindings(data, predicate) {
  return (Array.isArray(data?.findings) ? data.findings : [])
    .filter(predicate)
    .reduce((n, finding) => n + Math.max(1, Number(finding?.occurrences) || 1), 0);
}

function metric(id, label, score, observed, target, source = 'heuristic', status = null) {
  const resolvedStatus = status || (Number.isFinite(score) ? 'measured' : 'not_measured');
  return {
    id,
    label,
    score: roundScore(score),
    status: resolvedStatus,
    observed,
    target,
    source
  };
}

function cap(score, maximum) {
  return Number.isFinite(score) ? Math.min(score, maximum) : score;
}

function dimensionScore(result, minimumCoverage = 50) {
  return result?.coverage >= minimumCoverage ? result.score : null;
}

function runtimeCaptureScore(data) {
  const pageKnown = Array.isArray(data?.page_errors);
  const consoleKnown = Array.isArray(data?.console_errors);
  return weighted([
    [pageKnown ? linear(data.page_errors.length, 0, 3) : null, 0.6],
    [consoleKnown ? linear(data.console_errors.length, 0, 8) : null, 0.4]
  ]);
}

function networkCaptureScore(data) {
  const reqKnown = Array.isArray(data?.request_failures);
  const responsesKnown = Array.isArray(data?.bad_responses);
  const five = responsesKnown ? data.bad_responses.filter((x) => Number(x?.status) >= 500).length : null;
  const four = responsesKnown ? data.bad_responses.filter((x) => Number(x?.status) >= 400 && Number(x?.status) < 500).length : null;
  return weighted([
    [reqKnown ? linear(data.request_failures.length, 0, 5) : null, 0.45],
    [responsesKnown ? linear(five, 0, 3) : null, 0.4],
    [responsesKnown ? linear(four, 0, 8) : null, 0.15]
  ]);
}

function gradeFor(overall, overallCoverage) {
  if (!Number.isFinite(overall) || overallCoverage < 60) return 'N/A';
  return overall >= 90 ? 'A' : overall >= 80 ? 'B' : overall >= 70 ? 'C' : overall >= 60 ? 'D' : 'F';
}

function benchmarkContext(data) {
  const journey = Array.isArray(data?.journey) ? data.journey.map((x) => String(x).trim().replace(/\s+/g, ' ')) : [];
  const context = {
    scorecard_version: SCORECARD_VERSION,
    target_url: String(data?.target_url || '').trim(),
    target_input: String(data?.target_input || '').trim(),
    journey_mode: String(data?.journey_mode || (journey.length ? 'guided' : 'automatic-safe-tour')),
    journey,
    viewport: String(data?.viewport || ''),
    duration_seconds: Number.isFinite(Number(data?.duration_seconds)) ? Number(data.duration_seconds) : null
  };
  return { ...context, fingerprint: JSON.stringify(context) };
}

export function buildScorecard(data, desktopRows, mobileRows, interaction, identity, keyboard = null) {
  const desktop = successfulRows(desktopRows);
  const mobile = successfulRows(mobileRows);
  const all = [...desktop, ...mobile];
  const opening = desktop[0]?.audit || null;
  const mobileOpening = mobile[0]?.audit || null;
  const gates = [];

  const desktopOverflow = maxMetric(desktop, 'horizontal_overflow_px');
  const mobileOverflow = maxMetric(mobile, 'horizontal_overflow_px');
  const offscreen = sumMetric(all, 'offscreen_element_count');
  const visualIntegrityParts = [];
  if (Number.isFinite(desktopOverflow)) visualIntegrityParts.push([linear(desktopOverflow, 2, 120), 0.35]);
  if (Number.isFinite(mobileOverflow)) visualIntegrityParts.push([linear(mobileOverflow, 2, 80), 0.45]);
  if (Number.isFinite(offscreen)) visualIntegrityParts.push([linear(offscreen, 0, 20), 0.20]);
  const visualIntegrity = weighted(visualIntegrityParts);

  const contrastFail = sumMetric(all, 'contrast_failure_count');
  const contrastChecked = sumMetric(all, 'contrast_checked_count');
  const tiny = sumMetric(all, 'tiny_text_count');
  const text = sumMetric(all, 'visible_text_element_count');
  const contrastScore = Number.isFinite(contrastChecked) && contrastChecked > 0 ? passRate(contrastFail || 0, contrastChecked) : null;
  const textSizeScore = Number.isFinite(text) && text > 0 ? passRate(tiny || 0, text) : null;
  const readability = weighted([[contrastScore, 0.75], [textSizeScore, 0.25]]);

  const buttonConsistency = avgMetric(all, 'button_consistency_score');
  const spacingConsistency = avgMetric(all, 'spacing_consistency_score');
  const consistency = weighted([[buttonConsistency, 0.65], [spacingConsistency, 0.35]]);

  const mobileTargets = sumMetric(mobile, 'visible_interactive_count');
  const mobileSmall = sumMetric(mobile, 'wcag_small_target_count');
  const targetScore = Number.isFinite(mobileTargets) && mobileTargets > 0 ? passRate(mobileSmall || 0, mobileTargets) : null;
  const desktopNavLinks = Number(opening?.visible_navigation_link_count);
  const mobileNavLinks = Number(mobileOpening?.visible_navigation_link_count);
  const mobileMenuButtons = Number(mobileOpening?.visible_menu_button_count);
  const mobileNavScore = Number.isFinite(desktopNavLinks) && desktopNavLinks > 0
    ? ((Number.isFinite(mobileNavLinks) && mobileNavLinks > 0) || (Number.isFinite(mobileMenuButtons) && mobileMenuButtons > 0) ? 100 : 0)
    : null;
  const responsive = weighted([[Number.isFinite(mobileOverflow) ? linear(mobileOverflow, 2, 80) : null, 0.45], [targetScore, 0.35], [mobileNavScore, 0.20]]);

  const headingJumps = sumMetric(all, 'heading_jump_count');
  const headings = sumMetric(all, 'heading_count');
  const hierarchy = Number.isFinite(headings) && headings > 0 ? passRate(headingJumps || 0, Math.max(1, headings - 1)) : null;

  const uiResult = weighted([
    [visualIntegrity.score, 0.28],
    [readability.score, 0.24],
    [consistency.score, 0.18],
    [responsive.score, 0.20],
    [hierarchy, 0.10]
  ]);
  let ui = dimensionScore(uiResult);

  const visibleInteractive = Number(opening?.visible_interactive_count);
  const interactive = Number(opening?.usable_interactive_count);
  const disabledInteractive = Number(opening?.disabled_interactive_count);
  const buttons = Number(opening?.visible_button_count);
  const links = Number(opening?.visible_link_count);
  const completeness = Number.isFinite(interactive)
    ? (interactive === 0 ? 0 : interactive <= 2 ? 35 : (buttons === 0 && links <= 2 ? 50 : Math.min(100, 65 + interactive * 3)))
    : null;

  const requested = Array.isArray(data?.journey) ? data.journey.length : 0;
  const failedJourney = countFindings(data, (f) => ['journey.step_missing', 'journey.step_failed'].includes(String(f?.code)));
  const unsafeJourney = countFindings(data, (f) => String(f?.code) === 'journey.unsafe_step_skipped');
  const autoFailures = countFindings(data, (f) => String(f?.code) === 'journey.auto_step_failed');
  const distinctScenes = new Set((Array.isArray(data?.scenes) ? data.scenes : []).map((x) => String(x?.url || '').replace(/#.*$/, '')).filter(Boolean)).size;
  const guidedSafeRequested = Math.max(0, requested - unsafeJourney);
  const guidedTaskScore = requested > 0 && guidedSafeRequested > 0
    ? roundScore(Math.max(0, guidedSafeRequested - failedJourney) / guidedSafeRequested * 100)
    : null;
  const tourCoverage = requested === 0
    ? roundScore(Math.max(0, (distinctScenes >= 2 ? 100 : distinctScenes === 1 ? 50 : 0) - autoFailures * 20))
    : null;

  const dialogCount = sumMetric(all, 'visible_dialog_count');
  const noDismiss = sumMetric(all, 'dialogs_without_dismiss_count');
  const dialogScore = Number.isFinite(dialogCount) && dialogCount > 0 ? passRate(noDismiss || 0, dialogCount) : null;
  const responseMs = typeof interaction?.response_signal_ms === 'number' && Number.isFinite(interaction.response_signal_ms) ? interaction.response_signal_ms : null;
  const interactionMeasured = interaction?.success === true;
  const interactionProbeFailed = interaction?.success === false;
  const responseScore = Number.isFinite(responseMs) ? linear(responseMs, 200, 1000) : null;
  const returnScore = interactionMeasured ? (interaction.explicit_return_affordance ? 100 : 25) : null;

  const keyboardExpected = typeof keyboard?.expected_sample === 'number' && Number.isFinite(keyboard.expected_sample) ? keyboard.expected_sample : null;
  const keyboardReached = typeof keyboard?.reached_count === 'number' && Number.isFinite(keyboard.reached_count) ? keyboard.reached_count : null;
  const keyboardTested = typeof keyboard?.tested_focus_steps === 'number' && Number.isFinite(keyboard.tested_focus_steps) ? keyboard.tested_focus_steps : null;
  const keyboardVisible = typeof keyboard?.visible_focus_count === 'number' && Number.isFinite(keyboard.visible_focus_count) ? keyboard.visible_focus_count : null;
  const keyboardNotObscured = typeof keyboard?.not_obscured_count === 'number' && Number.isFinite(keyboard.not_obscured_count) ? keyboard.not_obscured_count : null;
  const keyboardReachScore = Number.isFinite(keyboardExpected) && keyboardExpected > 0 && Number.isFinite(keyboardReached)
    ? roundScore((Math.min(keyboardExpected, keyboardReached) / keyboardExpected) * 100) : null;
  const focusVisibleScore = Number.isFinite(keyboardTested) && keyboardTested > 0 && Number.isFinite(keyboardVisible)
    ? roundScore((keyboardVisible / keyboardTested) * 100) : null;
  const focusNotObscuredScore = Number.isFinite(keyboardTested) && keyboardTested > 0 && Number.isFinite(keyboardNotObscured)
    ? roundScore((keyboardNotObscured / keyboardTested) * 100) : null;
  const keyboardFocusResult = weighted([[keyboardReachScore, 0.35], [focusVisibleScore, 0.35], [focusNotObscuredScore, 0.30]]);
  const dialogEscapeScore = Number(keyboard?.dialog_count) > 0 && typeof keyboard?.dialog_escape_dismissed === 'boolean'
    ? (keyboard.dialog_escape_dismissed ? 100 : 0) : null;
  const dialogContainmentScore = Number(keyboard?.dialog_count) > 0 && typeof keyboard?.dialog_focus_contained === 'boolean'
    ? (keyboard.dialog_focus_contained ? 100 : 0) : null;
  const dialogKeyboardResult = weighted([[dialogEscapeScore, 0.45], [dialogContainmentScore, 0.55]]);
  const desktopAuditCount = desktop.length;
  const deadEnds = desktop.filter((x) => Number(x.audit?.usable_interactive_count) === 0 && !x.audit?.has_return_affordance).length;
  const deadEndScore = desktopAuditCount ? passRate(deadEnds, desktopAuditCount) : null;
  const recoveryParts = [[deadEndScore, 0.4]];
  const reversibilityParts = [[returnScore, 0.72]];
  if (Number.isFinite(dialogScore)) {
    recoveryParts.push([dialogScore, 0.6]);
    reversibilityParts.push([dialogScore, 0.28]);
  }
  if (Number.isFinite(dialogKeyboardResult.score)) {
    reversibilityParts.push([dialogKeyboardResult.score, 0.20]);
  }
  const recovery = weighted(recoveryParts);
  const reversibility = weighted(reversibilityParts);

  const uxResult = requested > 0
    ? weighted([[completeness, 0.20], [guidedTaskScore, 0.30], [responseScore, 0.15], [reversibility.score, 0.25], [recovery.score, 0.10]])
    : weighted([[completeness, 0.25], [tourCoverage, 0.10], [responseScore, 0.20], [reversibility.score, 0.30], [recovery.score, 0.15]]);
  let ux = dimensionScore(uxResult);

  if (Number.isFinite(interactive) && interactive === 0) {
    ux = 0;
    gates.push({ id: 'ux.no_interaction', effect: 'UX forced to 0; overall capped at 39', reason: 'App opening view exposes no usable interactive controls (controls may be absent, disabled, or inert).' });
  }
  if (Number.isFinite(noDismiss) && noDismiss > 0) {
    ux = cap(ux, 59);
    gates.push({ id: 'ux.trapped_dialog', effect: 'UX and overall capped at 59', reason: 'A visible dialog/modal has no detectable Close/Cancel/Done/Back control.' });
  }
  if (requested > 0 && unsafeJourney > 0) {
    gates.push({ id: 'benchmark.unsafe_guided_step', effect: 'Unsafe requested step excluded from app task score', reason: 'One or more requested guided steps were intentionally skipped by the demo safety policy; they are not counted as app failures.' });
  }
  if (requested > 0 && failedJourney > 0) {
    ux = cap(ux, 49);
    gates.push({ id: 'ux.guided_task_failure', effect: 'UX capped at 49; overall capped at 59', reason: `${failedJourney} required guided journey step(s) were missing or failed. A broken requested task cannot receive a high UX grade.` });
  }
  if (Number.isFinite(mobileOverflow) && mobileOverflow > 24) {
    ui = cap(ui, 64);
    gates.push({ id: 'ui.mobile_overflow', effect: 'UI capped at 64; overall capped at 69', reason: 'Mobile horizontal overflow exceeds 24px.' });
  }

  const lcp = vitalMax(desktop, 'lcp');
  const inp = vitalMax(desktop, 'inp');
  const cls = vitalMax(desktop, 'cls');
  const longTask = vitalMax(desktop, 'longTaskMs');
  const load = maxMetric(desktop, 'load_ms');
  const ttfb = maxMetric(desktop, 'ttfb_ms');
  const lcpOrLoad = Number.isFinite(lcp) ? lcp : load;
  const lcpScore = Number.isFinite(lcp) ? linear(lcp, 2500, 4000) : Number.isFinite(load) ? linear(load, 2500, 5000) : null;
  const inpOrResponse = Number.isFinite(inp) && inp > 0 ? inp : Number.isFinite(responseMs) ? responseMs : null;
  const inpScore = Number.isFinite(inp) && inp > 0 ? linear(inp, 200, 500) : Number.isFinite(responseMs) ? linear(responseMs, 200, 1000) : null;
  const performanceResult = weighted([
    [lcpScore, 0.32],
    [inpScore, 0.28],
    [Number.isFinite(cls) ? linear(cls, 0.1, 0.25) : null, 0.18],
    [Number.isFinite(longTask) ? linear(longTask, 150, 1600) : null, 0.12],
    [Number.isFinite(ttfb) ? linear(ttfb, 800, 1800) : null, 0.10]
  ]);
  const performance = dimensionScore(performanceResult);

  const unnamed = sumMetric(all, 'unnamed_interactive_count');
  const unlabeled = sumMetric(all, 'unlabeled_input_count');
  const totalInteractive = sumMetric(all, 'visible_interactive_count');
  const missingAlt = sumMetric(all, 'missing_alt_count');
  const images = sumMetric(all, 'visible_image_count');
  const hardTargets = sumMetric(all, 'wcag_small_target_count');
  const rawUnder24 = sumMetric(all, 'raw_under_24px_target_count');
  const spacingExceptions = sumMetric(all, 'target_spacing_exception_count');
  const inlineExceptions = sumMetric(all, 'inline_target_exception_count');
  const nameScore = Number.isFinite(totalInteractive) && totalInteractive > 0 ? passRate(Math.max(unnamed || 0, unlabeled || 0), totalInteractive) : null;
  const a11yContrastScore = Number.isFinite(contrastChecked) && contrastChecked > 0 ? passRate(contrastFail || 0, contrastChecked) : null;
  const a11yTargetScore = Number.isFinite(totalInteractive) && totalInteractive > 0 ? passRate(hardTargets || 0, totalInteractive) : null;
  const altScore = Number.isFinite(images) && images > 0 ? passRate(missingAlt || 0, images) : null;
  const accessibilityParts = [[nameScore, 0.22], [a11yContrastScore, 0.20], [a11yTargetScore, 0.16], [hierarchy, 0.10], [keyboardFocusResult.score, 0.22]];
  if (Number.isFinite(altScore)) accessibilityParts.push([altScore, 0.05]);
  if (Number.isFinite(dialogScore)) accessibilityParts.push([dialogScore, 0.025]);
  if (Number.isFinite(dialogKeyboardResult.score)) accessibilityParts.push([dialogKeyboardResult.score, 0.025]);
  const accessibilityResult = weighted(accessibilityParts);
  const accessibility = dimensionScore(accessibilityResult);

  const runtimeResult = runtimeCaptureScore(data);
  const networkResult = networkCaptureScore(data);
  const totalProbeRows = (Array.isArray(desktopRows) ? desktopRows.length : 0) + (Array.isArray(mobileRows) ? mobileRows.length : 0);
  const probeFailures = Math.max(0, totalProbeRows - desktop.length - mobile.length);
  const probeScore = totalProbeRows > 0 ? passRate(probeFailures, totalProbeRows) : null;
  const reliabilityResult = weighted([[runtimeResult.score, 0.45], [networkResult.score, 0.35], [probeScore, 0.20]]);
  let reliability = dimensionScore(reliabilityResult);

  if (identity?.status === 'mismatch') {
    reliability = cap(reliability, 20);
    gates.push({ id: 'target.identity_mismatch', effect: 'Assessment invalid / overall capped at 19', reason: (identity.reason || 'Resolved target identity does not match the requested Synapse project.') + ` Expected ${identity.expected}, detected ${identity.detected}.` });
  }

  const topLevel = weighted([[ui, 0.30], [ux, 0.30], [performance, 0.15], [accessibility, 0.15], [reliability, 0.10]]);
  const overallCoverage = roundScore(uiResult.coverage * 0.30 + uxResult.coverage * 0.30 + performanceResult.coverage * 0.15 + accessibilityResult.coverage * 0.15 + reliabilityResult.coverage * 0.10);
  let overall = topLevel.score;

  if (!desktop.length) {
    overall = 0;
    gates.push({ id: 'target.probe_failed', effect: 'Overall forced to 0', reason: 'No desktop target page could be loaded and audited, so the application assessment is invalid.' });
  }
  if (Number.isFinite(interactive) && interactive === 0) overall = cap(overall, 39);
  if (Number.isFinite(noDismiss) && noDismiss > 0) overall = cap(overall, 59);
  if (requested > 0 && failedJourney > 0) overall = cap(overall, 59);
  if (Number.isFinite(mobileOverflow) && mobileOverflow > 24) overall = cap(overall, 69);
  if (identity?.status === 'mismatch') overall = cap(overall, 19);

  const metrics = {
    ui: [
      metric('ui.visual_integrity', 'Visual integrity', visualIntegrity.score, { desktop_overflow_px: desktopOverflow, mobile_overflow_px: mobileOverflow, offscreen }, 'No overflow, clipping, or off-screen UI', 'heuristic', visualIntegrity.score === null ? 'not_measured' : visualIntegrity.coverage < 100 ? 'partial' : 'measured'),
      metric('ui.readability', 'Readability & contrast', readability.score, { contrast_failures: contrastFail, checked: contrastChecked, tiny_text: tiny, text_elements: text }, 'WCAG AA text contrast where the background is deterministically measurable; avoid tiny body text', 'heuristic', readability.score === null ? 'not_measured' : readability.coverage < 100 ? 'partial' : 'measured'),
      metric('ui.consistency', 'Component consistency', consistency.score, { button_consistency: buttonConsistency, spacing_consistency: spacingConsistency }, 'Consistent controls and spacing rhythm', 'heuristic', consistency.score === null ? 'not_measured' : consistency.coverage < 100 ? 'partial' : 'measured'),
      metric('ui.responsive', 'Responsive adaptation', responsive.score, { mobile_overflow_px: mobileOverflow, small_targets: mobileSmall, controls: mobileTargets, mobile_navigation_score: mobileNavScore }, 'No mobile overflow; controls remain usable; desktop navigation remains reachable on mobile', 'heuristic', responsive.score === null ? 'not_measured' : responsive.coverage < 100 ? 'partial' : 'measured'),
      metric('ui.mobile_navigation', 'Mobile navigation access', mobileNavScore, { desktop_navigation_links: Number.isFinite(desktopNavLinks) ? desktopNavLinks : null, mobile_navigation_links: Number.isFinite(mobileNavLinks) ? mobileNavLinks : null, mobile_menu_buttons: Number.isFinite(mobileMenuButtons) ? mobileMenuButtons : null }, 'If desktop exposes navigation links, mobile exposes visible navigation links or a visible menu/navigation control', 'responsive DOM heuristic', Number.isFinite(desktopNavLinks) && desktopNavLinks > 0 ? (mobileNavScore === null ? 'not_measured' : 'measured') : 'not_applicable'),
      metric('ui.hierarchy', 'Information hierarchy', hierarchy, { heading_jumps: headingJumps, headings }, 'Logical heading structure', 'heuristic', hierarchy === null ? 'not_measured' : 'measured')
    ],
    ux: [
      metric('ux.completeness', 'Interactive completeness', completeness, { opening_usable_interactives: Number.isFinite(interactive) ? interactive : null, opening_visible_interactives: Number.isFinite(visibleInteractive) ? visibleInteractive : null, disabled_or_inert: Number.isFinite(disabledInteractive) ? disabledInteractive : null, buttons: Number.isFinite(buttons) ? buttons : null, links: Number.isFinite(links) ? links : null }, 'Interactive app exposes clear usable actions'),
      metric('ux.task_success', 'Guided task success', guidedTaskScore, { mode: requested ? 'guided' : 'automatic-safe-tour', requested, unsafe_excluded: unsafeJourney, failed: failedJourney }, 'All safe requested guided journey steps complete', 'journey evidence', requested === 0 || guidedSafeRequested === 0 ? 'not_applicable' : 'measured'),
      metric('ux.tour_coverage', 'Automatic tour coverage', tourCoverage, { mode: requested ? 'guided' : 'automatic-safe-tour', captured_scenes: (Array.isArray(data?.scenes) ? data.scenes : []).length, distinct_scenes: distinctScenes, failed_auto_steps: autoFailures }, 'Automatic safe tour captures at least two distinct usable states without failed steps', 'journey evidence', requested > 0 ? 'not_applicable' : 'measured'),
      metric('ux.feedback', 'Responsiveness & feedback', responseScore, { response_signal_ms: Number.isFinite(responseMs) ? responseMs : null, interaction_attempted: interaction != null, interaction_probe_failed: interactionProbeFailed, interaction_label: interaction?.label || null }, 'Visible response signal <=200ms where measurable', 'browser interaction', responseScore === null ? 'not_measured' : 'measured'),
      metric('ux.reversibility', 'Navigation & reversibility', reversibility.score, { return_affordance: returnScore, dialogs_without_exit: noDismiss, interaction_probe_failed: interactionProbeFailed, dialog_escape_dismissed: keyboard?.dialog_escape_dismissed ?? null, dialog_focus_contained: keyboard?.dialog_focus_contained ?? null }, 'Users can return/back/close without browser-only escape hatches; modal keyboard focus stays contained where applicable', 'browser + heuristic', reversibility.score === null ? 'not_measured' : reversibility.coverage < 100 ? 'partial' : 'measured'),
      metric('ux.recovery', 'Dead-end resistance', recovery.score, { dead_ends: desktopAuditCount ? deadEnds : null, dialogs_without_exit: noDismiss }, 'No trapped states or dead ends', 'heuristic', recovery.score === null ? 'not_measured' : recovery.coverage < 100 ? 'partial' : 'measured'),
      metric('ux.dialog_keyboard', 'Modal keyboard escape & containment', dialogKeyboardResult.score, { dialogs: keyboard?.dialog_count ?? null, escape_dismissed: keyboard?.dialog_escape_dismissed ?? null, focus_contained: keyboard?.dialog_focus_contained ?? null, focus_escape_count: keyboard?.dialog_focus_escape_count ?? null }, 'When a modal is present, keyboard focus stays inside it and Escape dismisses it when the interaction model supports dismissal', 'browser keyboard probe', Number(keyboard?.dialog_count) > 0 ? (dialogKeyboardResult.score === null ? 'not_measured' : dialogKeyboardResult.coverage < 100 ? 'partial' : 'measured') : 'not_applicable')
    ],
    performance: [
      metric('perf.lcp', 'Largest Contentful Paint', lcpScore, Number.isFinite(lcpOrLoad) ? lcpOrLoad : null, 'Good LCP <=2500ms; poor >4000ms', Number.isFinite(lcp) ? 'Core Web Vitals' : Number.isFinite(load) ? 'Navigation timing fallback' : 'not measured'),
      metric('perf.inp', 'Interaction responsiveness', inpScore, Number.isFinite(inpOrResponse) ? inpOrResponse : null, 'Good INP <=200ms; poor >500ms', Number.isFinite(inp) && inp > 0 ? 'Core Web Vitals' : Number.isFinite(responseMs) ? 'response proxy' : 'not measured'),
      metric('perf.cls', 'Layout stability', Number.isFinite(cls) ? linear(cls, 0.1, 0.25) : null, Number.isFinite(cls) ? cls : null, 'Good CLS <=0.1; poor >0.25', 'Core Web Vitals'),
      metric('perf.long_tasks', 'Long-task pressure', Number.isFinite(longTask) ? linear(longTask, 150, 1600) : null, Number.isFinite(longTask) ? longTask : null, 'Prefer <=150ms cumulative long-task time in the lab window', 'PerformanceObserver'),
      metric('perf.ttfb', 'Server response', Number.isFinite(ttfb) ? linear(ttfb, 800, 1800) : null, Number.isFinite(ttfb) ? ttfb : null, 'Prefer TTFB <=800ms', 'Navigation timing')
    ],
    accessibility: [
      metric('a11y.names', 'Accessible names & labels', nameScore, { unnamed, unlabeled, controls: totalInteractive }, 'Every control has a useful accessible name; inputs are labeled', 'heuristic', nameScore === null ? 'not_applicable' : 'measured'),
      metric('a11y.contrast', 'Text contrast', a11yContrastScore, { failures: contrastFail, checked: contrastChecked }, 'Normal text >=4.5:1; large text >=3:1; complex/translucent backgrounds remain unmeasured', 'deterministic color check', a11yContrastScore === null ? 'not_measured' : 'measured'),
      metric('a11y.targets', 'Target size', a11yTargetScore, { raw_under_24px: rawUnder24, spacing_exceptions: spacingExceptions, inline_exceptions: inlineExceptions, remaining_failures: hardTargets, controls: totalInteractive, unresolved_exceptions: 'Equivalent-control, essential-presentation, and unmodified user-agent-control exceptions require semantic review.' }, 'WCAG 2.2 target >=24x24 CSS px or an applicable exception; automated checks implement spacing and inline exceptions', 'browser geometry heuristic', a11yTargetScore === null ? 'not_applicable' : 'measured'),
      metric('a11y.keyboard_focus', 'Keyboard focus visibility & reachability', keyboardFocusResult.score, { focusable_count: keyboard?.focusable_count ?? null, expected_sample: keyboardExpected, reached: keyboardReached, tested: keyboardTested, visible_focus: keyboardVisible, not_obscured: keyboardNotObscured, probe_error: keyboard?.probe_error ?? null }, 'Sequential keyboard focus reaches sampled controls, has a detectable focus indicator, and is not fully obscured', 'browser keyboard probe', keyboardFocusResult.score === null ? (keyboard?.probe_error ? 'not_measured' : Number(keyboard?.focusable_count) === 0 ? 'not_applicable' : 'not_measured') : keyboardFocusResult.coverage < 100 ? 'partial' : 'measured'),
      metric('a11y.images', 'Image alternatives', altScore, { missing_alt: missingAlt, images }, 'Visible informative images expose appropriate alt text', 'heuristic', altScore === null ? 'not_applicable' : 'measured'),
      metric('a11y.dialogs', 'Dialog dismissal', dialogScore, { dialogs: dialogCount, without_exit: noDismiss }, 'Every modal/dialog has a clear exit', 'heuristic', dialogScore === null ? 'not_applicable' : 'measured')
    ],
    reliability: [
      metric('reliability.runtime', 'Runtime correctness', runtimeResult.score, { page_errors: Array.isArray(data?.page_errors) ? data.page_errors.length : null, console_errors: Array.isArray(data?.console_errors) ? data.console_errors.length : null }, 'Zero unhandled errors', 'captured browser events', runtimeResult.score === null ? 'not_measured' : runtimeResult.coverage < 100 ? 'partial' : 'measured'),
      metric('reliability.network', 'Network/API health', networkResult.score, { failed_requests: Array.isArray(data?.request_failures) ? data.request_failures.length : null, http_5xx: Array.isArray(data?.bad_responses) ? data.bad_responses.filter((x) => Number(x?.status) >= 500).length : null, http_4xx: Array.isArray(data?.bad_responses) ? data.bad_responses.filter((x) => Number(x?.status) >= 400 && Number(x?.status) < 500).length : null }, 'No failed requests or unexpected 4xx/5xx', 'captured browser events', networkResult.score === null ? 'not_measured' : networkResult.coverage < 100 ? 'partial' : 'measured'),
      metric('reliability.probes', 'Benchmark route reachability', probeScore, { attempted: totalProbeRows, failed: probeFailures }, 'All requested benchmark routes load independently in desktop/mobile probes', 'benchmark browser probes', probeScore === null ? 'not_measured' : 'measured')
    ]
  };

  const dimensions = {
    ui: { status: !Number.isFinite(ui) ? 'not_measured' : uiResult.coverage < 100 ? 'partial' : 'measured', coverage: uiResult.coverage },
    ux: { status: !Number.isFinite(ux) ? 'not_measured' : uxResult.coverage < 100 ? 'partial' : 'measured', coverage: uxResult.coverage },
    performance: { status: !Number.isFinite(performance) ? 'not_measured' : performanceResult.coverage < 100 ? 'partial' : 'measured', coverage: performanceResult.coverage },
    accessibility: { status: !Number.isFinite(accessibility) ? 'not_measured' : accessibilityResult.coverage < 100 ? 'partial' : 'measured', coverage: accessibilityResult.coverage },
    reliability: { status: !Number.isFinite(reliability) ? 'not_measured' : reliabilityResult.coverage < 100 ? 'partial' : 'measured', coverage: reliabilityResult.coverage }
  };
  const unmeasuredMetrics = Object.values(metrics).flat().filter((m) => m.status === 'not_measured').map((m) => m.id);
  const notApplicableMetrics = Object.values(metrics).flat().filter((m) => m.status === 'not_applicable').map((m) => m.id);

  const grade = gradeFor(overall, overallCoverage);
  return {
    version: SCORECARD_VERSION,
    experience_mode: 'app',
    validity: identity,
    benchmark_context: benchmarkContext(data),
    overall_score: roundScore(overall),
    grade,
    scores: { ui: roundScore(ui), ux: roundScore(ux), performance: roundScore(performance), accessibility: roundScore(accessibility), reliability: roundScore(reliability) },
    measurement: { overall_coverage: overallCoverage, dimensions, unmeasured_metrics: unmeasuredMetrics, not_applicable_metrics: notApplicableMetrics },
    gates,
    metrics,
    raw: {
      opening_usable_interactives: Number.isFinite(interactive) ? interactive : null,
      opening_visible_interactives: Number.isFinite(visibleInteractive) ? visibleInteractive : null,
      disabled_or_inert: Number.isFinite(disabledInteractive) ? disabledInteractive : null,
      desktop_pages: desktop.length,
      desktop_probe_failures: Math.max(0, (Array.isArray(desktopRows) ? desktopRows.length : 0) - desktop.length),
      mobile_pages: mobile.length,
      mobile_probe_failures: Math.max(0, (Array.isArray(mobileRows) ? mobileRows.length : 0) - mobile.length),
      response_signal_ms: Number.isFinite(responseMs) ? responseMs : null,
      keyboard_focus_score: keyboardFocusResult.score,
      keyboard_dialog_score: dialogKeyboardResult.score,
      lcp_ms: Number.isFinite(lcp) ? lcp : null,
      inp_ms: Number.isFinite(inp) && inp > 0 ? inp : null,
      cls: Number.isFinite(cls) ? cls : null
    }
  };
}

export function compareScorecards(previous, current) {
  if (!previous || !current) return null;
  if (previous.version !== current.version) return null;
  if (!previous.benchmark_context?.fingerprint || previous.benchmark_context.fingerprint !== current.benchmark_context?.fingerprint) return null;
  if (!Number.isFinite(previous.overall_score) || !Number.isFinite(current.overall_score)) return null;
  const deltas = {};
  for (const key of Object.keys(current.scores || {})) {
    const before = previous.scores?.[key];
    const after = current.scores?.[key];
    deltas[key] = Number.isFinite(before) && Number.isFinite(after) ? after - before : null;
  }
  return {
    comparable: true,
    scorecard_version: current.version,
    benchmark_fingerprint: current.benchmark_context.fingerprint,
    previous_overall: previous.overall_score,
    current_overall: current.overall_score,
    overall_delta: current.overall_score - previous.overall_score,
    score_deltas: deltas
  };
}

export { SCORECARD_VERSION };
