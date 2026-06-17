// Keyboard shortcuts help modal (v0.1.35) -- press `?` anywhere outside
// an input to open. Single source of truth for every keybinding the app
// declares so a discoverability gap doesn't grow over time.
//
// New shortcut? Add it to SHORTCUTS below; it appears in the modal AND
// (future work) can drive an actual `useEffect` registration so the
// listing and the behaviour can't drift.

import { Keyboard } from 'lucide-react';

import { Modal } from './ui/modal';

interface Shortcut {
  keys: string[]; // each entry rendered as a separate <kbd>; arrays render with "+" between
  description: string;
  scope: 'global' | 'palette' | 'sessions';
}

const isMac = typeof navigator !== 'undefined' && /mac/i.test(navigator.platform);
const MOD = isMac ? '⌘' : 'Ctrl';

const SHORTCUTS: Shortcut[] = [
  // ── Global ─────────────────────────────────────────────────────────
  { keys: [MOD, 'K'], description: 'Open the command palette (search projects, pages, actions)', scope: 'global' },
  { keys: ['?'], description: 'Show this shortcuts help', scope: 'global' },
  { keys: ['Esc'], description: 'Dismiss the current dialog / popover', scope: 'global' },
  // ── Command palette (when open) ────────────────────────────────────
  { keys: ['↑'], description: 'Previous result', scope: 'palette' },
  { keys: ['↓'], description: 'Next result', scope: 'palette' },
  { keys: ['Enter'], description: 'Run the highlighted action', scope: 'palette' },
  // ── Sessions ───────────────────────────────────────────────────────
  { keys: ['Ctrl', 'C'], description: 'Interrupt the running command inside the active terminal', scope: 'sessions' },
  // xterm.js inherits its own bindings; this is a heads-up not a binding.
];

const SCOPE_LABEL: Record<Shortcut['scope'], string> = {
  global: 'Global',
  palette: 'Command palette (open)',
  sessions: 'Sessions',
};

export interface ShortcutsHelpProps {
  open: boolean;
  onClose: () => void;
}

export function ShortcutsHelp({ open, onClose }: ShortcutsHelpProps): JSX.Element | null {
  if (!open) return null;
  // Group by scope so users can scan to the section they need.
  const grouped = SHORTCUTS.reduce<Record<Shortcut['scope'], Shortcut[]>>(
    (acc, s) => {
      acc[s.scope] = acc[s.scope] ?? [];
      acc[s.scope].push(s);
      return acc;
    },
    { global: [], palette: [], sessions: [] }
  );
  return (
    <Modal open onClose={onClose} labelledBy='shortcuts-title'>
      <div className='flex items-center gap-2'>
        <Keyboard className='h-5 w-5 text-primary' aria-hidden='true' />
        <h2 id='shortcuts-title' className='text-lg font-semibold'>
          Keyboard shortcuts
        </h2>
      </div>
      <p className='text-sm text-muted-foreground'>
        These work from anywhere in the app unless noted. Press{' '}
        <kbd className='rounded border border-border bg-secondary px-1.5 py-0.5 font-mono text-xs'>
          ?
        </kbd>{' '}
        any time to reopen this list.
      </p>
      <div className='flex flex-col gap-4'>
        {(Object.keys(grouped) as Shortcut['scope'][]).map((scope) =>
          grouped[scope].length > 0 ? (
            <section key={scope}>
              <h3 className='mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground'>
                {SCOPE_LABEL[scope]}
              </h3>
              <ul className='flex flex-col gap-1.5'>
                {grouped[scope].map((s, idx) => (
                  <li
                    key={`${scope}-${idx}`}
                    className='flex items-center justify-between gap-3 rounded-md border border-border bg-secondary/30 px-3 py-1.5 text-sm'
                  >
                    <span className='text-foreground'>{s.description}</span>
                    <span className='flex items-center gap-1'>
                      {s.keys.map((k, i) => (
                        <span key={i} className='flex items-center gap-1'>
                          {i > 0 && (
                            <span className='text-xs text-muted-foreground'>+</span>
                          )}
                          <kbd className='rounded border border-border bg-card px-1.5 py-0.5 font-mono text-xs text-foreground'>
                            {k}
                          </kbd>
                        </span>
                      ))}
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          ) : null
        )}
      </div>
    </Modal>
  );
}
