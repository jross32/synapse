// Project auto-discovery dialog (v0.1.8.5).
//
// Enter a folder, scan it, and Synapse fingerprints every project inside --
// stack, suggested launch command, confidence. Tick the ones to import; the
// launch command stays editable per row. Imported projects are flagged
// `discovered` and land in the registry.

import { useMemo, useState } from 'react';
import { FolderSearch, Loader2 } from 'lucide-react';

import { importProjects, scanForProjects, type ImportItem } from '@shared/discovery-client';
import { useDaemon } from '@shared/daemon-context';
import type { DetectedProject } from '@shared/generated-types';
import { kindMeta } from '@shared/project-kinds';
import { cn } from '@shared/utils';
import { Badge } from './ui/badge';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Modal } from './ui/modal';

/** The directory (drive + first 3 path segments, e.g. `C:\Users\justi`) that
 * the MOST registered projects have in common -- inferred from what
 * Synapse already knows rather than needing a new IPC call to the OS for a
 * home-directory path. Deliberately a mode (majority wins), not a strict
 * everyone-must-share-a-prefix comparison: found live 2026-08-25 that a
 * single outlier registered with a relative path ("Quick-action
 * scratchpad", `data\projects\scratch`) zeroed out a first-item-vs-
 * everyone-else prefix comparison completely, even though 29 of the other
 * 30 projects agreed perfectly on `C:\Users\justi`. One odd entry should
 * never be able to blank out an otherwise-obvious answer -- a project
 * living squarely under that home dir (RackPilot) was never found by a
 * scan because nobody had typed the root in by hand, and this field
 * defaulting to empty every time is exactly why nobody thought to. */
export function commonParentDir(paths: string[], depth = 3): string {
  const isAbsolute = (p: string) => /^[a-zA-Z]:[\\/]/.test(p) || p.startsWith('/');
  const splitPath = (p: string) => p.split(/[\\/]+/).filter(Boolean);
  const counts = new Map<string, { count: number; original: string[] }>();
  for (const p of paths) {
    if (!isAbsolute(p)) continue;
    const segs = splitPath(p);
    if (segs.length < depth) continue;
    const prefix = segs.slice(0, depth);
    const key = prefix.join('\\').toLowerCase();
    const existing = counts.get(key);
    if (existing) existing.count += 1;
    else counts.set(key, { count: 1, original: prefix });
  }
  let best: { count: number; original: string[] } | null = null;
  for (const entry of counts.values()) {
    if (!best || entry.count > best.count) best = entry;
  }
  return best ? best.original.join('\\') : '';
}

export interface DiscoveryDialogProps {
  open: boolean;
  onClose: () => void;
  onImported: (count: number) => void;
}

type Phase = 'input' | 'scanning' | 'results' | 'importing';

interface Row {
  detected: DetectedProject;
  selected: boolean;
  launchCmd: string;
}

const STACK_TONE: Record<string, string> = {
  node: 'bg-status-launched/20 text-status-launched',
  'python-django': 'bg-primary/20 text-primary',
  python: 'bg-primary/20 text-primary',
  rust: 'bg-status-launching/20 text-status-launching',
  go: 'bg-status-launched/20 text-status-launched',
  'docker-compose': 'bg-status-launching/20 text-status-launching',
  static: 'bg-muted text-muted-foreground',
  unknown: 'bg-muted text-muted-foreground',
};

