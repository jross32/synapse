const DESTRUCTIVE_RE = /\b(delete|remove|destroy|erase|purge|purchase|buy|checkout|pay|payment|submit|send|publish|deploy|logout|log\s*out|sign\s*out|reset|stop|kill|archive|revoke|disconnect|cancel\s+subscription|close\s+account|trade|sell|order|place\s+order)\b/i;
const MUTATING_BUTTON_RE = /\b(create|add|save|update|edit|enable|disable|start|stop|connect|disconnect|invite|upload|import|sync|refresh\s+data|run|execute|retry\s+job|approve|reject|accept|decline|claim|redeem|subscribe|unsubscribe|send|submit|publish|deploy|delete|remove|archive|reset|buy|sell|trade|order|pay)\b/i;
const SAFE_BUTTON_RE = /^(view|show|hide|open|close|dismiss|details?|more|less|expand|collapse|next|previous|prev|menu|navigation|filter|sort|learn|inspect|preview|tour|help|about|overview|history|activity)(?:\b|$)/i;
const HIGH_VALUE_RE = /\b(dashboard|overview|research|analysis|analytics|insights?|portfolio|positions?|watchlist|agents?|reports?|results?|details?|evidence|activity|history|performance|risk|orders?|settings|account|billing|customers?|projects?|inventory|collection|binder|market|signals?|opportunities|alerts?)\b/i;
const LOW_VALUE_RE = /\b(home|back|return|previous|privacy|terms|legal|copyright|github|documentation|docs)\b/i;

export function normalizeLabel(value) {
  return String(value || '').trim().replace(/\s+/g, ' ').slice(0, 120);
}

export function isDestructiveAction(value) {
  return DESTRUCTIVE_RE.test(normalizeLabel(value));
}

export function canonicalRoute(value, base) {
  try {
    const url = new URL(String(value || ''), base);
    url.username = '';
    url.password = '';
    for (const key of [...url.searchParams.keys()]) {
      if (/^(utm_|fbclid$|gclid$|_ga$|timestamp$|ts$|nonce$|cachebust$)/i.test(key)) url.searchParams.delete(key);
    }
    url.searchParams.sort();
    const query = url.searchParams.toString();
    const pathname = url.pathname.replace(/\/{2,}/g, '/').replace(/\/$/, '') || '/';
    return `${url.origin}${pathname}${query ? `?${query}` : ''}${url.hash || ''}`;
  } catch {
    return '';
  }
}

function candidateKind(candidate) {
  const role = String(candidate?.role || '').toLowerCase();
  const tag = String(candidate?.tag || '').toLowerCase();
  if (role === 'tab') return 'tab';
  if (tag === 'a' || role === 'link' || candidate?.href) return 'link';
  if (role === 'button' || tag === 'button') return 'button';
  return String(candidate?.kind || 'control').toLowerCase();
}

function buttonIsRevealOnly(candidate, label) {
  if (String(candidate?.role || '').toLowerCase() === 'tab') return true;
  if (candidate?.ariaControls || candidate?.ariaExpanded === true || candidate?.ariaExpanded === false) return true;
  return SAFE_BUTTON_RE.test(label) && !MUTATING_BUTTON_RE.test(label);
}

function safeLink(candidate, currentUrl) {
  if (!candidate?.href || candidate?.download) return { eligible: false, reason: 'non_navigation_link' };
  const raw = String(candidate.href).trim();
  if (/^(javascript:|mailto:|tel:|sms:|data:|blob:)/i.test(raw)) return { eligible: false, reason: 'unsafe_protocol' };
  try {
    const target = new URL(raw, currentUrl);
    const current = new URL(currentUrl);
    if (!/^https?:$/i.test(target.protocol)) return { eligible: false, reason: 'unsafe_protocol' };
    if (target.origin !== current.origin) return { eligible: false, reason: 'cross_origin' };
    if (candidate.externalTarget) return { eligible: false, reason: 'external_target' };
    return { eligible: true, route: canonicalRoute(target.href, currentUrl) };
  } catch {
    return { eligible: false, reason: 'invalid_url' };
  }
}

export function actionFingerprint(candidate, currentUrl) {
  const kind = candidateKind(candidate);
  const label = normalizeLabel(candidate?.label).toLowerCase();
  if (kind === 'link') return `link:${canonicalRoute(candidate?.href, currentUrl)}`;
  const source = canonicalRoute(candidate?.sourceUrl || currentUrl, currentUrl);
  return `${kind}:${source}:${String(candidate?.role || '').toLowerCase()}:${label}`;
}

