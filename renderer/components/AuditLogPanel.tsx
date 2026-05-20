// Audit log panel (Contract #11 · v0.1.17) -- Settings page.
//
// Surfaces the daemon's audit_log table in the UI: every state-changing
// action Synapse has taken, newest first. Useful for "what just happened?"
// debugging and seeing exactly what a mobile device or the tray did.

import { useEffect, useMemo, useState } from 'react';
import { Loader2, RefreshCw, ScrollText, Search } from 'lucide-react';

import type { AuditEntry } from '@shared/generated-types';
import { listAudit } from '@shared/audit-client';
import { formatLocal } from '@shared/format-time';
import { cn } from '@shared/utils';
import { Button } from './ui/button';
import { Card } from './ui/card';
import { Input } from './ui/input';

const PAGE_SIZE = 200;

function sourceLabel(src: string): string {
  switch (src) {
    case 'desktop':
      return 'Desktop';
    case 'mobile':
      return 'Mobile';
    case 'tray':
      return 'Tray';
    case 'cli':
      return 'CLI';
    case 'auto':
      return 'Auto';
    default:
      return src;
  }
}

function matches(entry: AuditEntry, q: string): boolean {
  if (!q) return true;
  const hay = [
    entry.entity_type,
    entry.entity_id ?? '',
    entry.action,
    entry.source,
    entry.result,
    entry.error_code ?? '',
  ]
    .join(' ')
    .toLowerCase();
  return q
    .toLowerCase()
    .split(/\s+/)
    .filter(Boolean)
    .every((w) => hay.includes(w));
}

export function AuditLogPanel(): JSX.Element {
  const [entries, setEntries] = useState<AuditEntry[] | null>(null);
  const [total, setTotal] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState('');

  async function refresh(): Promise<void> {
    setBusy(true);
    setError(null);
    try {
      const res = await listAudit(PAGE_SIZE);
      setEntries(res.entries);
      setTotal(res.total);
    } catch (err) {
      setError((err as Error).message || 'Failed to load audit log');
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const filtered = useMemo(
    () => (entries ? entries.filter((e) => matches(e, query)) : []),
    [entries, query]
  );

  return (
    <Card className='flex flex-col gap-4 p-6'>
      <div className='flex items-start justify-between gap-3'>
        <div>
          <h2 className='text-lg font-semibold'>Audit log</h2>
          <p className='mt-1 text-sm text-muted-foreground'>
            Every state-changing action Synapse has taken — launches, stops, project edits,
            tool actions, device pairings. Newest first.
          </p>
        </div>
        <Button
          variant='outline'
          size='sm'
          disabled={busy}
          onClick={() => void refresh()}
          aria-label='Refresh audit log'
        >
          {busy ? <Loader2 className='h-4 w-4 animate-spin' /> : <RefreshCw className='h-4 w-4' />}
          Refresh
        </Button>
      </div>

      <div className='flex flex-wrap items-center gap-3'>
        <div className='relative grow sm:max-w-md'>
          <Search className='pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground' />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder='Filter by entity, action, source…'
            className='pl-9'
            aria-label='Filter audit log'
          />
        </div>
        <span className='text-xs text-muted-foreground'>
          {query
            ? `${filtered.length} of ${entries?.length ?? 0} shown · ${total} total`
            : `${entries?.length ?? 0} shown · ${total} total`}
        </span>
      </div>

      {error && (
        <p role='alert' className='text-sm text-destructive'>
          {error}
        </p>
      )}

      {entries === null && !error ? (
        <div className='flex items-center justify-center gap-2 py-8 text-sm text-muted-foreground'>
          <Loader2 className='h-4 w-4 animate-spin' /> Loading audit log…
        </div>
      ) : filtered.length === 0 ? (
        <div className='flex flex-col items-center gap-2 py-8 text-sm text-muted-foreground'>
          <ScrollText className='h-6 w-6' />
          {entries?.length === 0
            ? 'No audit entries yet.'
            : `Nothing matches "${query}".`}
        </div>
      ) : (
        <ul
          className='flex max-h-[420px] flex-col divide-y divide-border overflow-y-auto rounded-md border border-border bg-secondary/30'
          role='log'
        >
          {filtered.map((e) => (
            <li key={e.id} className='grid grid-cols-[110px_1fr_auto] items-baseline gap-3 px-3 py-2 text-xs'>
              <span className='font-mono text-muted-foreground'>
                {formatLocal(e.timestamp_utc, 'time')}
              </span>
              <div className='min-w-0'>
                <div className='flex items-baseline gap-2'>
                  <span className='font-mono text-foreground'>{e.entity_type}</span>
                  {e.entity_id && (
                    <span className='truncate font-mono text-muted-foreground'>
                      {e.entity_id}
                    </span>
                  )}
                  <span className='font-mono font-medium text-primary'>{e.action}</span>
                </div>
                {e.error_code && (
                  <div className='mt-0.5 font-mono text-[11px] text-destructive'>
                    {e.error_code}
                  </div>
                )}
              </div>
              <span className='flex items-center gap-2'>
                <span
                  className={cn(
                    'rounded-full px-1.5 py-0.5 text-[10px] font-medium',
                    e.result === 'error'
                      ? 'bg-destructive/15 text-destructive'
                      : 'bg-status-launched/15 text-status-launched'
                  )}
                >
                  {e.result}
                </span>
                <span className='font-mono text-[10px] text-muted-foreground'>
                  {sourceLabel(e.source)}
                </span>
              </span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
