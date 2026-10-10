import { useEffect, useRef, useState } from 'react';
import { Send, Sparkles } from 'lucide-react';

import {
  getStaffChat,
  sendStaffChat,
  type StaffAvatarAsset,
  type StaffChatMessage,
} from '@shared/staff-client';

export function StaffChatPanel({
  staffId,
  name,
  title,
  avatar,
}: {
  staffId: string;
  name: string;
  title: string;
  avatar?: StaffAvatarAsset | null;
}): JSX.Element {
  const [messages, setMessages] = useState<StaffChatMessage[]>([]);
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const scrollRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    let active = true;
    setError('');
    void getStaffChat(staffId)
      .then((result) => {
        if (active) setMessages(result.messages);
      })
      .catch((err: unknown) => {
        if (active) setError(err instanceof Error ? err.message : 'Could not load this chat.');
      });
    return () => {
      active = false;
    };
  }, [staffId]);

  useEffect(() => {
    const node = scrollRef.current;
    if (node) node.scrollTop = node.scrollHeight;
  }, [messages, busy]);

  async function send(): Promise<void> {
    const message = text.trim();
    if (!message || busy) return;
    setText('');
    setBusy(true);
    setError('');

    const optimistic: StaffChatMessage = {
      id: 'optimistic-' + Date.now(),
      staff_member_id: staffId,
      role: 'user',
      content: message,
      created_at: new Date().toISOString(),
    };
    setMessages((current) => [...current, optimistic]);

    try {
      const result = await sendStaffChat(staffId, message);
      setMessages((current) => [
        ...current.filter((item) => item.id !== optimistic.id),
        result.user_message,
        result.assistant_message,
      ]);
    } catch (err) {
      setMessages((current) => current.filter((item) => item.id !== optimistic.id));
      setText(message);
      setError(err instanceof Error ? err.message : 'Could not send the message.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className='overflow-hidden rounded-[28px] border border-primary/25 bg-card/80 shadow-[0_20px_70px_rgba(0,0,0,.18)]'>
      <div className='flex items-center gap-3 border-b border-border bg-[radial-gradient(circle_at_15%_0%,rgba(59,130,246,.18),transparent_42%),rgba(15,23,42,.35)] px-4 py-3'>
        <div
          className='grid h-11 w-11 shrink-0 place-items-center rounded-2xl border border-white/15 text-lg'
          style={{
            background: avatar?.background ?? 'linear-gradient(145deg,#111827,#334155)',
            color: avatar?.accent ?? '#fff',
          }}
        >
          {avatar?.glyph ?? name.slice(0, 1)}
        </div>
        <div className='min-w-0'>
          <div className='flex items-center gap-2'>
            <p className='font-semibold text-foreground'>{name}</p>
            <span className='rounded-full border border-emerald-400/25 bg-emerald-500/10 px-2 py-0.5 text-[10px] text-emerald-300'>
              chat
            </span>
          </div>
          <p className='text-xs text-muted-foreground'>{title}</p>
        </div>
      </div>

      <div ref={scrollRef} className='h-[420px] space-y-3 overflow-y-auto p-4'>
        {messages.length === 0 && !busy && (
          <div className='grid h-full place-items-center text-center'>
            <div>
              <Sparkles className='mx-auto h-6 w-6 text-primary' />
              <p className='mt-3 text-sm font-medium text-foreground'>Talk to {name}</p>
              <p className='mt-1 max-w-sm text-xs leading-5 text-muted-foreground'>
                Ask anything naturally. This chat uses {name}'s stored role, personality, specialties, goals, and recent conversation history.
              </p>
            </div>
          </div>
        )}

        {messages.map((message) => (
          <div
            key={message.id}
            className={message.role === 'user' ? 'flex justify-end' : 'flex justify-start'}
          >
            <div
              className={
                message.role === 'user'
                  ? 'max-w-[82%] rounded-3xl rounded-br-lg bg-primary px-4 py-3 text-sm leading-6 text-primary-foreground'
                  : 'max-w-[82%] rounded-3xl rounded-bl-lg border border-border bg-background/70 px-4 py-3 text-sm leading-6 text-foreground'
              }
            >
              {message.content}
            </div>
          </div>
        ))}

        {busy && (
          <div className='flex justify-start'>
            <div className='rounded-3xl rounded-bl-lg border border-border bg-background/70 px-4 py-3 text-sm text-muted-foreground'>
              {name} is thinking…
            </div>
          </div>
        )}
      </div>

      {error && (
        <div className='mx-4 mb-3 rounded-2xl border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive'>
          {error}
        </div>
      )}

      <div className='border-t border-border p-3'>
        <div className='flex items-end gap-2 rounded-2xl border border-border bg-background/70 p-2 focus-within:border-primary/50'>
          <textarea
            value={text}
            onChange={(event) => setText(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                void send();
              }
            }}
            rows={2}
            placeholder={'Message ' + name + '…'}
            className='min-h-[44px] flex-1 resize-none bg-transparent px-2 py-2 text-sm text-foreground outline-none placeholder:text-muted-foreground'
          />
          <button
            type='button'
            disabled={!text.trim() || busy}
            onClick={() => void send()}
            className='grid h-10 w-10 place-items-center rounded-xl bg-primary text-primary-foreground transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-40'
            aria-label={'Send message to ' + name}
          >
            <Send className='h-4 w-4' />
          </button>
        </div>
        <p className='mt-2 px-1 text-[10px] text-muted-foreground'>
          Enter sends · Shift+Enter makes a new line
        </p>
      </div>
    </section>
  );
}
