// Sessions page (v0.1.26 · ADR-0002 Phase A step 2).
//
// One xterm tab per live PTY session, plus a launcher rail to start a new
// one. Quick-launch buttons cover the common cases (Claude, Codex, Python,
// shell); a free-text argv input handles anything else.

import { useEffect, useMemo, useState } from 'react';
import {
  Bot,
  ChevronDown,
  ChevronUp,
  Download,
  ExternalLink,
  HelpCircle,
  Loader2,
  Plus,
  RotateCcw,
  Sparkles,
  Terminal as TerminalIcon,
  TerminalSquare,
  X,
} from 'lucide-react';

import type { PtySessionSummary } from '@shared/generated-types';
import {
  closeSession,
  getSession,
  listSessions,
  probeCommand,
  spawnSession,
} from '@shared/pty-client';
import { SynapseApiError } from '@shared/api-client';
import { useDaemon } from '@shared/daemon-context';
import { openExternal } from '@shared/electron-bridge';
import { cn } from '@shared/utils';
import {
  launchQuickAction,
  listQuickActions,
  type QuickAction,
} from '../lib/quick-actions-client';
import { Button } from '../components/ui/button';
import { Card } from '../components/ui/card';
import { Input } from '../components/ui/input';
import { Modal } from '../components/ui/modal';
import { PageHeader } from '../components/PageHeader';
import { SessionTerminal } from '../components/SessionTerminal';

function HelpPanel(): JSX.Element {
  return (
    <Card className='flex flex-col gap-3 border-dashed p-5 text-sm'>
      <h2 className='text-base font-semibold'>How Synapse Sessions work</h2>
      <ul className='ml-5 list-disc space-y-1 text-muted-foreground'>
        <li>
          Every session is a real pseudo-terminal — colours, line editing,
          Ctrl+C, all work like a normal shell.
        </li>
        <li>
          Quick-launch buttons spawn the CLI for you. If the binary isn't on
          PATH, Synapse offers to install it (npm) and shows the output live.
        </li>
        <li>
          You can also paste any custom argv into the text field — anything on
          PATH works (<span className='font-mono'>node --version</span>,{' '}
          <span className='font-mono'>psql</span>,{' '}
          <span className='font-mono'>gh repl</span>, ...).
        </li>
        <li>
          Sessions opened from elsewhere (curl, another tab) appear under{' '}
          <span className='font-mono'>Re-attach to</span> — click to bind a
          terminal panel to a session that was already alive.
        </li>
      </ul>
      <h2 className='text-base font-semibold'>Claude Code & Codex inside Sessions</h2>
      <ul className='ml-5 list-disc space-y-1 text-muted-foreground'>
        <li>
          Sign-in happens inside the CLI on first launch — Claude opens an
          OAuth flow in your browser; Codex uses your existing ChatGPT
          session. Synapse stores no credentials.
        </li>
        <li>
          Runtime controls (Claude Code): <span className='font-mono'>/permissions</span>{' '}
          to manage edit approvals, <span className='font-mono'>/tools</span> to see
          what's wired in, <span className='font-mono'>--dangerously-skip-permissions</span>{' '}
          to bypass approval prompts (yolo mode — be careful).
        </li>
        <li>
          MCP servers configured for your Claude / Codex install are available
          inside the session unchanged.
        </li>
        <li>
          Sessions survive page navigation — you can flip to Apps, edit a
          project, and come back; the terminal keeps running.
        </li>
      </ul>
      <h2 className='text-base font-semibold'>Built for AI agents too</h2>
      <p className='text-muted-foreground'>
        This dashboard is designed to be used by an AI inside a Sessions tab
        just as much as by a human at the keyboard. Each project's path,
        installed tools, registry contents, and (in v0.1.29) workbench
        transcripts are exposed through the REST API so a Claude session can
        introspect what's running and where files live. The README and
        AGENTS.md call out which surfaces are AI-callable.
      </p>
    </Card>
  );
}

interface QuickLaunch {
  id: string;
  label: string;
  icon: typeof TerminalIcon;
  argv: string[];
}

