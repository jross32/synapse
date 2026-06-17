// SessionTerminal — xterm.js bound to a Synapse PTY session (v0.1.26).
//
// Sources of truth:
// - Output : subscribes to `v1.pty.session_output` events on the daemon WS
//            and base64-decodes them straight onto the xterm instance.
// - Input  : xterm's `onData` callback POSTs to /pty/{id}/input as text.
// - Resize : FitAddon recomputes size on container resize; we POST to
//            /pty/{id}/resize so the child sees a fresh TIOCSWINSZ.

import { useCallback, useEffect, useRef, useState } from 'react';
import { ChevronDown, ChevronUp, X } from 'lucide-react';
import { Terminal } from '@xterm/xterm';
import { FitAddon } from '@xterm/addon-fit';
import { SearchAddon } from '@xterm/addon-search';
import '@xterm/xterm/css/xterm.css';

import { useDaemon } from '@shared/daemon-context';
import { closeSession, resizeSession, writeInput } from '@shared/pty-client';
import { cn } from '@shared/utils';

export interface SessionTerminalProps {
  sessionId: string;
  /** Optional initial scrollback (base64) to paint before any live events. */
  initialScrollback?: string;
  onExit?: (exitCode: number | null) => void;
  className?: string;
}

function base64ToUint8(str: string): Uint8Array {
  const binary = atob(str);
  const out = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) out[i] = binary.charCodeAt(i);
  return out;
}

