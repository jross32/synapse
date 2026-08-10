// Local AI -- code with a model running on this machine, at no API cost.
//
// The engine is deliberately not started until the first prompt: a resident 5 GB model on a
// 16 GB laptop is a real cost to everything else the user is doing. That makes the cold-start
// wait a first-class part of the interface rather than an embarrassment to hide, so the
// stream's phases (engine starting / model loading / connected) are shown as they happen.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  AlertTriangle,
  ArrowUp,
  Check,
  Cpu,
  Gauge,
  Loader2,
  MessageSquarePlus,
  Square,
  Trash2,
  Wrench,
} from 'lucide-react';

import {
  createLocalChat,
  deleteLocalChat,
  getLocalAiOverview,
  getLocalChatMessages,
  listLocalChats,
  patchLocalChat,
  streamLocalChat,
  MODE_LABELS,
  type LocalAiOverview,
  type LocalChat,
  type LocalChatMessage,
  type PermissionMode,
  type StreamEvent,
} from '@shared/local-ai-client';
import { cn } from '@shared/utils';
import { Button } from '../components/ui/button';
import { Card } from '../components/ui/card';
import { LocalAiHowTo } from '../components/LocalAiHowTo';
import { PageHeader } from '../components/PageHeader';

const SELECT_CLASS =
  'h-8 rounded-md border border-input bg-transparent px-2 text-xs text-foreground';

/** A tool call as the transcript shows it. */
interface ToolEntry {
  name: string;
  args: Record<string, unknown>;
  result?: string;
}

/** What is rendered in the thread: stored messages plus the in-flight reply. */
interface Bubble {
  role: 'user' | 'assistant';
  content: string;
  tools?: ToolEntry[];
  pending?: boolean;
}

export interface LocalAiPageProps {
  headerless?: boolean;
}