// Cross-platform-ish defaults. The daemon resolves argv[0] on PATH; bad ones
// surface as a 422 "command not found" we display.
const isMac = typeof navigator !== 'undefined' && /mac/i.test(navigator.platform);
const isWindows = typeof navigator !== 'undefined' && /win/i.test(navigator.platform);

/**
 * Friendly label for an argv (tab title, restart/close aria-label,
 * orphan re-attach button). The daemon resolves the binary via
 * shutil.which, which on Windows returns a full path like
 * `C:\Users\justi\AppData\Roaming\npm\claude.CMD`. Rendering that
 * verbatim makes the tab strip useless and gives the impression
 * the session didn't really start. Strip down to the basename + drop
 * the .exe / .cmd / .bat extensions so the user sees `claude` /
 * `codex` / `powershell`.
 */
function friendlyArgvLabel(argv: string[], fallback: string): string {
  const head = argv[0];
  if (!head) return fallback;
  // Last path segment regardless of separator (Windows uses \, POSIX /).
  const base = head.split(/[\\/]/).pop() ?? head;
  // Drop a trailing executable extension; preserve case otherwise.
  const stripped = base.replace(/\.(exe|cmd|bat|com)$/i, '');
  return stripped || head;
}

const QUICK_LAUNCH: QuickLaunch[] = [
  { id: 'claude', label: 'Claude', icon: Sparkles, argv: ['claude'] },
  { id: 'codex', label: 'Codex', icon: Bot, argv: ['codex'] },
  {
    id: 'python',
    label: 'Python REPL',
    icon: TerminalIcon,
    argv: [isWindows ? 'python' : 'python3', '-i', '-q'],
  },
  {
    id: 'shell',
    label: isWindows ? 'PowerShell' : isMac ? 'zsh' : 'bash',
    icon: TerminalSquare,
    argv: isWindows ? ['powershell.exe', '-NoLogo'] : [isMac ? 'zsh' : 'bash', '-i'],
  },
];

/**
 * Install recipes for coders that aren't on PATH yet (v0.1.28). The user
 * sees the exact command before we run anything; the install itself runs
 * as a Synapse session so they can watch the output live.
 *
 * Auth note: every coder here manages its own auth on first launch
 * (Claude Code opens a browser OAuth flow, etc.). Synapse stores no
 * credentials -- the CLI caches them in its own home directory. That's
 * the ADR-0002 contract.
 */
interface InstallRecipe {
  label: string;
  install_argv: string[];
  needs: string;
  docs: string;
  notes?: string;
}

const INSTALL_RECIPES: Record<string, InstallRecipe> = {
  claude: {
    label: 'Claude Code',
    install_argv: ['npm', 'install', '-g', '@anthropic-ai/claude-code'],
    needs: 'npm (Node.js)',
    docs: 'https://docs.claude.com/en/docs/claude-code/quickstart',
    notes:
      'First launch opens a browser for sign-in. Cookies are cached in ~/.claude — next time it just starts up.',
  },
  codex: {
    label: 'OpenAI Codex CLI',
    install_argv: ['npm', 'install', '-g', '@openai/codex'],
    needs: 'npm (Node.js)',
    docs: 'https://github.com/openai/codex',
    notes:
      'Uses your existing ChatGPT login on first run. Synapse just spawns the CLI -- no API keys to hand it.',
  },
};

interface OpenTab {
  sessionId: string;
  argv: string[];
  scrollback: string | null;
  scrollbackLoaded: boolean;
}

export interface SessionsPageProps {
  /** Auto-open this session id on mount (used by the Tools deep link). */
  initialSessionId?: string | null;
  /** Called after the initial session id has been consumed, so it doesn't
   *  re-trigger on next mount. */
  onConsumedInitial?: () => void;
}

