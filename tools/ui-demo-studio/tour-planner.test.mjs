import test from 'node:test';
import assert from 'node:assert/strict';
import {
  assessCandidate,
  canonicalRoute,
  chooseTourAction,
  isDestructiveAction,
  isDistinctScene,
  mergeLinkFrontier,
  rankTourCandidates,
  sceneSignature,
} from './tour-planner.mjs';

const currentUrl = 'http://127.0.0.1:5173/';
const context = () => ({ currentUrl, visitedActions: new Set(), visitedRoutes: new Set([canonicalRoute(currentUrl, currentUrl)]) });

test('same-origin high-value app state outranks low-value chrome', () => {
  const chosen = chooseTourAction([
    { id: 'home', tag: 'a', label: 'Home', href: '/home', region: 'nav', domOrder: 0, sourceUrl: currentUrl },
    { id: 'research', tag: 'a', label: 'Research evidence', href: '/research', region: 'main', domOrder: 5, sourceUrl: currentUrl },
    { id: 'terms', tag: 'a', label: 'Terms', href: '/terms', region: 'footer', domOrder: 9, sourceUrl: currentUrl },
  ], context());
  assert.equal(chosen?.id, 'research');
  assert.equal(chosen?.route, 'http://127.0.0.1:5173/research');
});

test('external, destructive, download, submit, and mutating controls are rejected', () => {
  const cases = [
    [{ tag: 'a', label: 'Docs', href: 'https://example.com/docs' }, 'cross_origin'],
    [{ tag: 'a', label: 'Delete account', href: '/account/delete' }, 'destructive'],
    [{ tag: 'a', label: 'Export CSV', href: '/export', download: true }, 'non_navigation_link'],
    [{ tag: 'button', role: 'button', label: 'Search', type: 'submit', submit: true }, 'submit_control'],
    [{ tag: 'button', role: 'button', label: 'Start agent' }, 'mutating_control'],
    [{ tag: 'button', role: 'button', label: 'Save settings' }, 'mutating_control'],
  ];
  for (const [candidate, reason] of cases) assert.equal(assessCandidate(candidate, context()).reason, reason);
});

test('safe tabs and disclosure buttons are eligible while ambiguous buttons fail closed', () => {
  assert.equal(assessCandidate({ tag: 'button', role: 'tab', label: 'Performance', sourceUrl: currentUrl }, context()).eligible, true);
  assert.equal(assessCandidate({ tag: 'button', role: 'button', label: 'Metrics', ariaControls: 'metrics-panel', ariaExpanded: false, sourceUrl: currentUrl }, context()).eligible, true);
  const ambiguous = assessCandidate({ tag: 'button', role: 'button', label: 'Do thing', sourceUrl: currentUrl }, context());
  assert.equal(ambiguous.eligible, false);
  assert.equal(ambiguous.reason, 'ambiguous_button');
});

test('visited routes/actions are skipped so selection cannot loop', () => {
  const candidates = [
    { id: 'research', tag: 'a', label: 'Research', href: '/research', region: 'main', domOrder: 0, sourceUrl: currentUrl },
    { id: 'risk', tag: 'a', label: 'Risk analysis', href: '/risk', region: 'main', domOrder: 1, sourceUrl: currentUrl },
  ];
  const first = chooseTourAction(candidates, context());
  assert.equal(first?.id, 'research');
  const nextContext = context();
  nextContext.visitedRoutes.add(first.route);
  nextContext.visitedActions.add(first.fingerprint);
  const second = chooseTourAction(candidates, nextContext);
  assert.equal(second?.id, 'risk');
});

test('frontier preserves safe links from previous scenes but stale buttons never remain actionable', () => {
  const firstPage = [
    { id: 'portfolio', tag: 'a', label: 'Portfolio', href: '/portfolio', region: 'main', sourceUrl: currentUrl, domOrder: 1 },
    { id: 'show', tag: 'button', role: 'button', label: 'Show details', ariaControls: 'drawer', sourceUrl: currentUrl, domOrder: 2 },
  ];
  const frontier = mergeLinkFrontier([], firstPage, currentUrl);
  assert.deepEqual(frontier.map((x) => x.id), ['portfolio']);

  const anotherUrl = 'http://127.0.0.1:5173/risk';
  const stale = assessCandidate(firstPage[1], { currentUrl: anotherUrl, visitedActions: new Set(), visitedRoutes: new Set() });
  assert.equal(stale.reason, 'stale_page_control');
  const ranked = rankTourCandidates(frontier, { currentUrl: anotherUrl, visitedActions: new Set(), visitedRoutes: new Set([canonicalRoute(anotherUrl, anotherUrl)]) });
  assert.equal(ranked[0]?.candidate.id, 'portfolio');
});

test('ranking is deterministic for equal-score candidates', () => {
  const candidates = [
    { id: 'b', tag: 'a', label: 'Insights B', href: '/b', region: 'main', domOrder: 2, sourceUrl: currentUrl },
    { id: 'a', tag: 'a', label: 'Insights A', href: '/a', region: 'main', domOrder: 1, sourceUrl: currentUrl },
  ];
  const first = chooseTourAction(candidates, context());
  const second = chooseTourAction([...candidates].reverse(), context());
  assert.equal(first?.id, 'a');
  assert.equal(second?.id, 'a');
});

test('scene signatures suppress duplicate states but recognize useful state changes', () => {
  const a = { url: 'http://127.0.0.1:5173/research?utm_source=x', headings: ['Research', 'Evidence'], landmarks: ['Primary navigation'], dialogs: [] };
  const b = { ...a, url: 'http://127.0.0.1:5173/research?utm_source=y' };
  const c = { ...a, dialogs: ['Ticker details'] };
  assert.equal(sceneSignature(a), sceneSignature(b));
  const seen = new Set([sceneSignature(a)]);
  assert.equal(isDistinctScene(b, seen).distinct, false);
  assert.equal(isDistinctScene(c, seen).distinct, true);
});

test('canonical route strips tracking noise but retains meaningful app state', () => {
  const value = canonicalRoute('/research/?utm_source=demo&ticker=NVDA#evidence', currentUrl);
  assert.equal(value, 'http://127.0.0.1:5173/research?ticker=NVDA#evidence');
});

test('safe-control verbs must be control intent, not incidental prose', () => {
  const verbose = assessCandidate({
    tag: 'button', role: 'button',
    label: 'Design the next useful feature for a local-first AI development cockpit',
    sourceUrl: currentUrl,
  }, context());
  assert.equal(verbose.eligible, false);
  assert.equal(verbose.reason, 'ambiguous_button');
});

test('destructive action detection covers hidden intent in same-origin hrefs', () => {
  assert.equal(isDestructiveAction('Account /account/delete'), true);
  assert.equal(isDestructiveAction('View account /account/details'), false);
});

test('canonical route normalizes equivalent query parameter order', () => {
  const a = canonicalRoute('/research?readiness=all&view=growth', currentUrl);
  const b = canonicalRoute('/research?view=growth&readiness=all', currentUrl);
  assert.equal(a, b);
});