export function LocalAiPage({ headerless = false }: LocalAiPageProps): JSX.Element {
  const [overview, setOverview] = useState<LocalAiOverview | null>(null);
  const [chats, setChats] = useState<LocalChat[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [bubbles, setBubbles] = useState<Bubble[]>([]);
  const [draft, setDraft] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [phase, setPhase] = useState<{ label: string; detail?: string } | null>(null);
  const [error, setError] = useState<{ message: string; remedy?: string } | null>(null);
  const [loading, setLoading] = useState(true);

  const abortRef = useRef<(() => void) | null>(null);
  const threadRef = useRef<HTMLDivElement | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  // Mirrors `streaming` for use inside effects and stream callbacks, where the state
  // value would be captured stale. Without this, selecting/creating a chat mid-stream
  // reloads the transcript from the database and wipes the reply being streamed.
  const streamingRef = useRef(false);

  const activeChat = useMemo(
    () => chats.find((c) => c.id === activeId) ?? null,
    [chats, activeId],
  );

  // ── loading ────────────────────────────────────────────────────────────────

  const refreshChats = useCallback(async () => {
    try {
      setChats(await listLocalChats());
    } catch {
      /* the list is a convenience; a failure here shouldn't blank the page */
    }
  }, []);

  useEffect(() => {
    void (async () => {
      setLoading(true);
      try {
        const [ov] = await Promise.all([getLocalAiOverview(), refreshChats()]);
        setOverview(ov);
      } catch (err) {
        setError({ message: (err as Error)?.message ?? 'Could not reach the daemon.' });
      } finally {
        setLoading(false);
      }
    })();
  }, [refreshChats]);

  useEffect(() => {
    if (!activeId) {
      setBubbles([]);
      return;
    }
    // A send() that creates its chat sets activeId mid-flight; reloading here would
    // replace the streaming bubbles with the database's view (just the user message).
    if (streamingRef.current) return;
    void (async () => {
      try {
        const msgs = await getLocalChatMessages(activeId);
        setBubbles(messagesToBubbles(msgs));
      } catch {
        setBubbles([]);
      }
    })();
  }, [activeId]);

  // Keep the newest message in view while tokens arrive.
  useEffect(() => {
    threadRef.current?.scrollTo({ top: threadRef.current.scrollHeight });
  }, [bubbles, phase]);

  // ── actions ────────────────────────────────────────────────────────────────

  const defaultModel = useMemo(() => {
    if (!overview?.models?.length) return '';
    // Prefer the model measured best for agent work; it is the one that can use tools.
    const agent = overview.recommendations.find((r) => r.role === 'tool_agent' && r.model);
    return agent?.model ?? overview.models[0].name;
  }, [overview]);

  const newChat = useCallback(async () => {
    if (!defaultModel) return;
    try {
      const chat = await createLocalChat({ model: defaultModel, mode: 'auto' });
      setChats((prev) => [chat, ...prev]);
      setActiveId(chat.id);
      setBubbles([]);
      setError(null);
      textareaRef.current?.focus();
    } catch (err) {
      setError({ message: (err as Error)?.message ?? 'Could not start a new chat.' });
    }
  }, [defaultModel]);

  const removeChat = useCallback(async (id: string) => {
    try {
      await deleteLocalChat(id);
      setChats((prev) => prev.filter((c) => c.id !== id));
      setActiveId((cur) => (cur === id ? null : cur));
    } catch {
      /* leave the row in place if the delete failed */
    }
  }, []);

  const changeMode = useCallback(async (mode: PermissionMode) => {
    if (!activeChat) return;
    setChats((prev) => prev.map((c) => (c.id === activeChat.id ? { ...c, mode } : c)));
    try {
      await patchLocalChat(activeChat.id, { mode });
    } catch {
      /* optimistic; the next load corrects it */
    }
  }, [activeChat]);

  const changeModel = useCallback(async (model: string) => {
    if (!activeChat) return;
    setChats((prev) => prev.map((c) => (c.id === activeChat.id ? { ...c, model } : c)));
    try {
      await patchLocalChat(activeChat.id, { model });
    } catch {
      /* optimistic */
    }
  }, [activeChat]);

  const send = useCallback(async () => {
    const prompt = draft.trim();
    if (!prompt || streaming) return;

    let chatId = activeId;
    if (!chatId) {
      if (!defaultModel) return;
      const chat = await createLocalChat({ model: defaultModel, mode: 'auto' });
      setChats((prev) => [chat, ...prev]);
      setActiveId(chat.id);
      chatId = chat.id;
    }

    setDraft('');
    setError(null);
    streamingRef.current = true;
    setStreaming(true);
    setPhase({ label: 'Sending' });
    setBubbles((prev) => [...prev, { role: 'user', content: prompt },
                          { role: 'assistant', content: '', pending: true, tools: [] }]);

    const patchLast = (fn: (b: Bubble) => Bubble) =>
      setBubbles((prev) => {
        const next = [...prev];
        for (let i = next.length - 1; i >= 0; i -= 1) {
          if (next[i].role === 'assistant') {
            next[i] = fn(next[i]);
            break;
          }
        }
        return next;
      });

    abortRef.current = streamLocalChat(
      chatId,
      prompt,
      {
        onEvent: (ev: StreamEvent) => {
          switch (ev.type) {
            case 'status':
              if (ev.phase === 'engine_starting')
                setPhase({ label: 'Starting the local engine' });
              else if (ev.phase === 'model_loading')
                setPhase({ label: `Loading ${ev.model ?? 'the model'}`,
                           detail: 'First reply after a cold start takes longer.' });
              else if (ev.phase === 'ready')
                setPhase(null);
              break;
            case 'token':
              setPhase(null);
              patchLast((b) => ({ ...b, content: b.content + ev.text }));
              break;
            case 'tool_start':
              patchLast((b) => ({ ...b,
                tools: [...(b.tools ?? []), { name: ev.name, args: ev.arguments }] }));
              break;
            case 'tool_end':
              patchLast((b) => {
                const tools = [...(b.tools ?? [])];
                for (let i = tools.length - 1; i >= 0; i -= 1) {
                  if (tools[i].name === ev.name && tools[i].result === undefined) {
                    tools[i] = { ...tools[i], result: ev.result };
                    break;
                  }
                }
                return { ...b, tools };
              });
              break;
            case 'error':
              setError({ message: ev.message, remedy: ev.remedy });
              setPhase(null);
              break;
            case 'done':
              setPhase(null);
              break;
            default:
              break;
          }
        },
        onDone: () => {
          streamingRef.current = false;
          setStreaming(false);
          setPhase(null);
          patchLast((b) => ({ ...b, pending: false }));
          void refreshChats();
          // Re-read the stored transcript: the server is the source of truth for how the
          // turn was actually recorded.
          void (async () => {
            try {
              setBubbles(messagesToBubbles(await getLocalChatMessages(chatId)));
            } catch {
              /* keep what streamed if the reload fails */
            }
          })();
        },
        onError: (message) => {
          streamingRef.current = false;
          setStreaming(false);
          setPhase(null);
          setError({ message });
          patchLast((b) => ({ ...b, pending: false }));
        },
      },
    );
  }, [draft, streaming, activeId, defaultModel, refreshChats]);

  const stop = useCallback(() => {
    abortRef.current?.();
    abortRef.current = null;
    streamingRef.current = false;
    setStreaming(false);
    setPhase(null);
  }, []);

  // ── empty / blocked states ────────────────────────────────────────────────

  if (loading) {
    return (
      <div className='flex h-full items-center justify-center'>
        <Card className='flex items-center gap-2 p-6 text-sm text-muted-foreground'>
          <Loader2 className='h-4 w-4 animate-spin' /> Checking what this machine can run...
        </Card>
      </div>
    );
  }

  if (overview && !overview.ollama_installed) {
    return (
      <div className='flex h-full items-center justify-center p-6'>
        <Card className='flex max-w-lg flex-col items-center gap-3 border-dashed p-8 text-center'>
          <Cpu className='h-8 w-8 text-primary' />
          <h2 className='text-lg font-semibold'>No local engine installed</h2>
          <p className='text-sm text-muted-foreground'>
            Local models run through Ollama. Once it is installed, models you download appear
            here and run entirely on this machine, at no API cost.
          </p>
          <code className='rounded-md bg-card px-3 py-2 font-mono text-xs'>
            winget install Ollama.Ollama
          </code>
        </Card>
      </div>
    );
  }

  const hw = overview?.hardware;

  return (
    <div className='flex h-full min-h-0 flex-col'>
      {!headerless && (
        <PageHeader
          title='Local AI'
          subtitle='Code with a model running on this machine. No API cost.'
        />
      )}

      {/* Collapsed by default: it is reference material, not something to scroll past
          every visit. Expanding it costs nothing and it never pushes the chat off-screen. */}
      <div className='mb-3 shrink-0'>
        <LocalAiHowTo playbook={overview?.playbook} />
      </div>

      <div className='flex min-h-0 flex-1 gap-3'>
        {/* ── conversations ─────────────────────────────────────────────── */}
        <aside className='hidden w-60 shrink-0 flex-col gap-2 md:flex'>
          <Button onClick={() => void newChat()} className='w-full justify-start gap-2' size='sm'>
            <MessageSquarePlus className='h-4 w-4' /> New chat
          </Button>
          <div className='min-h-0 flex-1 space-y-1 overflow-y-auto scrollbar-thin pr-1'>
            {chats.length === 0 && (
              <p className='px-2 py-6 text-center text-xs text-muted-foreground'>
                No conversations yet.
              </p>
            )}
            {chats.map((chat) => (
              <div
                key={chat.id}
                className={cn(
                  'group flex items-center gap-1 rounded-md px-2 py-1.5 text-sm',
                  chat.id === activeId ? 'bg-accent text-accent-foreground' : 'hover:bg-accent/50',
                )}
              >
                <button
                  type='button'
                  onClick={() => setActiveId(chat.id)}
                  className='min-w-0 flex-1 truncate text-left'
                  title={chat.title}
                >
                  {chat.title}
                </button>
                <button
                  type='button'
                  aria-label={`Delete ${chat.title}`}
                  onClick={() => void removeChat(chat.id)}
                  className='opacity-0 transition-opacity group-hover:opacity-100'
                >
                  <Trash2 className='h-3.5 w-3.5 text-muted-foreground hover:text-destructive' />
                </button>
              </div>
            ))}
          </div>
          {hw && (
            <p className='px-2 pb-1 text-[11px] leading-tight text-muted-foreground'>
              {hw.gpus[0]?.name ?? 'CPU only'}
              {hw.vram_gb > 0 && ` · ${hw.vram_gb} GB VRAM`}
            </p>
          )}
        </aside>

        {/* ── thread ────────────────────────────────────────────────────── */}
        <section className='flex min-h-0 min-w-0 flex-1 flex-col'>
          <div ref={threadRef} className='min-h-0 flex-1 overflow-y-auto scrollbar-thin px-1'>
            {bubbles.length === 0 ? (
              <div className='flex h-full flex-col items-center justify-center gap-2 text-center'>
                <Cpu className='h-7 w-7 text-muted-foreground' />
                <p className='text-sm text-muted-foreground'>
                  Ask it to build something. It runs on your machine.
                </p>
              </div>
            ) : (
              <div className='mx-auto flex max-w-3xl flex-col gap-4 py-4'>
                {bubbles.map((b, i) => (
                  <MessageBubble key={i} bubble={b} />
                ))}
              </div>
            )}

            {phase && (
              <div className='mx-auto flex max-w-3xl items-center gap-2 px-1 pb-3 text-sm text-muted-foreground'>
                <Loader2 className='h-4 w-4 animate-spin' />
                <span>{phase.label}</span>
                {phase.detail && <span className='text-xs opacity-70'>{phase.detail}</span>}
              </div>
            )}

            {error && (
              <div
                role='alert'
                className='mx-auto mb-3 flex max-w-3xl items-start gap-2 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm'
              >
                <AlertTriangle className='mt-0.5 h-4 w-4 shrink-0 text-destructive' />
                <div>
                  <p>{error.message}</p>
                  {error.remedy && (
                    <p className='mt-0.5 text-xs text-muted-foreground'>{error.remedy}</p>
                  )}
                </div>
              </div>
            )}
          </div>

          {/* ── composer ────────────────────────────────────────────────── */}
          <div className='mx-auto w-full max-w-3xl shrink-0 pt-2'>
            <Card className='flex flex-col gap-2 p-2'>
              <textarea
                ref={textareaRef}
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    void send();
                  }
                }}
                rows={2}
                placeholder='Ask the local model to build or change something...'
                className='max-h-48 w-full resize-none bg-transparent px-2 py-1 text-sm outline-none'
              />
              <div className='flex flex-wrap items-center gap-2'>
                <select
                  aria-label='Model'
                  className={SELECT_CLASS}
                  value={activeChat?.model ?? defaultModel}
                  onChange={(e) => void changeModel(e.target.value)}
                >
                  {(overview?.models ?? []).map((m) => (
                    <option key={m.name} value={m.name}>
                      {m.name}
                      {m.median_tok_per_s ? ` · ${m.median_tok_per_s} tok/s` : ''}
                    </option>
                  ))}
                </select>

                <select
                  aria-label='Permission mode'
                  className={SELECT_CLASS}
                  value={activeChat?.mode ?? 'auto'}
                  onChange={(e) => void changeMode(e.target.value as PermissionMode)}
                  title={MODE_LABELS[(activeChat?.mode ?? 'auto') as PermissionMode].hint}
                >
                  {(Object.keys(MODE_LABELS) as PermissionMode[]).map((m) => (
                    <option key={m} value={m}>
                      {MODE_LABELS[m].label}
                    </option>
                  ))}
                </select>

                <span className='hidden text-[11px] text-muted-foreground sm:inline'>
                  {MODE_LABELS[(activeChat?.mode ?? 'auto') as PermissionMode].hint}
                </span>

                <div className='ml-auto flex items-center gap-2'>
                  {streaming ? (
                    <Button size='sm' variant='secondary' onClick={stop} className='gap-1'>
                      <Square className='h-3.5 w-3.5' /> Stop
                    </Button>
                  ) : (
                    <Button
                      size='sm'
                      onClick={() => void send()}
                      disabled={!draft.trim()}
                      className='gap-1'
                    >
                      <ArrowUp className='h-4 w-4' /> Send
                    </Button>
                  )}
                </div>
              </div>
            </Card>
          </div>
        </section>
      </div>
    </div>
  );
}