export function SessionTerminal({
  sessionId,
  initialScrollback,
  onExit,
  className,
}: SessionTerminalProps): JSX.Element {
  const { subscribeRaw } = useDaemon();
  const hostRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const termRef = useRef<Terminal | null>(null);
  const fitRef = useRef<FitAddon | null>(null);
  const searchRef = useRef<SearchAddon | null>(null);
  const exitedRef = useRef(false);

  // Ctrl+F search overlay (v0.1.35 · IDEAS). Open with Ctrl/Cmd+F while
  // focus is inside this terminal; Esc closes; Enter/Shift+Enter finds
  // next/prev. xterm SearchAddon highlights inline -- we just feed it.
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const searchInputRef = useRef<HTMLInputElement>(null);

  // Keep the latest onExit callback reachable without rebuilding the
  // terminal each time the parent re-renders.
  const onExitRef = useRef(onExit);
  onExitRef.current = onExit;
  const scrollbackReplayedRef = useRef(false);

  useEffect(() => {
    if (!hostRef.current) return;

    const term = new Terminal({
      convertEol: false,
      cursorBlink: true,
      fontFamily:
        'ui-monospace, SFMono-Regular, "JetBrains Mono", "Cascadia Code", Consolas, monospace',
      fontSize: 13,
      scrollback: 5000,
      theme: {
        background: '#0b0f17',
        foreground: '#e6e9f2',
        cursor: '#7c5cff',
      },
    });
    const fit = new FitAddon();
    const search = new SearchAddon();
    term.loadAddon(fit);
    term.loadAddon(search);
    term.open(hostRef.current);
    termRef.current = term;
    fitRef.current = fit;
    searchRef.current = search;

    // Deferred fit -- xterm's Viewport only finishes its internal setup on the
    // next animation frame, so calling fit() synchronously here can race the
    // renderer ("Cannot read properties of undefined (reading 'dimensions')").
    let initialFitFrame = 0;
    const safeFit = () => {
      const f = fitRef.current;
      const t = termRef.current;
      if (!f || !t) return;
      // Bail if the host has no measurable size yet -- fit() divides by it.
      const rect = hostRef.current?.getBoundingClientRect();
      if (!rect || rect.width < 4 || rect.height < 4) return;
      try {
        f.fit();
      } catch {
        /* swallow -- ResizeObserver will retry */
      }
    };
    initialFitFrame = requestAnimationFrame(() => {
      safeFit();
      // Drain any pending scrollback now that dimensions are real.
      if (initialScrollback && !scrollbackReplayedRef.current) {
        scrollbackReplayedRef.current = true;
        try {
          term.write(base64ToUint8(initialScrollback));
        } catch {
          /* malformed -- skip */
        }
      }
    });

    // Keystroke → POST /input. xterm hands us strings already, including
    // raw control sequences for arrow keys, ESC, etc.
    const inputDisposable = term.onData((data) => {
      if (exitedRef.current) return;
      void writeInput(sessionId, { text: data }).catch((err) => {
        term.write(`\r\n\x1b[31m[synapse] input failed: ${err.message}\x1b[0m\r\n`);
      });
    });

    // Resize the PTY whenever xterm re-fits.
    const resizeDisposable = term.onResize(({ cols, rows }) => {
      void resizeSession(sessionId, rows, cols).catch(() => undefined);
    });

    // Keep xterm in sync with the panel size.
    let lastW = 0;
    let lastH = 0;
    const ro = new ResizeObserver(() => {
      const r = hostRef.current?.getBoundingClientRect();
      if (!r) return;
      if (Math.abs(r.width - lastW) < 1 && Math.abs(r.height - lastH) < 1) return;
      lastW = r.width;
      lastH = r.height;
      safeFit();
    });
    ro.observe(hostRef.current);

    // Subscribe to the daemon's WS event stream and filter to this session.
    const unsubscribe = subscribeRaw((event) => {
      if (event.name === 'v1.pty.session_output') {
        const payload = event.payload as { session_id?: string; data?: string };
        if (payload.session_id !== sessionId || typeof payload.data !== 'string') return;
        try {
          term.write(base64ToUint8(payload.data));
        } catch {
          /* skip malformed chunk */
        }
      } else if (event.name === 'v1.pty.session_exited') {
        const payload = event.payload as { session_id?: string; exit_code?: number };
        if (payload.session_id !== sessionId) return;
        if (exitedRef.current) return;
        exitedRef.current = true;
        const code = typeof payload.exit_code === 'number' ? payload.exit_code : null;
        term.write(
          `\r\n\x1b[2m[synapse] session exited${code !== null ? ` (code ${code})` : ''}\x1b[0m\r\n`
        );
        onExitRef.current?.(code);
      }
    });

    term.focus();

    return () => {
      cancelAnimationFrame(initialFitFrame);
      unsubscribe();
      inputDisposable.dispose();
      resizeDisposable.dispose();
      ro.disconnect();
      term.dispose();
      termRef.current = null;
      fitRef.current = null;
      searchRef.current = null;
    };
    // Intentionally NOT depending on initialScrollback / onExit -- those would
    // tear the terminal down and rebuild it mid-stream. Scrollback is read
    // through a ref-guarded one-shot; onExit goes through onExitRef.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId, subscribeRaw]);

  // Late-arriving scrollback (the parent fetched it async): write it once
  // the terminal is alive, with the same one-shot guard.
  useEffect(() => {
    if (!initialScrollback || scrollbackReplayedRef.current) return;
    const t = termRef.current;
    if (!t) return;
    scrollbackReplayedRef.current = true;
    try {
      t.write(base64ToUint8(initialScrollback));
    } catch {
      /* skip */
    }
  }, [initialScrollback]);

  // Ctrl/Cmd+F to open the search overlay; only when this terminal has
  // focus (or the event fires inside its container). xterm steals most
  // keystrokes, so we capture on the container before xterm sees them.
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    function onKey(e: KeyboardEvent) {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'f') {
        e.preventDefault();
        e.stopPropagation();
        setSearchOpen(true);
        // Defer focus so React commits the input first.
        requestAnimationFrame(() => searchInputRef.current?.focus());
      }
    }
    container.addEventListener('keydown', onKey, true);
    return () => container.removeEventListener('keydown', onKey, true);
  }, []);

  const findNext = useCallback((q: string) => {
    if (!searchRef.current) return;
    if (!q) return;
    searchRef.current.findNext(q);
  }, []);

  const findPrev = useCallback((q: string) => {
    if (!searchRef.current) return;
    if (!q) return;
    searchRef.current.findPrevious(q);
  }, []);

  function closeSearch() {
    setSearchOpen(false);
    setSearchQuery('');
    searchRef.current?.clearDecorations();
    termRef.current?.focus();
  }

  return (
    <div
      ref={containerRef}
      className={cn(
        'relative h-full w-full overflow-hidden rounded-md border border-border bg-[#0b0f17]',
        className
      )}
    >
      <div
        ref={hostRef}
        role='application'
        aria-label={`Terminal session ${sessionId}`}
        className='h-full w-full p-2'
      />
      {searchOpen && (
        <div
          role='search'
          aria-label='Search terminal scrollback'
          className='absolute right-2 top-2 z-10 flex items-center gap-1 rounded-md border border-border bg-card/95 p-1 shadow-lg backdrop-blur'
        >
          <input
            ref={searchInputRef}
            type='text'
            value={searchQuery}
            onChange={(e) => {
              setSearchQuery(e.target.value);
              findNext(e.target.value);
            }}
            onKeyDown={(e) => {
              if (e.key === 'Escape') {
                e.preventDefault();
                closeSearch();
              } else if (e.key === 'Enter') {
                e.preventDefault();
                if (e.shiftKey) findPrev(searchQuery);
                else findNext(searchQuery);
              }
            }}
            placeholder='Find in scrollback…'
            aria-label='Search query'
            className='h-7 w-48 rounded bg-background px-2 font-mono text-xs outline-none ring-0 placeholder:text-muted-foreground focus:ring-1 focus:ring-primary'
          />
          <button
            type='button'
            onClick={() => findPrev(searchQuery)}
            disabled={!searchQuery}
            aria-label='Previous match'
            title='Previous match (Shift+Enter)'
            className='rounded p-1 text-muted-foreground hover:bg-accent hover:text-foreground disabled:cursor-not-allowed disabled:opacity-50'
          >
            <ChevronUp className='h-3.5 w-3.5' aria-hidden='true' />
          </button>
          <button
            type='button'
            onClick={() => findNext(searchQuery)}
            disabled={!searchQuery}
            aria-label='Next match'
            title='Next match (Enter)'
            className='rounded p-1 text-muted-foreground hover:bg-accent hover:text-foreground disabled:cursor-not-allowed disabled:opacity-50'
          >
            <ChevronDown className='h-3.5 w-3.5' aria-hidden='true' />
          </button>
          <button
            type='button'
            onClick={closeSearch}
            aria-label='Close search'
            title='Close (Esc)'
            className='rounded p-1 text-muted-foreground hover:bg-accent hover:text-foreground'
          >
            <X className='h-3.5 w-3.5' aria-hidden='true' />
          </button>
        </div>
      )}
    </div>
  );
}

/** Convenience: programmatically close a session from a button click. */
export async function killSession(id: string): Promise<void> {
  try {
    await closeSession(id);
  } catch {
    /* swallow — UI will refresh and re-render naturally */
  }
}
