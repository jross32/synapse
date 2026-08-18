import { useEffect, useState } from 'react';
import { Loader2, Wrench } from 'lucide-react';

import { apiFetch } from '../lib/api-client';

interface McpTool {
  name: string;
  description: string;
}

interface McpServerTools {
  id: string;
  name: string;
  reachable: boolean;
  transport?: string;
  count?: number;
  error?: string;
  tools: McpTool[];
}

/**
 * What one installed MCP server can actually do, asked of the server itself.
 *
 * An installed server used to be a name in a list: no indication of whether it worked or
 * what it offered. Listing its tools is also the only honest status check available - a
 * server that answers `tools/list` is genuinely up, where a stored "connected" flag is just
 * something somebody wrote down once.
 */
export function McpServerPage({ serverId, blurb }: { serverId: string; blurb: string }) {
  const [data, setData] = useState<McpServerTools | null>(null);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('');

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    apiFetch<McpServerTools>(`/mcp-servers/${serverId}/tools`, { method: 'GET' })
      .then((result) => {
        if (!cancelled) setData(result);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setData({
            id: serverId,
            name: serverId,
            reachable: false,
            error: err instanceof Error ? err.message : String(err),
            tools: [],
          });
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [serverId]);

  const shown = (data?.tools ?? []).filter(
    (tool) =>
      !filter.trim() ||
      tool.name.toLowerCase().includes(filter.toLowerCase()) ||
      tool.description.toLowerCase().includes(filter.toLowerCase())
  );

  return (
    <div className='flex h-full min-h-0 flex-col gap-4 p-5'>
      <header className='shrink-0 space-y-1'>
        <h1 className='text-xl font-semibold tracking-tight'>{data?.name ?? serverId}</h1>
        <p className='text-sm text-muted-foreground'>{blurb}</p>
      </header>

      {loading ? (
        <div className='flex items-center gap-2 text-sm text-muted-foreground'>
          <Loader2 className='h-4 w-4 animate-spin' />
          Asking {serverId} what it can do…
        </div>
      ) : data?.reachable ? (
        <>
          <div className='flex shrink-0 flex-wrap items-center gap-3'>
            <span className='rounded-full border border-emerald-500/40 bg-emerald-500/10 px-3 py-1 text-[11px] uppercase tracking-[0.14em] text-emerald-200'>
              Connected · {data.count ?? data.tools.length} tools · {data.transport}
            </span>
            <input
              value={filter}
              onChange={(event) => setFilter(event.target.value)}
              placeholder='Filter tools…'
              className='min-w-[200px] flex-1 rounded-xl border border-border/70 bg-background/60 px-3 py-1.5 text-sm outline-none focus:border-primary/60'
            />
          </div>

          <div className='min-h-0 flex-1 overflow-y-auto scrollbar-thin'>
            <ul className='grid gap-2 md:grid-cols-2'>
              {shown.map((tool) => (
                <li
                  key={tool.name}
                  className='rounded-xl border border-border/60 bg-background/40 p-3'
                >
                  <div className='flex items-center gap-2'>
                    <Wrench className='h-3.5 w-3.5 shrink-0 text-primary/80' />
                    <code className='font-mono text-xs text-foreground'>{tool.name}</code>
                  </div>
                  {tool.description && (
                    <p className='mt-1 text-xs text-muted-foreground'>{tool.description}</p>
                  )}
                </li>
              ))}
            </ul>
            {shown.length === 0 && (
              <p className='text-sm text-muted-foreground'>Nothing matches “{filter}”.</p>
            )}
          </div>
        </>
      ) : (
        <div className='rounded-2xl border border-amber-500/35 bg-amber-500/10 px-4 py-3 text-sm text-amber-100'>
          <p className='font-medium'>{serverId} did not answer.</p>
          <p className='mt-1 text-xs opacity-90'>{data?.error ?? 'No detail returned.'}</p>
        </div>
      )}
    </div>
  );
}
