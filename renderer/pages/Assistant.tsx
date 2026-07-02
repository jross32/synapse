// Assistant page (ADR-0014) -- a private, opt-in local LLM (Ollama) chat.
// Off by default: until the user turns it on, this shows an opt-in screen.
// Works on desktop + the mobile shell (single responsive column).

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Bot,
  Loader2,
  MessageSquarePlus,
  Mic,
  MicOff,
  Power,
  PowerOff,
  Send,
  Sparkles,
  Trash2,
} from 'lucide-react';

import {
  createAssistantChat,
  deleteAssistantChat,
  getAssistantChat,
  getAssistantStatus,
  listAssistantChats,
  patchAssistantSettings,
  sendAssistantMessage,
  startAssistantEngine,
  stopAssistantEngine,
  type AssistantChat,
  type AssistantChatDetail,
  type AssistantStatus,
} from '@shared/assistant-client';
import { useSpeechDictation } from '@shared/use-speech';
import { cn } from '@shared/utils';
import { Button } from '../components/ui/button';
import { Card } from '../components/ui/card';
import { Input } from '../components/ui/input';
import { PageHeader } from '../components/PageHeader';
import { ModelBrowser } from '../components/ModelBrowser';

const SELECT_CLASS =
  'h-9 rounded-md border border-input bg-transparent px-2 text-sm text-foreground';

export interface AssistantPageProps {
  headerless?: boolean;
}

