// Project auto-discovery dialog (v0.1.8.5).
//
// Enter a folder, scan it, and Synapse fingerprints every project inside --
// stack, suggested launch command, confidence. Tick the ones to import; the
// launch command stays editable per row. Imported projects are flagged
// `discovered` and land in the registry.

import { useMemo, useState } from 'react';
import { FolderSearch, Loader2 } from 'lucide-react';

import { importProjects, scanForProjects, type ImportItem } from '@shared/discovery-client';
import type { DetectedProject } from '@shared/generated-types';
import { Badge } from './ui/badge';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Modal } from './ui/modal';

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
  const [phase, setPhase] = useState<Phase>('input');
  const [root, setRoot] = useState('');
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
            onChange={(e) => setRoot(e.target.value)}
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
