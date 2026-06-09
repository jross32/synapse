// Sessions page (v0.1.26 · ADR-0002 Phase A step 2).
//
// One xterm tab per live PTY session, plus a launcher rail to start a new
// one. Quick-launch buttons cover the common cases (Claude, Codex, Python,
// shell); a free-text argv input handles anything else.

import { useEffect, useMemo, useState } from 'react';
import {
  Bot,
  Loader2,
  Plus,
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
  spawnSession,
} from '@shared/pty-client';
import { useDaemon } from '@shared/daemon-context';
import { cn } from '@shared/utils';
import { Button } from '../components/ui/button';
import { Card } from '../components/ui/card';
import { Input } from '../components/ui/input';
import { PageHeader } from '../components/PageHeader';
import { SessionTerminal } from '../components/SessionTerminal';

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

  // Bring the existing session list in on mount so a refresh doesn't lose
  // sessions started from elsewhere (curl / a previous tab).
  useEffect(() => {
    void listSessions().then(setRegistry).catch(() => undefined);
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

  async function spawnAndOpen(argv: string[]): Promise<void> {
    if (argv.length === 0 || !argv[0].trim()) {
      setError('argv must have at least one entry.');
      return;
    }
    setSpawning(true);
    setError(null);
    try {
      const session = await spawnSession({ argv });
      await openTab(session.session_id, session.argv);
      setArgvText('');
    } catch (err) {
      setError((err as Error).message || 'Spawn failed.');
    } finally {
      setSpawning(false);
    }
  }

  async function closeTab(sessionId: string): Promise<void> {
    try {
      await closeSession(sessionId);
    } catch {
      /* if it's already gone, just drop the tab */
    }
    setTabs((prev) => prev.filter((t) => t.sessionId !== sessionId));
    if (active === sessionId) {
      const remaining = tabs.filter((t) => t.sessionId !== sessionId);
      setActive(remaining[0]?.sessionId ?? null);
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
                onClick={() => void spawnAndOpen(q.argv)}
              >
                <Icon className='h-4 w-4' />
                {q.label}
              </Button>
            );
          })}
        </div>
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
                {o.argv.slice(-1).pop() ?? o.session_id}
              </Button>
            ))}
          </div>
        )}
      </Card>

      {/* Tab strip */}
      {tabs.length > 0 && (
        <div role='tablist' aria-label='Open sessions' className='flex flex-wrap items-center gap-1'>
          {tabs.map((t) => {
            const isActive = t.sessionId === active;
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
                >
                  <TerminalIcon className='h-3 w-3' />
                  {t.argv[0] ?? t.sessionId}
                </button>
                <button
                  type='button'
                  onClick={() => void closeTab(t.sessionId)}
                  className='rounded p-0.5 opacity-60 hover:bg-accent hover:opacity-100'
                  aria-label={`Close session ${t.sessionId}`}
                >
                  <X className='h-3 w-3' />
                </button>
              </div>
            );
          })}
        </div>
      )}

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
