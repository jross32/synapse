export type RestartKind = 'startup' | 'restart';
export type RestartStageState = 'pending' | 'active' | 'success' | 'error';
export type RestartStageKey = 'request' | 'stop' | 'desktop' | 'daemon' | 'interface';

export interface RestartStage {
  key: RestartStageKey;
  label: string;
  state: RestartStageState;
  detail: string;
  errorCode?: string;
}

export interface RestartProgress {
  operationId: string;
  kind: RestartKind;
  source: string;
  startedAt: string;
  updatedAt: string;
  stages: RestartStage[];
  errorCode?: string;
  errorMessage?: string;
}

export const RESTART_ERROR_CODES: Record<string, string> = {
  'SYN-RST-001': 'A restart is already running. Wait for the current restart window to finish.',
  'SYN-RST-101': 'Synapse could not stop its previous services cleanly.',
  'SYN-RST-201': 'Electron could not schedule or hand off the relaunch.',
  'SYN-BOOT-101': 'The Synapse daemon process could not be started.',
  'SYN-BOOT-102': 'The Synapse daemon started but did not become healthy in time.',
  'SYN-BOOT-201': 'The desktop interface could not be loaded.',
  'SYN-BOOT-202': 'The desktop interface loaded but never became ready to show.',
  'SYN-BOOT-301': 'The saved restart progress record was invalid or unreadable.',
};

const STARTUP_STAGES: RestartStage[] = [
  { key: 'desktop', label: 'Desktop process started', state: 'active', detail: 'Opening Synapse…' },
  { key: 'daemon', label: 'Synapse services running', state: 'pending', detail: 'Waiting to start' },
  { key: 'interface', label: 'Interface ready', state: 'pending', detail: 'Waiting to load' },
];

const RESTART_STAGES: RestartStage[] = [
  { key: 'request', label: 'Restart requested', state: 'active', detail: 'Preparing a clean restart…' },
  { key: 'stop', label: 'Previous services stopped', state: 'pending', detail: 'Waiting to stop' },
  { key: 'desktop', label: 'Desktop process restarted', state: 'pending', detail: 'Waiting to relaunch' },
  { key: 'daemon', label: 'Synapse services running', state: 'pending', detail: 'Waiting to start' },
  { key: 'interface', label: 'Interface ready', state: 'pending', detail: 'Waiting to load' },
];

export function createRestartProgress(
  kind: RestartKind,
  operationId: string,
  source: string
): RestartProgress {
  const now = new Date().toISOString();
  const template = kind === 'restart' ? RESTART_STAGES : STARTUP_STAGES;
  return {
    operationId,
    kind,
    source,
    startedAt: now,
    updatedAt: now,
    stages: template.map((stage) => ({ ...stage })),
  };
}

export function updateRestartStage(
  progress: RestartProgress,
  key: RestartStageKey,
  state: RestartStageState,
  detail: string,
  errorCode?: string,
  errorMessage?: string
): RestartProgress {
  return {
    ...progress,
    updatedAt: new Date().toISOString(),
    errorCode: state === 'error' ? errorCode : progress.errorCode,
    errorMessage: state === 'error' ? errorMessage ?? detail : progress.errorMessage,
    stages: progress.stages.map((stage) =>
      stage.key === key ? { ...stage, state, detail, errorCode } : stage
    ),
  };
}

export function restartDiagnostics(progress: RestartProgress): string {
  const lines = [
    `Synapse ${progress.kind} operation: ${progress.operationId}`,
    `Source: ${progress.source}`,
    `Started: ${progress.startedAt}`,
    `Updated: ${progress.updatedAt}`,
  ];
  for (const stage of progress.stages) {
    lines.push(`[${stage.state.toUpperCase()}] ${stage.label}: ${stage.detail}`);
  }
  if (progress.errorCode) {
    lines.push(`Error code: ${progress.errorCode}`);
    lines.push(`Meaning: ${RESTART_ERROR_CODES[progress.errorCode] ?? 'Unknown restart error.'}`);
  }
  if (progress.errorMessage) lines.push(`Details: ${progress.errorMessage}`);
  return lines.join('\n');
}