// ── pieces ──────────────────────────────────────────────────────────────────

function MessageBubble({ bubble }: { bubble: Bubble }): JSX.Element {
  if (bubble.role === 'user') {
    return (
      <div className='flex justify-end'>
        <div className='max-w-[85%] whitespace-pre-wrap rounded-2xl bg-accent px-4 py-2 text-sm'>
          {bubble.content}
        </div>
      </div>
    );
  }
  return (
    <div className='flex flex-col gap-2'>
      {(bubble.tools ?? []).map((tool, i) => (
        <ToolRow key={i} tool={tool} />
      ))}
      {bubble.content && (
        <div className='whitespace-pre-wrap text-sm leading-relaxed'>{bubble.content}</div>
      )}
      {bubble.pending && !bubble.content && (bubble.tools ?? []).length === 0 && (
        <div className='flex items-center gap-2 text-sm text-muted-foreground'>
          <Loader2 className='h-3.5 w-3.5 animate-spin' /> Thinking...
        </div>
      )}
    </div>
  );
}

function ToolRow({ tool }: { tool: ToolEntry }): JSX.Element {
  const [open, setOpen] = useState(false);
  const failed = typeof tool.result === 'string' && tool.result.startsWith('ERROR');
  const target =
    (tool.args.path as string) ?? (tool.args.command as string) ??
    (tool.args.query as string) ?? (tool.args.url as string) ?? '';

  return (
    <div className='rounded-md border border-border/60 bg-card/50 text-xs'>
      <button
        type='button'
        onClick={() => setOpen((v) => !v)}
        className='flex w-full items-center gap-2 px-2.5 py-1.5 text-left'
      >
        <Wrench className='h-3.5 w-3.5 shrink-0 text-muted-foreground' />
        <span className='font-medium'>{tool.name}</span>
        {target && <span className='truncate text-muted-foreground'>{target}</span>}
        <span className='ml-auto shrink-0'>
          {tool.result === undefined ? (
            <Loader2 className='h-3.5 w-3.5 animate-spin text-muted-foreground' />
          ) : failed ? (
            <AlertTriangle className='h-3.5 w-3.5 text-destructive' />
          ) : (
            <Check className='h-3.5 w-3.5 text-emerald-500' />
          )}
        </span>
      </button>
      {open && tool.result !== undefined && (
        <pre className='max-h-56 overflow-auto border-t border-border/60 px-2.5 py-2 font-mono text-[11px] leading-snug text-muted-foreground'>
          {tool.result}
        </pre>
      )}
    </div>
  );
}

function messagesToBubbles(msgs: LocalChatMessage[]): Bubble[] {
  const out: Bubble[] = [];
  for (const m of msgs) {
    if (m.role === 'user') {
      out.push({ role: 'user', content: m.content });
    } else if (m.role === 'assistant') {
      const tools = (m.tool_calls ?? []).map((t) => ({
        name: t.name,
        args: (t.arguments ?? {}) as Record<string, unknown>,
        result: t.result,
      }));
      // Skip the empty shell rows written between tool rounds.
      if (!m.content && tools.length === 0) continue;
      out.push({ role: 'assistant', content: m.content, tools });
    }
  }
  return out;
}

export default LocalAiPage;