export function DiscoveryDialog({ open, onClose, onImported }: DiscoveryDialogProps): JSX.Element | null {
  const { projects } = useDaemon();
  const [phase, setPhase] = useState<Phase>('input');
  // `null` = no explicit override yet -> derive from the registry (below).
  // A real string (including "") once the user has typed/cleared the
  // field, so their choice always wins over the computed guess.
  //
  // This is a plain render-time useMemo, not a useEffect reacting to
  // `projects` changing -- found live that the effect version could get
  // stuck permanently blank: both of its early runs happened to land
  // before DaemonProvider's initial project fetch resolved (its first
  // render always starts from an empty list while that request is in
  // flight), and it never got a later chance to recompute. A memo has no
  // such race -- it recalculates from whatever `projects` the CURRENT
  // render actually has, every render, so there is no "too early" moment
  // for it to get stuck on.
  const [rootOverride, setRootOverride] = useState<string | null>(null);
  const defaultRoot = useMemo(() => commonParentDir(projects.map((p) => p.path)), [projects]);
  const root = rootOverride ?? defaultRoot;
  const [depth, setDepth] = useState('2');
  const [rows, setRows] = useState<Row[]>([]);
  const [scanRoot, setScanRoot] = useState('');
  const [error, setError] = useState<string | null>(null);

  const selectableCount = useMemo(
    () => rows.filter((r) => !r.detected.already_registered).length,
    [rows]
  );
  const selectedCount = useMemo(() => rows.filter((r) => r.selected).length, [rows]);

  async function handleScan(): Promise<void> {
    setPhase('scanning');
    setError(null);
    try {
      const res = await scanForProjects(root, Math.max(1, Math.min(Number(depth) || 2, 4)));
      setScanRoot(res.root);
      setRows(
        res.projects.map((d) => ({
          detected: d,
          // Pre-select confident, not-yet-registered projects that have a command.
          selected: !d.already_registered && d.confidence >= 0.6 && !!d.suggested_launch_cmd,
          launchCmd: d.suggested_launch_cmd ?? '',
        }))
      );
      setPhase('results');
    } catch (err) {
      setError((err as Error).message);
      setPhase('input');
    }
  }

  async function handleImport(): Promise<void> {
    const picks: ImportItem[] = rows
      .filter((r) => r.selected && !r.detected.already_registered)
      .map((r) => ({
        id: r.detected.suggested_id,
        name: r.detected.name,
        path: r.detected.path,
        launch_cmd: r.launchCmd.trim() || 'echo set-a-launch-command',
        description: r.detected.description,
        expected_port: r.detected.suggested_port,
        icon: r.detected.icon,
        tags: r.detected.stack !== 'unknown' ? [r.detected.stack] : [],
        kind: r.detected.kind,
      }));
    if (picks.length === 0) {
      onClose();
      return;
    }
    setPhase('importing');
    setError(null);
    try {
      const report = await importProjects(picks);
      onImported(report.imported.length);
      reset();
    } catch (err) {
      setError((err as Error).message);
      setPhase('results');
    }
  }

  function reset(): void {
    setPhase('input');
    setRows([]);
    setError(null);
    // Each fresh open re-derives the default from the registry's current
    // state, rather than carrying forward whatever the user last typed.
    setRootOverride(null);
  }

  function toggle(path: string): void {
    setRows((prev) => prev.map((r) => (r.detected.path === path ? { ...r, selected: !r.selected } : r)));
  }

  function setCmd(path: string, cmd: string): void {
    setRows((prev) => prev.map((r) => (r.detected.path === path ? { ...r, launchCmd: cmd } : r)));
  }

  return (
    <Modal
      open={open}
      onClose={() => {
        reset();
        onClose();
      }}
      labelledBy='discovery-title'
      className='max-w-3xl'
      dismissable={phase !== 'scanning' && phase !== 'importing'}
    >
      <h2 id='discovery-title' className='flex items-center gap-2 text-xl font-semibold'>
        <FolderSearch className='h-5 w-5 text-primary' /> Scan for projects
      </h2>
      <p className='text-sm text-muted-foreground'>
        Point Synapse at a folder. It fingerprints every project inside — any stack — and
        suggests how to launch each one. Imported projects stay local.
      </p>

      {/* Folder input */}
      <div className='flex items-end gap-2'>
        <label className='flex flex-1 flex-col gap-1.5'>
          <span className='text-sm text-muted-foreground'>Folder to scan</span>
          <Input
            value={root}
            onChange={(e) => setRootOverride(e.target.value)}
            placeholder='Leave blank to scan your home folder'
          />
        </label>
        <label className='flex w-24 flex-col gap-1.5'>
          <span className='text-sm text-muted-foreground'>Depth</span>
          <Input
            value={depth}
            onChange={(e) => setDepth(e.target.value.replace(/[^1-4]/g, ''))}
            inputMode='numeric'
          />
        </label>
        <Button onClick={handleScan} disabled={phase === 'scanning' || phase === 'importing'}>
          {phase === 'scanning' ? <Loader2 className='h-4 w-4 animate-spin' /> : <FolderSearch className='h-4 w-4' />}
          Scan
        </Button>
      </div>

      {error && (
        <p role='alert' className='text-sm text-destructive'>
          {error}
        </p>
      )}

      {/* Results */}
      {phase === 'scanning' && (
        <p className='py-8 text-center text-sm text-muted-foreground'>Scanning…</p>
      )}

      {(phase === 'results' || phase === 'importing') && (
        <>
          <p className='text-xs text-muted-foreground'>
            {rows.length} found in <span className='font-mono'>{scanRoot}</span> ·{' '}
            {selectedCount} selected of {selectableCount} importable
          </p>
          <div className='flex max-h-[42vh] flex-col gap-2 overflow-y-auto'>
            {rows.length === 0 && (
              <p className='py-6 text-center text-sm text-muted-foreground'>
                No projects found in that folder. Try a different path or a deeper scan.
              </p>
            )}
            {rows.map((r) => (
              <DiscoveryRow key={r.detected.path} row={r} onToggle={toggle} onSetCmd={setCmd} />
            ))}
          </div>
        </>
      )}

      <div className='flex justify-end gap-2'>
        <Button
          variant='outline'
          onClick={() => {
            reset();
            onClose();
          }}
          disabled={phase === 'scanning' || phase === 'importing'}
        >
          Cancel
        </Button>
        {(phase === 'results' || phase === 'importing') && (
          <Button onClick={handleImport} disabled={phase === 'importing' || selectedCount === 0}>
            {phase === 'importing'
              ? 'Importing…'
              : `Import ${selectedCount} project${selectedCount === 1 ? '' : 's'}`}
          </Button>
        )}
      </div>
    </Modal>
  );
}