export function AssistantPage({ headerless = false }: AssistantPageProps): JSX.Element {
  const [status, setStatus] = useState<AssistantStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [chats, setChats] = useState<AssistantChat[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [detail, setDetail] = useState<AssistantChatDetail | null>(null);
  const [model, setModel] = useState('');
  const [draft, setDraft] = useState('');
  const [view, setView] = useState<'chat' | 'models'>('chat');
  const dictation = useSpeechDictation(
    useCallback((t: string) => setDraft((d) => (d ? `${d} ${t}` : t)), [])
  );
  const scrollRef = useRef<HTMLDivElement>(null);

  async function refreshStatus(): Promise<void> {
    try {
      const s = await getAssistantStatus();
      setStatus(s);
      setModel((prev) => prev || s.default_model || s.models[0]?.name || '');
      setError(null);
    } catch (e) {
      setError((e as Error).message || 'Could not load assistant status.');
    } finally {
      setLoading(false);
    }
  }

  async function refreshChats(): Promise<void> {
    try {
      const { chats: list } = await listAssistantChats();
      setChats(list);
      setActiveId((prev) => prev ?? list[0]?.id ?? null);
    } catch {
      /* surfaced elsewhere */
    }
  }

  useEffect(() => {
    setLoading(true);
    void refreshStatus();
    void refreshChats();
  }, []);

  useEffect(() => {
    if (!activeId) {
      setDetail(null);
      return;
    }
    let cancelled = false;
    void getAssistantChat(activeId)
      .then((d) => !cancelled && setDetail(d))
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [activeId]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [detail]);

  async function run(key: string, fn: () => Promise<unknown>): Promise<void> {
    setBusy(key);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError((e as Error).message || 'Action failed.');
    } finally {
      setBusy(null);
    }
  }

  async function newChat(): Promise<void> {
    await run('new', async () => {
      const chat = await createAssistantChat({ model: model || null });
      await refreshChats();
      setActiveId(chat.id);
    });
  }

  async function removeChat(id: string): Promise<void> {
    await run(`del:${id}`, async () => {
      await deleteAssistantChat(id);
      if (activeId === id) setActiveId(null);
      await refreshChats();
    });
  }

  async function pickModel(next: string): Promise<void> {
    setModel(next);
    void patchAssistantSettings({ default_model: next }).catch(() => undefined);
  }

  async function send(): Promise<void> {
    const content = draft.trim();
    if (!content) return;
    let chatId = activeId;
    await run('send', async () => {
      if (!chatId) {
        const chat = await createAssistantChat({ model: model || null });
        chatId = chat.id;
        setActiveId(chat.id);
        await refreshChats();
      }
      setDraft('');
      // Show the user's message immediately (local models can take many
      // seconds to reply); the spinner below shows it's thinking.
      const optimistic = {
        id: `pending-${Date.now()}`,
        chat_id: chatId!,
        role: 'user' as const,
        content,
        created_at: new Date().toISOString(),
      };
      setDetail((prev) => {
        const base =
          prev && prev.chat.id === chatId
            ? prev
            : { chat: { id: chatId!, title: 'New chat', model: model || null, created_at: '', updated_at: '' }, messages: [] };
        return { ...base, messages: [...base.messages, optimistic] };
      });
      await sendAssistantMessage(chatId!, { content, include_context: true, model: model || null });
      setDetail(await getAssistantChat(chatId!));
      await refreshChats();
    });
  }

  const header = headerless ? null : (
    <PageHeader
      title='Assistant'
      subtitle='A private, local LLM (Ollama) that runs on your machine. Ask about your projects, squads, and Synapse itself.'
    />
  );

  if (loading) {
    return (
      <div className='flex h-full flex-col gap-4'>
        {header}
        <Card className='flex items-center gap-2 p-6 text-sm text-muted-foreground'>
          <Loader2 className='h-4 w-4 animate-spin' /> Checking the local assistant...
        </Card>
      </div>
    );
  }

  // ── Not installed ──────────────────────────────────────────────────────────
  if (status && !status.installed) {
    return (
      <div className='flex h-full flex-col gap-4'>
        {header}
        <Card className='mx-auto flex max-w-xl flex-col items-center gap-3 border-dashed p-8 text-center'>
          <Bot className='h-8 w-8 text-primary' />
          <h2 className='text-lg font-semibold'>Ollama isn&apos;t installed yet</h2>
          <p className='text-sm text-muted-foreground'>
            The local assistant runs on <span className='font-medium text-foreground'>Ollama</span>, a
            free local LLM engine. Install it, then come back and turn the assistant on.
          </p>
          <code className='rounded-md bg-card px-3 py-2 font-mono text-xs'>winget install Ollama.Ollama</code>
          <Button variant='outline' size='sm' onClick={() => void refreshStatus()}>
            <Loader2 className={cn('h-4 w-4', busy && 'animate-spin')} /> Re-check
          </Button>
        </Card>
      </div>
    );
  }

  // ── Installed but OFF (opt-in) ─────────────────────────────────────────────
  if (status && !status.enabled) {
    return (
      <div className='flex h-full flex-col gap-4'>
        {header}
        <Card className='mx-auto flex max-w-xl flex-col items-center gap-3 p-8 text-center'>
          <Sparkles className='h-8 w-8 text-primary' />
          <h2 className='text-lg font-semibold'>Turn on the local assistant</h2>
          <p className='text-sm text-muted-foreground'>
            Off by default. When on, you get a private chat powered by your own models — nothing leaves
            your machine. You can turn it off any time.
          </p>
          <Button
            disabled={busy === 'enable'}
            onClick={() => void run('enable', async () => {
              await patchAssistantSettings({ enabled: true });
              await refreshStatus();
            })}
          >
            <Power className='h-4 w-4' /> Turn on assistant
          </Button>
          {error && <p role='alert' className='text-xs text-destructive'>{error}</p>}
        </Card>
      </div>
    );
  }

  // ── Enabled ────────────────────────────────────────────────────────────────
  const noModels = (status?.models.length ?? 0) === 0;

  return (
    <div className='flex h-full flex-col gap-4'>
      {header}

      <Card className='flex flex-wrap items-center gap-2 p-3'>
        <div className='inline-flex rounded-md border border-border p-0.5'>
          {(['chat', 'models'] as const).map((v) => (
            <button
              key={v}
              onClick={() => setView(v)}
              className={cn(
                'rounded px-3 py-1 text-xs font-medium capitalize transition-colors',
                view === v ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground'
              )}
            >
              {v}
            </button>
          ))}
        </div>
        <span
          className={cn(
            'inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium',
            status?.server_up ? 'bg-emerald-500/15 text-emerald-300' : 'bg-amber-500/15 text-amber-100'
          )}
        >
          <span className={cn('h-2 w-2 rounded-full', status?.server_up ? 'bg-emerald-400' : 'bg-amber-400')} />
          Engine {status?.server_up ? 'running' : 'stopped'}
        </span>
        {!status?.server_up ? (
          <Button size='sm' variant='outline' disabled={busy === 'start'}
            onClick={() => void run('start', async () => { await startAssistantEngine(); await refreshStatus(); })}>
            {busy === 'start' ? <Loader2 className='h-4 w-4 animate-spin' /> : <Power className='h-4 w-4' />} Start engine
          </Button>
        ) : (
          <Button size='sm' variant='ghost' disabled={busy === 'stop'}
            onClick={() => void run('stop', async () => { await stopAssistantEngine(); await refreshStatus(); })}>
            <PowerOff className='h-4 w-4' /> Stop
          </Button>
        )}
        {view === 'chat' && (
          <>
            <div className='flex items-center gap-2'>
              <label htmlFor='asst-model' className='text-xs text-muted-foreground'>Model</label>
              <select id='asst-model' className={SELECT_CLASS} value={model} onChange={(e) => void pickModel(e.target.value)}>
                {noModels && <option value=''>none installed</option>}
                {status?.models.map((m) => <option key={m.name} value={m.name}>{m.name}</option>)}
              </select>
            </div>
            <div className='ml-auto flex items-center gap-2'>
              <select className={SELECT_CLASS} value={activeId ?? ''} onChange={(e) => setActiveId(e.target.value || null)} aria-label='Active chat'>
                {chats.length === 0 && <option value=''>no chats yet</option>}
                {chats.map((c) => <option key={c.id} value={c.id}>{c.title}</option>)}
              </select>
              {activeId && (
                <Button size='sm' variant='ghost' aria-label='Delete chat' title='Delete chat'
                  disabled={busy === `del:${activeId}`} onClick={() => void removeChat(activeId)}>
                  <Trash2 className='h-4 w-4' />
                </Button>
              )}
              <Button size='sm' onClick={() => void newChat()} disabled={busy === 'new'}>
                <MessageSquarePlus className='h-4 w-4' /> New chat
              </Button>
            </div>
          </>
        )}
      </Card>

      {view === 'models' && <ModelBrowser onInstalledChange={refreshStatus} />}

      {view === 'chat' && noModels && (
        <Card className='flex flex-col items-start gap-2 border-dashed p-4 text-sm text-muted-foreground'>
          <p>No models installed yet. Grab one to get started:</p>
          <Button size='sm' onClick={() => setView('models')}>Browse models</Button>
        </Card>
      )}

      {view === 'chat' && (
      <Card className='flex min-h-0 flex-1 flex-col p-0'>
        <div ref={scrollRef} className='flex-1 space-y-3 overflow-y-auto p-4'>
          {!detail || detail.messages.length === 0 ? (
            <div className='flex h-full flex-col items-center justify-center gap-2 text-center text-sm text-muted-foreground'>
              <Bot className='h-7 w-7 text-primary' />
              <p>Say hi, or ask &ldquo;what projects do I have?&rdquo; / &ldquo;what&apos;s the boss doing?&rdquo;</p>
            </div>
          ) : (
            detail.messages.map((m) => (
              <div key={m.id} className={cn('flex', m.role === 'user' ? 'justify-end' : 'justify-start')}>
                <div className={cn(
                  'max-w-[85%] whitespace-pre-wrap rounded-2xl px-3 py-2 text-sm',
                  m.role === 'user' ? 'bg-primary text-primary-foreground' : 'border border-border bg-secondary/40'
                )}>
                  {m.content}
                </div>
              </div>
            ))
          )}
          {busy === 'send' && (
            <div className='flex justify-start'>
              <div className='rounded-2xl border border-border bg-secondary/40 px-3 py-2 text-sm text-muted-foreground'>
                <Loader2 className='h-4 w-4 animate-spin' />
              </div>
            </div>
          )}
        </div>
        {error && <p role='alert' className='px-4 pb-2 text-xs text-destructive'>{error}</p>}
        <form className='flex items-end gap-2 border-t border-border p-3'
          onSubmit={(e) => { e.preventDefault(); void send(); }}>
          <Input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder={
              dictation.listening ? (dictation.interim || 'Listening…') : noModels ? 'Install a model first...' : 'Message the assistant...'
            }
            aria-label='Message the assistant'
            disabled={noModels || busy === 'send'}
          />
          {dictation.supported && (
            <Button
              type='button'
              variant={dictation.listening ? 'default' : 'outline'}
              disabled={noModels}
              onClick={() => dictation.toggle()}
              aria-label={dictation.listening ? 'Stop dictation' : 'Dictate a message'}
            >
              {dictation.listening ? <MicOff className='h-4 w-4' /> : <Mic className='h-4 w-4' />}
            </Button>
          )}
          <Button type='submit' disabled={noModels || busy === 'send' || !draft.trim()}>
            {busy === 'send' ? <Loader2 className='h-4 w-4 animate-spin' /> : <Send className='h-4 w-4' />}
          </Button>
        </form>
      </Card>
      )}
    </div>
  );
}
