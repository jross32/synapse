// Universal command palette (Contract #21 · v0.1.14) -- one shortcut, every
// action. Ctrl+K (or Cmd+K) opens it; type to filter projects, pages, and
// actions; arrow keys + Enter to run.

import { useEffect, useMemo, useRef, useState } from 'react';
import {
  Activity,
  ArrowRight,
  Boxes,
  CornerDownLeft,
  Download,
  ExternalLink,
  FolderSearch,
  Home,
  Plus,
  Search,
  Settings as SettingsIcon,
  Smartphone,
  Square,
  SunMoon,
  Triangle,
  Wrench,
} from 'lucide-react';

import { useDaemon } from '@shared/daemon-context';
import { launchProject, stopProject } from '@shared/projects-client';
import { exportSnapshot } from '@shared/snapshot-client';
import { openExternal } from '@shared/electron-bridge';
import type { Project } from '@shared/generated-types';
import type { PageId } from '@shared/nav';
import { applyTheme, getStoredTheme, setStoredTheme } from '@shared/theme';
import { cn } from '@shared/utils';
import { Modal } from './ui/modal';

type IconCmp = typeof Wrench;

interface Command {
  id: string;
  label: string;
  hint: string;
  icon: IconCmp;
  searchString: string;
  run: () => void | Promise<void>;
}

const RESULT_CAP = 30;

function timestamp(): string {
  return new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-');
}

function isRunning(p: Project): boolean {
  return p.status === 'launched' || p.status === 'stopping';
}