function safeInlineJson(value: unknown): string {
  return JSON.stringify(value).replace(/</g, '\\u003c');
}

export function restartProgressHtml(progress: RestartProgress): string {
  const initial = safeInlineJson(progress);
  const errorCatalog = safeInlineJson(RESTART_ERROR_CODES);
  return `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'">
  <title>Synapse startup</title>
  <style>
    :root {
      --bg: #07110c; --panel: #0c1a12; --panel-2: #10251a; --border: #24533a;
      --text: #e7fff0; --muted: #8bc9a2; --accent: #23ef77; --active: #5de99a;
      --error: #ff6b78; --error-bg: #2a1016; --shadow: rgba(0, 0, 0, .48);
    }
    * { box-sizing: border-box; }
    body { margin: 0; min-height: 100vh; display: grid; place-items: center; overflow: hidden;
      color: var(--text); background: radial-gradient(circle at 50% 0%, #12351f 0, var(--bg) 58%);
      font-family: "Segoe UI", system-ui, sans-serif; }
    main { width: min(620px, calc(100vw - 32px)); padding: 28px; border: 1px solid var(--border);
      border-radius: 18px; background: linear-gradient(180deg, rgba(16,37,26,.98), rgba(7,17,12,.98));
      box-shadow: 0 24px 80px var(--shadow); }
    .brand { display: flex; align-items: center; gap: 14px; }
    .orb { width: 42px; height: 42px; border-radius: 50%; border: 4px solid #7c3aed;
      box-shadow: inset 0 0 0 7px #0b1520, 0 0 28px rgba(35,239,119,.34); position: relative; }
    .orb::after { content: ""; position: absolute; inset: 11px; border-radius: 50%; background: var(--text); }
    h1 { margin: 0; font-size: 24px; letter-spacing: -.02em; }
    #subtitle { margin: 5px 0 0; color: var(--muted); font-size: 14px; }
    .bar { height: 6px; margin: 22px 0; overflow: hidden; border-radius: 999px; background: #13271b; }
    #barFill { height: 100%; width: 0; border-radius: inherit; background: linear-gradient(90deg, #13c85a, #5dffa0);
      transition: width .25s ease; }
    #stages { display: grid; gap: 10px; }
    .stage { display: grid; grid-template-columns: 32px 1fr; gap: 12px; align-items: center;
      min-height: 58px; padding: 10px 12px; border: 1px solid transparent; border-radius: 12px; }
    .stage.active { background: var(--panel-2); border-color: var(--border); }
    .stage.error { background: var(--error-bg); border-color: #6f2632; }
    .icon { width: 28px; height: 28px; display: grid; place-items: center; border-radius: 50%;
      border: 1px solid #385244; color: #6b8f79; font-weight: 700; }
    .success .icon { color: #03150a; background: var(--accent); border-color: var(--accent); }
    .active .icon { color: var(--active); border-color: var(--active); animation: pulse 1.1s ease-in-out infinite; }
    .error .icon { color: white; background: var(--error); border-color: var(--error); }
    .label { font-weight: 650; font-size: 15px; }
    .detail { margin-top: 3px; color: var(--muted); font-size: 12.5px; line-height: 1.35; }
    #errorBox { display: none; margin-top: 18px; padding: 14px; border-radius: 12px;
      border: 1px solid #7b2b37; background: var(--error-bg); }
    #errorBox.visible { display: block; }
    #errorCode { color: #ff9aa4; font-family: Consolas, monospace; font-weight: 700; }
    #errorMeaning, #errorDetails { margin-top: 6px; color: #ffd7db; font-size: 13px; line-height: 1.4; }
    .actions { display: flex; justify-content: flex-end; margin-top: 14px; }
    button { padding: 9px 13px; border: 1px solid #426c50; border-radius: 9px; color: var(--text);
      background: #173523; font: inherit; cursor: pointer; }
    button:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
    #operation { margin-top: 18px; color: #5e8e6c; font: 11px Consolas, monospace; }
    @keyframes pulse { 0%,100% { box-shadow: 0 0 0 0 rgba(93,233,154,.05); }
      50% { box-shadow: 0 0 0 6px rgba(93,233,154,.16); } }
    @media (prefers-reduced-motion: reduce) { * { animation: none !important; transition: none !important; } }
  </style>
</head>
<body>
  <main role="status" aria-live="polite">
    <div class="brand"><div class="orb" aria-hidden="true"></div><div><h1 id="title"></h1><p id="subtitle"></p></div></div>
    <div class="bar" aria-hidden="true"><div id="barFill"></div></div>
    <section id="stages" aria-label="Startup checks"></section>
    <section id="errorBox" role="alert"><div id="errorCode"></div><div id="errorMeaning"></div><div id="errorDetails"></div>
      <div class="actions"><button id="copyButton" type="button">Copy diagnostics</button></div></section>
    <div id="operation"></div>
  </main>
  <script>
    const errorCatalog = ${errorCatalog};
    let current = ${initial};
    const icons = { pending: '·', active: '↻', success: '✓', error: '!' };
    function diagnostics(value) {
      const lines = ['Synapse ' + value.kind + ' operation: ' + value.operationId, 'Source: ' + value.source,
        'Started: ' + value.startedAt, 'Updated: ' + value.updatedAt];
      value.stages.forEach(stage => lines.push('[' + stage.state.toUpperCase() + '] ' + stage.label + ': ' + stage.detail));
      if (value.errorCode) { lines.push('Error code: ' + value.errorCode); lines.push('Meaning: ' + (errorCatalog[value.errorCode] || 'Unknown restart error.')); }
      if (value.errorMessage) lines.push('Details: ' + value.errorMessage);
      return lines.join('\\n');
    }
    function render(value) {
      current = value;
      const error = value.stages.some(stage => stage.state === 'error');
      const complete = value.stages.every(stage => stage.state === 'success');
      document.getElementById('title').textContent = error ? 'Synapse needs attention' : complete ? 'Synapse is ready' : value.kind === 'restart' ? 'Restarting Synapse…' : 'Starting Synapse…';
      document.getElementById('subtitle').textContent = error ? 'A check failed. The diagnostic code below identifies the exact stage.' : complete ? 'Every startup check passed.' : 'You can watch each part come back online.';
      const successes = value.stages.filter(stage => stage.state === 'success').length;
      document.getElementById('barFill').style.width = Math.round((successes / value.stages.length) * 100) + '%';
      const stages = document.getElementById('stages'); stages.replaceChildren();
      value.stages.forEach(stage => {
        const row = document.createElement('div'); row.className = 'stage ' + stage.state;
        const icon = document.createElement('div'); icon.className = 'icon'; icon.textContent = icons[stage.state];
        const copy = document.createElement('div');
        const label = document.createElement('div'); label.className = 'label'; label.textContent = stage.label;
        const detail = document.createElement('div'); detail.className = 'detail'; detail.textContent = stage.detail;
        copy.append(label, detail); row.append(icon, copy); stages.append(row);
      });
      const box = document.getElementById('errorBox'); box.classList.toggle('visible', error);
      document.getElementById('errorCode').textContent = value.errorCode || '';
      document.getElementById('errorMeaning').textContent = value.errorCode ? (errorCatalog[value.errorCode] || 'Unknown restart error.') : '';
      document.getElementById('errorDetails').textContent = value.errorMessage || '';
      document.getElementById('operation').textContent = 'Operation ' + value.operationId;
    }
    window.updateRestartProgress = render;
    document.getElementById('copyButton').addEventListener('click', async () => {
      const text = diagnostics(current);
      try { await navigator.clipboard.writeText(text); }
      catch { const area = document.createElement('textarea'); area.value = text; document.body.append(area); area.select(); document.execCommand('copy'); area.remove(); }
      document.getElementById('copyButton').textContent = 'Copied';
    });
    render(current);
  </script>
</body>
</html>`;
}