function DiscoveryRow({
  row,
  onToggle,
  onSetCmd,
}: {
  row: Row;
  onToggle: (path: string) => void;
  onSetCmd: (path: string, cmd: string) => void;
}): JSX.Element {
  const { detected: d } = row;
  const tone = STACK_TONE[d.stack] ?? STACK_TONE.unknown;
  const disabled = d.already_registered;

  return (
    <div
      className={`rounded-md border border-border p-3 ${disabled ? 'opacity-50' : ''}`}
    >
      <div className='flex items-start gap-3'>
        <input
          type='checkbox'
          className='mt-1 h-4 w-4 accent-[hsl(var(--primary))]'
          checked={row.selected && !disabled}
          disabled={disabled}
          onChange={() => onToggle(d.path)}
        />
        <div className='min-w-0 flex-1'>
          <div className='flex flex-wrap items-center gap-2'>
            <span className='font-medium'>{d.name}</span>
            <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${tone}`}>{d.stack}</span>
            {d.kind && d.kind !== 'app' && (() => {
              const km = kindMeta(d.kind);
              const KIcon = km.icon;
              return (
                <span
                  className={cn(
                    'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium',
                    km.badgeClass
                  )}
                  title={`Detected as ${km.label}`}
                >
                  <KIcon className='h-2.5 w-2.5' />
                  {km.label}
                </span>
              );
            })()}
            <span className='text-[10px] text-muted-foreground'>
              {Math.round(d.confidence * 100)}% match
            </span>
            {disabled && <Badge variant='secondary'>already added</Badge>}
          </div>
          <p className='mt-0.5 break-words font-mono text-xs text-muted-foreground'>{d.path}</p>
          {!disabled && (
            <Input
              className='mt-2 h-8 font-mono text-xs'
              value={row.launchCmd}
              placeholder='set a launch command'
              onChange={(e) => onSetCmd(d.path, e.target.value)}
            />
          )}
        </div>
      </div>
    </div>
  );
}
