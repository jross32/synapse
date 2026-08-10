/**
 * "How to use local AI" — the measured playbook, rendered for a human.
 *
 * Everything shown here comes from the API rather than being written into the component,
 * because the same constant is served to any AI reading /ai/context. Hard-coding the copy
 * here would let the human instructions and the machine instructions drift apart, and the
 * whole point is that both audiences get the same measured answer.
 */
import { useState } from 'react';
import { Check, ChevronDown, Copy, Cpu, Info, TriangleAlert, Wrench, Zap } from 'lucide-react';
import { cn } from '../lib/utils';

export interface Playbook {
  summary?: string;
  the_one_rule?: string;
  for_writing_code?: { do?: string; why?: string; then?: string; raise_max_repairs_freely?: string };
  for_everything_else?: { do?: string; good_for?: string; modes?: string };
  what_does_not_work?: string[];
  when_to_use_your_own_tokens_instead?: string;
  endpoints?: Record<string, string>;
  measured_in?: string;
}

function CopyLine({ text }: { text: string }): JSX.Element {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type='button'
      onClick={() => {
        void navigator.clipboard.writeText(text).then(() => {
          setCopied(true);
          window.setTimeout(() => setCopied(false), 1400);
        });
      }}
      title='Copy'
      className='group flex w-full min-w-0 items-center gap-2 rounded-md border border-border bg-muted/40 px-2.5 py-1.5 text-left font-mono text-xs hover:bg-muted'
    >
      <span className='min-w-0 flex-1 truncate'>{text}</span>
      {copied ? (
        <Check className='h-3.5 w-3.5 shrink-0 text-[var(--status-ok,theme(colors.emerald.500))]' />
      ) : (
        <Copy className='h-3.5 w-3.5 shrink-0 opacity-0 transition-opacity group-hover:opacity-70' />
      )}
    </button>
  );
}

export function LocalAiHowTo({ playbook }: { playbook?: Playbook }): JSX.Element | null {
  const [open, setOpen] = useState(false);
  if (!playbook?.the_one_rule) return null;

  const code = playbook.for_writing_code ?? {};
  const other = playbook.for_everything_else ?? {};

  return (
    <section className='min-w-0 rounded-lg border border-border bg-card'>
      <button
        type='button'
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className='flex w-full items-center gap-2 px-3 py-2.5 text-left'
      >
        <Info className='h-4 w-4 shrink-0 text-muted-foreground' />
        <span className='flex-1 text-sm font-medium'>How to use local AI</span>
        <span className='hidden text-xs text-muted-foreground sm:inline'>
          measured on this machine
        </span>
        <ChevronDown
          className={cn('h-4 w-4 shrink-0 transition-transform', open && 'rotate-180')}
        />
      </button>

      {open && (
        <div className='min-w-0 space-y-4 border-t border-border px-3 py-3 text-sm'>
          {playbook.summary && <p className='text-muted-foreground'>{playbook.summary}</p>}

          {/* The single most expensive mistake, stated first so it is the thing you read. */}
          <div className='rounded-md border border-[var(--status-warn-border,theme(colors.amber.500/30))] bg-[var(--status-warn-bg,theme(colors.amber.500/10))] p-3'>
            <p className='mb-1 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide'>
              <TriangleAlert className='h-3.5 w-3.5' /> The one rule
            </p>
            <p className='break-words text-sm leading-relaxed'>{playbook.the_one_rule}</p>
          </div>

          <div className='grid min-w-0 gap-3 md:grid-cols-2'>
            <div className='min-w-0 space-y-2 rounded-md border border-border p-3'>
              <p className='flex items-center gap-1.5 text-sm font-medium'>
                <Zap className='h-4 w-4' /> Writing code
              </p>
              {code.do && <CopyLine text={code.do} />}
              {code.why && <p className='text-xs text-muted-foreground'>{code.why}</p>}
              {code.then && (
                <p className='text-xs text-muted-foreground'>
                  <span className='font-medium text-foreground'>If it gets stuck: </span>
                  {code.then}
                </p>
              )}
            </div>

            <div className='min-w-0 space-y-2 rounded-md border border-border p-3'>
              <p className='flex items-center gap-1.5 text-sm font-medium'>
                <Wrench className='h-4 w-4' /> Everything else
              </p>
              {other.do && <CopyLine text={other.do} />}
              {other.good_for && <p className='text-xs text-muted-foreground'>{other.good_for}</p>}
              {other.modes && (
                <p className='text-xs text-muted-foreground'>
                  <span className='font-medium text-foreground'>Modes: </span>
                  {other.modes}
                </p>
              )}
            </div>
          </div>

          {!!playbook.what_does_not_work?.length && (
            <div>
              <p className='mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground'>
                Things that were tried and made it worse
              </p>
              <ul className='space-y-1.5'>
                {playbook.what_does_not_work.map((item) => (
                  <li key={item} className='flex gap-2 text-xs text-muted-foreground'>
                    <span aria-hidden className='select-none pt-px'>
                      &times;
                    </span>
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {playbook.when_to_use_your_own_tokens_instead && (
            <div className='rounded-md border border-border bg-muted/30 p-3'>
              <p className='mb-1 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide'>
                <Cpu className='h-3.5 w-3.5' /> When to use a paid model instead
              </p>
              <p className='text-xs text-muted-foreground'>
                {playbook.when_to_use_your_own_tokens_instead}
              </p>
            </div>
          )}

          {playbook.measured_in && (
            <p className='text-[11px] text-muted-foreground'>
              Every claim here is measured on this machine — see{' '}
              <code className='rounded bg-muted px-1 py-0.5'>{playbook.measured_in}</code>. Re-run
              the benchmark after changing models and these numbers update.
            </p>
          )}
        </div>
      )}
    </section>
  );
}

export default LocalAiHowTo;