export function SessionsPage({
  initialSessionId,
  onConsumedInitial,
}: SessionsPageProps = {}): JSX.Element {
  const { recentEvents } = useDaemon();
  const [tabs, setTabs] = useState<OpenTab[]>([]);
  const [active, setActive] = useState<string | null>(null);
  const [registry, setRegistry] = useState<PtySessionSummary[]>([]);
  const [argvText, setArgvText] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [spawning, setSpawning] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  // Drives the Install dialog when a quick-launch's binary isn't on PATH.
  const [installPrompt, setInstallPrompt] = useState<
    | (InstallRecipe & { quickLaunchId: string; original_argv: string[] })
    | null
  >(null);
  // Quick-actions rail (v0.1.34). Loaded once on mount; the daemon reads
  // templates/quick-actions/*.json so adding one doesn't need a restart.
  const [quickActions, setQuickActions] = useState<QuickAction[]>([]);
  const [launchingActionId, setLaunchingActionId] = useState<string | null>(null);

  // Bring the existing session list in on mount so a refresh doesn't lose
  // sessions started from elsewhere (curl / a previous tab).
  useEffect(() => {
    void listSessions().then(setRegistry).catch(() => undefined);
  }, []);

  // Quick-action templates (v0.1.34). A bare daemon without any user
  // templates ships two defaults; an empty list just hides the rail.
  useEffect(() => {
    void listQuickActions().then(setQuickActions).catch(() => undefined);
  }, []);

  // Deep link from Tools → "Open in Sessions" (v0.1.27). Look up the session
  // detail to know its argv, then open a tab and consume the id so a re-mount
  // doesn't loop.
  useEffect(() => {
    if (!initialSessionId) return;
    let cancelled = false;
    void getSession(initialSessionId)
      .then((s) => {
        if (cancelled) return;
        void openTab(s.session_id, s.argv);
        onConsumedInitial?.();
      })
      .catch(() => {
        if (!cancelled) onConsumedInitial?.();
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialSessionId]);

  // Auto-refresh the registry when a session lifecycle event lands. The
  // daemon broadcasts session_started + session_exited; that's enough to
  // keep the rail accurate without polling.
  useEffect(() => {
    const fresh = recentEvents.some(
      (e) =>
        e.name === 'v1.pty.session_started' || e.name === 'v1.pty.session_exited'
    );
    if (fresh) void listSessions().then(setRegistry).catch(() => undefined);
  }, [recentEvents]);

  async function openTab(sessionId: string, argv: string[]): Promise<void> {
    // Already open? Just focus it.
    if (tabs.find((t) => t.sessionId === sessionId)) {
      setActive(sessionId);
      return;
    }
    setTabs((prev) => [
      ...prev,
      { sessionId, argv, scrollback: null, scrollbackLoaded: false },
    ]);
    setActive(sessionId);
    // Fetch scrollback in the background; passing it into SessionTerminal
    // before mount means the user sees prior context immediately.
    try {
      const detail = await getSession(sessionId);
      setTabs((prev) =>
        prev.map((t) =>
          t.sessionId === sessionId
            ? { ...t, scrollback: detail.scrollback, scrollbackLoaded: true }
            : t
        )
      );
    } catch {
      setTabs((prev) =>
        prev.map((t) =>
          t.sessionId === sessionId ? { ...t, scrollbackLoaded: true } : t
        )
      );
    }
  }

  /** Look up the binary on PATH first. If a known coder is missing, route
   *  through the Install dialog instead of just surfacing "command not
   *  found". Anything else falls through to the daemon's normal error. */
  async function spawnAndOpen(
    argv: string[],
    opts: { quickLaunchId?: string } = {}
  ): Promise<void> {
    if (argv.length === 0 || !argv[0].trim()) {
      setError('argv must have at least one entry.');
      return;
    }
    setSpawning(true);
    setError(null);
    try {
      // Skip the probe for the custom argv path -- the user typed it; let the
      // daemon's error be the source of truth.
      if (opts.quickLaunchId) {
        const probe = await probeCommand(argv[0]).catch(() => null);
        if (probe && !probe.available) {
          const recipe = INSTALL_RECIPES[opts.quickLaunchId];
          if (recipe) {
            setInstallPrompt({
              ...recipe,
              quickLaunchId: opts.quickLaunchId,
              original_argv: argv,
            });
            return;
          }
        }
      }
      const session = await spawnSession({ argv });
      await openTab(session.session_id, session.argv);
      setArgvText('');
    } catch (err) {
      setError((err as Error).message || 'Spawn failed.');
    } finally {
      setSpawning(false);
    }
  }

  /** Fire a quick-action: the daemon spawns a workbench session in the
   *  scratch project with the templated prompt pre-loaded as PROMPT.md and
   *  ``SYNAPSE_QUICK_ACTION_PROMPT``. The session lands in a tab just like
   *  any other PTY. */
  async function launchAction(action: QuickAction): Promise<void> {
    setLaunchingActionId(action.id);
    setError(null);
    try {
      const launched = await launchQuickAction(action.id);
      await openTab(launched.session_id, launched.argv);
    } catch (err) {
      setError((err as Error).message || 'Quick-action launch failed.');
    } finally {
      setLaunchingActionId(null);
    }
  }

  /** Run the recipe's install command as a Synapse session so the user can
   *  watch the output in xterm. After it finishes (they close the tab or it
   *  exits) they click the quick-launch again to use the installed binary. */
  async function runInstall(recipe: InstallRecipe): Promise<void> {
    try {
      const session = await spawnSession({ argv: recipe.install_argv });
      await openTab(session.session_id, session.argv);
      setInstallPrompt(null);
    } catch (err) {
      setError((err as Error).message || 'Install spawn failed.');
    }
  }

  async function closeTab(sessionId: string): Promise<void> {
    let dropTab = true;
    try {
      await closeSession(sessionId);
    } catch (err) {
      // 404: the daemon already lost the session -- a tab pointing at
      // it is dead weight; drop silently. Anything else (network blip,
      // 5xx) might mean the session is still running on the daemon
      // side, so surface a warning AND keep the tab visible so the
      // user can retry or attach a fresh terminal.
      const status =
        err instanceof SynapseApiError ? err.status : undefined;
      if (status !== 404) {
        const msg = (err as Error).message || 'Close failed.';
        setError(
          `Couldn't close session ${sessionId}: ${msg}. The PTY may still be running; check 'Re-attach to' below.`
        );
        dropTab = false;
      }
    }
    if (!dropTab) return;
    setTabs((prev) => prev.filter((t) => t.sessionId !== sessionId));
    if (active === sessionId) {
      const remaining = tabs.filter((t) => t.sessionId !== sessionId);
      setActive(remaining[0]?.sessionId ?? null);
    }
  }

  /** Restart a session in place: close the existing PTY, spawn a new
   *  one with the same argv, swap the tab to point at the new id. The
   *  position in the tab strip is preserved. Useful when a coder
   *  freezes but you don't want to lose your spot. */
  async function restartTab(sessionId: string): Promise<void> {
    const tab = tabs.find((t) => t.sessionId === sessionId);
    if (!tab) return;
    setError(null);
    try {
      await closeSession(sessionId).catch(() => undefined);
      const fresh = await spawnSession({ argv: tab.argv });
      setTabs((prev) =>
        prev.map((t) =>
          t.sessionId === sessionId
            ? {
                sessionId: fresh.session_id,
                argv: fresh.argv,
                scrollback: null,
                scrollbackLoaded: true,
              }
            : t
        )
      );
      if (active === sessionId) setActive(fresh.session_id);
    } catch (err) {
      setError((err as Error).message || 'Restart failed.');
    }
  }

  // Sessions already running on the daemon that the user hasn't opened a
  // tab for. Lets them re-attach to a curl-spawned session etc.
  const orphans = useMemo(
    () =>
      registry.filter(
        (s) => s.exit_code === null && !tabs.find((t) => t.sessionId === s.session_id)
      ),
    [registry, tabs]
  );

  const activeTab = tabs.find((t) => t.sessionId === active) ?? null;

  return (
    <div className='flex h-full flex-col gap-4'>
      <PageHeader
        title='Sessions'
        subtitle='Live AI coders & shells — Claude, Codex, Python, anything on PATH. Each session runs under a real PTY so colours, line editing and Ctrl+C all behave.'
      />

      {/* Quick launch rail + custom argv */}
      <Card className='flex flex-col gap-3 p-4'>
        <div className='flex flex-wrap items-center gap-2'>
          {QUICK_LAUNCH.map((q) => {
            const Icon = q.icon;
            return (
              <Button
                key={q.id}
                variant='outline'
                size='sm'
                disabled={spawning}
                onClick={() => void spawnAndOpen(q.argv, { quickLaunchId: q.id })}
              >
                <Icon className='h-4 w-4' />
                {q.label}
              </Button>
            );
          })}
          <Button
            type='button'
            variant='ghost'
            size='sm'
            onClick={() => setHelpOpen((o) => !o)}
            className='ml-auto text-muted-foreground'
            title='How sessions work'
          >
            <HelpCircle className='h-4 w-4' />
            Help
            {helpOpen ? (
              <ChevronUp className='h-3 w-3' />
            ) : (
              <ChevronDown className='h-3 w-3' />
            )}
          </Button>
        </div>
        {quickActions.length > 0 && (
          <div className='flex flex-col gap-2 border-t border-border pt-3'>
            <div className='flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-muted-foreground'>
              <Sparkles className='h-3.5 w-3.5' />
              <span>AI Quick-actions</span>
              <span
                className='font-normal normal-case tracking-normal text-muted-foreground/80'
                title='Each one opens a Claude session in the scratch project with a templated prompt pre-loaded.'
              >
                — one click; the AI does the work.
              </span>
            </div>
            <div className='flex flex-wrap gap-2'>
              {quickActions.map((qa) => {
                const isLaunching = launchingActionId === qa.id;
                return (
                  <button
                    key={qa.id}
                    type='button'
                    disabled={launchingActionId !== null}
                    onClick={() => void launchAction(qa)}
                    title={qa.description}
                    className={cn(
                      'group flex max-w-xs flex-col items-start gap-1 rounded-md border border-border bg-secondary/30 px-3 py-2 text-left transition-colors',
                      'hover:border-primary hover:bg-secondary/60',
                      'disabled:cursor-not-allowed disabled:opacity-50'
                    )}
                  >
                    <div className='flex w-full items-center gap-1.5 text-sm font-medium'>
                      {isLaunching ? (
                        <Loader2 className='h-3.5 w-3.5 animate-spin' />
                      ) : (
                        <Sparkles className='h-3.5 w-3.5 text-primary' />
                      )}
                      <span>{qa.name}</span>
                    </div>
                    <p className='line-clamp-2 text-xs text-muted-foreground'>
                      {qa.description}
                    </p>
                  </button>
                );
              })}
            </div>
          </div>
        )}
        <form
          className='flex flex-wrap items-center gap-2'
          onSubmit={(e) => {
            e.preventDefault();
            const argv = argvText
              .trim()
              .split(/\s+/)
              .filter(Boolean);
            void spawnAndOpen(argv);
          }}
        >
          <Input
            value={argvText}
            onChange={(e) => setArgvText(e.target.value)}
            placeholder='Or a custom argv, e.g. "node --version" or "psql -U me"'
            className='grow sm:max-w-2xl'
            aria-label='Custom argv'
          />
          <Button type='submit' disabled={spawning || !argvText.trim()}>
            {spawning ? <Loader2 className='h-4 w-4 animate-spin' /> : <Plus className='h-4 w-4' />}
            Spawn
          </Button>
        </form>
        {error && (
          <p role='alert' className='text-sm text-destructive'>
            {error}
          </p>
        )}
        {orphans.length > 0 && (
          <div className='flex flex-wrap items-center gap-2 border-t border-border pt-3'>
            <span className='text-xs text-muted-foreground'>Re-attach to:</span>
            {orphans.map((o) => (
              <Button
                key={o.session_id}
                variant='ghost'
                size='sm'
                className='h-7 px-2 font-mono text-xs'
                onClick={() => void openTab(o.session_id, o.argv)}
              >
                {friendlyArgvLabel(o.argv, o.session_id)}
              </Button>
            ))}
          </div>
        )}
      </Card>

      {/* Tab strip */}
      {/* Install dialog (v0.1.28). Surfaces when a quick-launch's binary
          isn't on PATH; the install runs as a real Synapse session so the
          user can watch the output. */}
      {installPrompt && (
        <Modal
          open
          onClose={() => setInstallPrompt(null)}
          labelledBy='install-prompt-title'
        >
          <h2 id='install-prompt-title' className='text-lg font-semibold'>
            {installPrompt.label} isn't installed yet
          </h2>
          <p className='text-sm text-muted-foreground'>
            Synapse will spawn the install command as a regular session so you
            can watch the output. After it's done, click {installPrompt.label}{' '}
            again and you'll land in a real {installPrompt.label} session.
          </p>
          <div className='rounded-md border border-border bg-secondary/40 p-3 font-mono text-xs'>
            $ {installPrompt.install_argv.join(' ')}
          </div>
          <div className='text-xs text-muted-foreground'>
            Requires <span className='font-mono'>{installPrompt.needs}</span>.
            {installPrompt.notes && (
              <>
                <br />
                {installPrompt.notes}
              </>
            )}
          </div>
          <div className='flex flex-wrap justify-end gap-2'>
            <Button
              variant='outline'
              size='sm'
              onClick={() => void openExternal(installPrompt.docs)}
            >
              <ExternalLink className='h-4 w-4' />
              Open docs
            </Button>
            <Button
              size='sm'
              onClick={() => void runInstall(installPrompt)}
            >
              <Download className='h-4 w-4' />
              Run install
            </Button>
          </div>
        </Modal>
      )}

      {tabs.length > 0 && (
        <div role='tablist' aria-label='Open sessions' className='flex flex-wrap items-center gap-1'>
          {tabs.map((t) => {
            const isActive = t.sessionId === active;
            const label = friendlyArgvLabel(t.argv, t.sessionId);
            return (
              <div
                key={t.sessionId}
                role='tab'
                aria-selected={isActive}
                className={cn(
                  'group flex items-center gap-1 rounded-md border px-2 py-1 text-xs transition-colors',
                  isActive
                    ? 'border-primary bg-card text-foreground'
                    : 'border-border bg-secondary/40 text-muted-foreground hover:text-foreground'
                )}
              >
                <button
                  type='button'
                  onClick={() => setActive(t.sessionId)}
                  className='flex items-center gap-1.5 font-mono'
                  title={t.argv.join(' ')}
                >
                  <TerminalIcon className='h-3 w-3' aria-hidden='true' />
                  {label}
                </button>
                <button
                  type='button'
                  onClick={() => void restartTab(t.sessionId)}
                  className='rounded p-0.5 opacity-60 hover:bg-accent hover:opacity-100'
                  aria-label={`Restart session ${label}`}
                  title='Restart this session (close + respawn with the same argv)'
                >
                  <RotateCcw className='h-3 w-3' aria-hidden='true' />
                </button>
                <button
                  type='button'
                  onClick={() => void closeTab(t.sessionId)}
                  className='rounded p-0.5 opacity-60 hover:bg-accent hover:opacity-100'
                  aria-label={`Close session ${label}`}
                >
                  <X className='h-3 w-3' aria-hidden='true' />
                </button>
              </div>
            );
          })}
        </div>
      )}

      {helpOpen && <HelpPanel />}

      {/* Terminal panel — fixed height keeps fit math stable. */}
      {activeTab ? (
        <div className='h-[60vh] min-h-[420px]'>
          <SessionTerminal
            key={activeTab.sessionId}
            sessionId={activeTab.sessionId}
            initialScrollback={activeTab.scrollback ?? undefined}
          />
        </div>
      ) : (
        <Card className='flex flex-col items-center gap-3 border-dashed p-12 text-center'>
          <TerminalSquare className='h-8 w-8 text-muted-foreground' />
          <h3 className='text-lg font-semibold'>No active session</h3>
          <p className='max-w-md text-sm text-muted-foreground'>
            Click a quick-launch above, or type a custom argv. Each session is a real PTY
            and stays alive until you close it -- so you can flip between AI coders and
            shells without losing context.
          </p>
        </Card>
      )}
    </div>
  );
}