export function assessCandidate(candidate, context = {}) {
  const currentUrl = String(context.currentUrl || candidate?.sourceUrl || '');
  const currentRoute = canonicalRoute(currentUrl, currentUrl);
  const label = normalizeLabel(candidate?.label);
  const kind = candidateKind(candidate);
  const visitedActions = context.visitedActions || new Set();
  const visitedRoutes = context.visitedRoutes || new Set();

  if (!label) return { eligible: false, reason: 'missing_label', score: -Infinity };
  if (candidate?.disabled || candidate?.inert || candidate?.ariaDisabled) return { eligible: false, reason: 'disabled', score: -Infinity };
  if (isDestructiveAction(`${label} ${candidate?.href || ''}`)) return { eligible: false, reason: 'destructive', score: -Infinity };

  let route = '';
  if (kind === 'link') {
    const link = safeLink(candidate, currentUrl);
    if (!link.eligible) return { ...link, score: -Infinity };
    route = link.route;
    if (!route || route === currentRoute) return { eligible: false, reason: 'same_route', score: -Infinity, route };
    if (visitedRoutes.has(route)) return { eligible: false, reason: 'visited_route', score: -Infinity, route };
  } else {
    const source = canonicalRoute(candidate?.sourceUrl || currentUrl, currentUrl);
    if (source && currentRoute && source !== currentRoute) return { eligible: false, reason: 'stale_page_control', score: -Infinity };
    if (candidate?.submit || String(candidate?.type || '').toLowerCase() === 'submit') return { eligible: false, reason: 'submit_control', score: -Infinity };
    if (MUTATING_BUTTON_RE.test(label)) return { eligible: false, reason: 'mutating_control', score: -Infinity };
    if (!buttonIsRevealOnly(candidate, label)) return { eligible: false, reason: 'ambiguous_button', score: -Infinity };
  }

  const fingerprint = actionFingerprint(candidate, currentUrl);
  if (visitedActions.has(fingerprint)) return { eligible: false, reason: 'visited_action', score: -Infinity, route, fingerprint };

  let score = kind === 'tab' ? 74 : kind === 'button' ? 64 : 56;
  const region = String(candidate?.region || 'other').toLowerCase();
  if (region === 'main') score += 34;
  else if (region === 'other') score += 16;
  else if (region === 'nav') score += 8;
  else if (region === 'aside' || region === 'header') score += 3;
  else if (region === 'footer') score -= 12;

  if (HIGH_VALUE_RE.test(label)) score += 32;
  if (LOW_VALUE_RE.test(label)) score -= 22;
  if (candidate?.ariaControls) score += 16;
  if (candidate?.ariaExpanded === false) score += 12;
  if (kind === 'link' && route) {
    const target = new URL(route);
    score += Math.min(18, target.pathname.split('/').filter(Boolean).length * 4);
  }
  if (candidate?.sourceUrl && canonicalRoute(candidate.sourceUrl, currentUrl) === currentRoute) score += 5;

  return { eligible: true, reason: 'safe', score, route, fingerprint, kind, label };
}

function stableKey(candidate, assessment) {
  return [String(Number(candidate?.domOrder ?? 999999)).padStart(6, '0'), assessment.kind || '', assessment.route || '', assessment.label?.toLowerCase() || '', String(candidate?.id || '')].join('|');
}

export function rankTourCandidates(candidates, context = {}) {
  return (Array.isArray(candidates) ? candidates : [])
    .map((candidate) => ({ candidate, assessment: assessCandidate(candidate, context) }))
    .filter((item) => item.assessment.eligible)
    .sort((a, b) => b.assessment.score - a.assessment.score || stableKey(a.candidate, a.assessment).localeCompare(stableKey(b.candidate, b.assessment)));
}

export function chooseTourAction(candidates, context = {}) {
  const first = rankTourCandidates(candidates, context)[0];
  return first ? { ...first.candidate, ...first.assessment } : null;
}

export function mergeLinkFrontier(frontier, candidates, currentUrl) {
  const map = new Map();
  for (const candidate of Array.isArray(frontier) ? frontier : []) {
    if (candidateKind(candidate) !== 'link') continue;
    const key = canonicalRoute(candidate.href, currentUrl);
    if (key) map.set(key, candidate);
  }
  for (const candidate of Array.isArray(candidates) ? candidates : []) {
    if (candidateKind(candidate) !== 'link') continue;
    const safe = safeLink(candidate, currentUrl);
    if (!safe.eligible || !safe.route) continue;
    if (!map.has(safe.route)) map.set(safe.route, { ...candidate, sourceUrl: candidate.sourceUrl || currentUrl });
  }
  return [...map.values()];
}

export function sceneSignature(snapshot = {}) {
  const route = canonicalRoute(snapshot.url || '', snapshot.url || 'http://invalid.local');
  const headings = (Array.isArray(snapshot.headings) ? snapshot.headings : []).map(normalizeLabel).filter(Boolean).slice(0, 6).join('|').toLowerCase();
  const landmarks = (Array.isArray(snapshot.landmarks) ? snapshot.landmarks : []).map(normalizeLabel).filter(Boolean).slice(0, 8).join('|').toLowerCase();
  const dialogs = (Array.isArray(snapshot.dialogs) ? snapshot.dialogs : []).map(normalizeLabel).filter(Boolean).slice(0, 4).join('|').toLowerCase();
  return `${route}::h=${headings}::l=${landmarks}::d=${dialogs}`;
}

export function isDistinctScene(snapshot, visitedSceneSignatures = new Set()) {
  const signature = sceneSignature(snapshot);
  return { distinct: Boolean(signature) && !visitedSceneSignatures.has(signature), signature };
}