function buildCommands(args: {
  projects: Project[];
  navigate: (page: PageId) => void;
  onProjectLaunched: (p: Project) => void;
  onProjectStopped: (p: Project) => void;
  onError: (msg: string) => void;
}): Command[] {
  const { projects, navigate, onProjectLaunched, onProjectStopped, onError } = args;
  const list: Command[] = [];

  // Pages
  const pages: Array<{ id: PageId; label: string; icon: IconCmp }> = [
    { id: 'home', label: 'Home', icon: Home },
    { id: 'apps', label: 'Apps', icon: Boxes },
    { id: 'tools', label: 'Tools', icon: Wrench },
    { id: 'processes', label: 'Processes', icon: Activity },
    { id: 'settings', label: 'Settings', icon: SettingsIcon },
  ];
  for (const p of pages) {
    list.push({
      id: `page:${p.id}`,
      label: `Go to ${p.label}`,
      hint: 'Page',
      icon: p.icon,
      searchString: `go to ${p.label} page navigate`,
      run: () => navigate(p.id),
    });
  }

  // Static actions
  list.push({
    id: 'action:add-project',
    label: 'Add a project',
    hint: 'Action',
    icon: Plus,
    searchString: 'add project new create register',
    run: () => navigate('apps'),
  });
  list.push({
    id: 'action:scan',
    label: 'Scan for projects',
    hint: 'Action',
    icon: FolderSearch,
    searchString: 'scan discover find folder auto-discovery',
    run: () => navigate('apps'),
  });
  list.push({
    id: 'action:pair',
    label: 'Pair a device',
    hint: 'Action',
    icon: Smartphone,
    searchString: 'pair device phone mobile code',
    run: () => navigate('settings'),
  });
  list.push({
    id: 'action:snapshot',
    label: 'Download snapshot',
    hint: 'Action',
    icon: Download,
    searchString: 'snapshot export backup download json',
    run: async () => {
      try {
        const snap = await exportSnapshot();
        const blob = new Blob([JSON.stringify(snap, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `synapse-snapshot-${timestamp()}.json`;
        a.click();
        URL.revokeObjectURL(url);
      } catch (err) {
        onError(`Snapshot failed: ${(err as Error).message}`);
      }
    },
  });
  list.push({
    id: 'action:mobile',
    label: 'Open mobile UI in browser',
    hint: 'Action',
    icon: ExternalLink,
    searchString: 'mobile phone open browser web ui',
    run: () => void openExternal('http://localhost:7878/mobile'),
  });
  list.push({
    id: 'action:theme',
    label: 'Toggle light / dark theme',
    hint: 'Action',
    icon: SunMoon,
    searchString: 'theme dark light toggle switch appearance',
    run: () => {
      const next = getStoredTheme() === 'light' ? 'dark' : 'light';
      setStoredTheme(next);
      applyTheme(next);
    },
  });

  // Projects -- contextual action by status
  for (const p of projects) {
    const running = isRunning(p);
    list.push({
      id: `project:${p.id}`,
      label: running ? `Stop ${p.name}` : `Launch ${p.name}`,
      hint: running ? 'Project · running' : 'Project',
      icon: running ? Square : Triangle,
      searchString: `${p.name} ${p.id} ${p.path} project ${running ? 'stop' : 'launch start run'} ${p.group ?? ''} ${(p.tags ?? []).join(' ')}`,
      run: async () => {
        try {
          if (running) onProjectStopped(await stopProject(p.id));
          else onProjectLaunched(await launchProject(p.id));
        } catch (err) {
          onError(`${p.name}: ${(err as Error).message}`);
        }
      },
    });
  }

  return list;
}

// Substring + word-prefix scoring. Higher = better. 0 = no match.
//
// We match symmetrically per word: a query word like "paired" matches a
// search word "pair" (and vice versa) because one is a prefix of the other.
// That keeps the palette useful while the user is mid-typing.
function score(searchString: string, query: string): number {
  const ls = searchString.toLowerCase();
  const lq = query.trim().toLowerCase();
  if (!lq) return 1;
  if (ls.startsWith(lq)) return 1000;
  const idx = ls.indexOf(lq);
  if (idx >= 0) return 500 - idx; // earlier hit ranks higher

  const qWords = lq.split(/\s+/).filter(Boolean);
  const sWords = ls.split(/[\s.,/_-]+/).filter(Boolean);
  if (qWords.every((qw) => sWords.some((sw) => sw.startsWith(qw) || qw.startsWith(sw)))) {
    return 200;
  }
  if (qWords.every((qw) => ls.includes(qw))) return 100;
  return 0;
}

function filterCommands(commands: Command[], query: string): Command[] {
  if (!query.trim()) return commands.slice(0, RESULT_CAP);
  return commands
    .map((c) => ({ c, s: score(c.searchString + ' ' + c.label, query) }))
    .filter((x) => x.s > 0)
    .sort((a, b) => b.s - a.s)
    .slice(0, RESULT_CAP)
    .map((x) => x.c);
}

export interface CommandPaletteProps {
  open: boolean;
  onClose: () => void;
  onNavigate: (page: PageId) => void;
}

export function CommandPalette({ open, onClose, onNavigate }: CommandPaletteProps): JSX.Element {
  const { projects, upsertProjectLocal } = useDaemon();
  const [query, setQuery] = useState('');
  const [selected, setSelected] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLUListElement>(null);

  // Reset state every time the palette opens; focus the input on the next tick.
  useEffect(() => {
    if (!open) return;
    setQuery('');
    setSelected(0);
    setError(null);
    const t = setTimeout(() => inputRef.current?.focus(), 0);
    return () => clearTimeout(t);
  }, [open]);

  const commands = useMemo(
    () =>
      buildCommands({
        projects,
        navigate: (p) => {
          onNavigate(p);
          onClose();
        },
        onProjectLaunched: (p) => {
          upsertProjectLocal(p);
          onClose();
        },
        onProjectStopped: (p) => {
          upsertProjectLocal(p);
          onClose();
        },
        onError: (msg) => setError(msg),
      }),
    [projects, onNavigate, onClose, upsertProjectLocal]
  );

  const filtered = useMemo(() => filterCommands(commands, query), [commands, query]);

  // Clamp selection when the filtered list shrinks.
  useEffect(() => {
    if (selected >= filtered.length) setSelected(0);
  }, [filtered, selected]);

  // Scroll the selected item into view as the user arrows through.
  useEffect(() => {
    const el = listRef.current?.querySelector<HTMLElement>(`[data-idx="${selected}"]`);
    el?.scrollIntoView({ block: 'nearest' });
  }, [selected]);

  function onKeyDown(e: React.KeyboardEvent): void {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setSelected((i) => Math.min(filtered.length - 1, i + 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setSelected((i) => Math.max(0, i - 1));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      const cmd = filtered[selected];
      if (cmd) void cmd.run();
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      labelledBy='command-palette-title'
      className='!max-w-xl !p-0 !gap-0'
    >
      <div className='flex items-center gap-2 border-b border-border px-4 py-3'>
        <Search className='h-4 w-4 shrink-0 text-muted-foreground' />
        <input
          ref={inputRef}
          id='command-palette-title'
          aria-label='Run a command'
          placeholder='Type to launch a project, jump to a page, or run an action…'
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={onKeyDown}
          className='w-full bg-transparent text-sm outline-none placeholder:text-muted-foreground'
        />
      </div>

      <ul
        ref={listRef}
        role='listbox'
        className='max-h-[60vh] overflow-y-auto px-2 py-2'
      >
        {filtered.length === 0 ? (
          <li className='px-3 py-6 text-center text-sm text-muted-foreground'>
            Nothing matches "{query}".
          </li>
        ) : (
          filtered.map((c, i) => {
            const Icon = c.icon;
            const isSelected = i === selected;
            return (
              <li
                key={c.id}
                data-idx={i}
                role='option'
                aria-selected={isSelected}
                onMouseEnter={() => setSelected(i)}
                onClick={() => void c.run()}
                className={cn(
                  'flex cursor-pointer items-center gap-3 rounded-md px-3 py-2 text-sm',
                  isSelected ? 'bg-accent text-accent-foreground' : 'text-foreground'
                )}
              >
                <Icon className='h-4 w-4 shrink-0 text-muted-foreground' />
                <span className='min-w-0 flex-1 truncate'>{c.label}</span>
                <span className='shrink-0 text-xs text-muted-foreground'>{c.hint}</span>
                {isSelected && <CornerDownLeft className='h-3.5 w-3.5 text-muted-foreground' />}
              </li>
            );
          })
        )}
      </ul>

      {error && (
        <p role='alert' className='border-t border-border px-4 py-2 text-xs text-destructive'>
          {error}
        </p>
      )}

      <div className='flex items-center justify-between gap-3 border-t border-border px-4 py-2 text-[11px] text-muted-foreground'>
        <span className='flex items-center gap-2'>
          <Kbd>↑</Kbd>
          <Kbd>↓</Kbd> to navigate
          <Kbd>↵</Kbd> to run
          <Kbd>Esc</Kbd> to close
        </span>
        <span className='flex items-center gap-1'>
          <ArrowRight className='h-3 w-3' /> {filtered.length} result
          {filtered.length === 1 ? '' : 's'}
        </span>
      </div>
    </Modal>
  );
}

function Kbd({ children }: { children: React.ReactNode }): JSX.Element {
  return (
    <kbd className='inline-flex h-5 min-w-5 items-center justify-center rounded border border-border bg-secondary px-1 font-mono text-[10px]'>
      {children}
    </kbd>
  );
}
