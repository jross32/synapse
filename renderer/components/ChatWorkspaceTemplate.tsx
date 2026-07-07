import type { ReactNode } from 'react';
import {
  Blocks,
  MessageSquareText,
  PanelLeft,
  PencilRuler,
  ShieldCheck,
  SquarePen,
} from 'lucide-react';

import { cn } from '@shared/utils';
import { Badge } from './ui/badge';

export interface ChatWorkspaceShellProps {
  leftPane: ReactNode;
  centerPane: ReactNode;
  rightPane: ReactNode;
  className?: string;
}

const COMPONENT_LIST = [
  'Project target rail with recent context and saved captures',
  'Live source pane for the active chat surface or embedded browser',
  'Transcript pane for visible chats, messages, and selected context',
  'Sticky composer rail for draft, revise, and save actions',
  'Inspector panel for workflow notes, provenance, and quality reminders',
];

const TOKEN_GUIDE = [
  {
    label: 'Shell gap',
    token: '--synapse-space-4',
    usage: 'Keep the three panes visually separated without wasting width.',
  },
  {
    label: 'Pane radius',
    token: '--synapse-radius-lg',
    usage: 'Use the same rounded frame across rails, transcript cards, and composer panels.',
  },
  {
    label: 'Header rhythm',
    token: '--synapse-space-3 / --synapse-space-4',
    usage: 'Use compact headers so more of the working surface stays visible.',
  },
  {
    label: 'Body type',
    token: '--synapse-text-sm / --synapse-text-base',
    usage: 'Keep dense metadata small while prompts and replies stay comfortably readable.',
  },
  {
    label: 'Surface stack',
    token: '--background / --card / --secondary',
    usage: 'Let the shell feel layered without copying ChatGPT colors.',
  },
];

const PATTERNS = [
  {
    title: 'Sidebar pattern',
    detail:
      'A compact left rail that chooses project scope first, then keeps saved context and trust notes inside the same pane.',
  },
  {
    title: 'Transcript pane pattern',
    detail:
      'The middle workspace owns the conversation view and related capture index, with each pane scrolling on its own instead of the whole page.',
  },
  {
    title: 'Sticky composer pattern',
    detail:
      'Actions stay anchored near the draft surface so the user can fill, send, revise, and save without hunting around the page.',
  },
];

const PROVENANCE_NOTES = [
  'Inspired by ChatGPT layout discipline: quiet rails, strong center focus, and low-friction composer placement.',
  'Not a branded copy: Synapse keeps its own tokens, labels, actions, data model, and browser-managed account flow.',
  'Reusable for future apps: swap the left rail source, transcript content, or inspector detail without rebuilding the shell.',
];

export function ChatWorkspaceShell({
  leftPane,
  centerPane,
  rightPane,
  className,
}: ChatWorkspaceShellProps): JSX.Element {
  return (
    <div
      className={cn(
        'grid min-h-0 flex-1 gap-4 xl:grid-cols-[280px_minmax(0,1fr)_380px]',
        className
      )}
      data-surface-id='chat-workspace-template.shell'
    >
      <section className='min-h-0' data-surface-id='chat-workspace-template.left-pane'>
        {leftPane}
      </section>
      <section className='min-h-0' data-surface-id='chat-workspace-template.center-pane'>
        {centerPane}
      </section>
      <section className='min-h-0' data-surface-id='chat-workspace-template.right-pane'>
        {rightPane}
      </section>
    </div>
  );
}

export function ChatWorkspaceTemplateGuide(): JSX.Element {
  return (
    <div className='flex flex-col gap-4 text-sm'>
      <div className='rounded-xl border border-border/70 bg-secondary/20 px-4 py-4'>
        <div className='flex flex-wrap items-center gap-2'>
          <Badge variant='outline'>Reference-inspired</Badge>
          <Badge variant='outline'>Unbranded</Badge>
          <Badge variant='outline'>Reusable shell</Badge>
        </div>
        <p className='mt-3 text-muted-foreground'>
          This template borrows the layout discipline that makes ChatGPT easy to
          work inside, then translates it into Synapse-native panes, actions, and
          tokens.
        </p>
      </div>

      <GuideSection
        icon={Blocks}
        title='Component list'
        items={COMPONENT_LIST}
      />

      <div className='rounded-xl border border-border/70 bg-card px-4 py-4'>
        <div className='flex items-center gap-2'>
          <PencilRuler className='h-4 w-4 text-primary' />
          <h3 className='font-semibold'>Spacing + token guide</h3>
        </div>
        <div className='mt-3 grid gap-3'>
          {TOKEN_GUIDE.map((entry) => (
            <div
              key={entry.label}
              className='grid gap-1 rounded-lg border border-border/60 bg-background/70 px-3 py-3'
            >
              <div className='flex flex-wrap items-center justify-between gap-2'>
                <span className='font-medium text-foreground'>{entry.label}</span>
                <code className='rounded bg-secondary/60 px-2 py-1 text-xs text-primary'>
                  {entry.token}
                </code>
              </div>
              <p className='text-muted-foreground'>{entry.usage}</p>
            </div>
          ))}
        </div>
      </div>

      <GuideSection
        icon={MessageSquareText}
        title='Interaction patterns'
        items={PATTERNS.map((entry) => `${entry.title}: ${entry.detail}`)}
      />

      <GuideSection
        icon={ShieldCheck}
        title='Provenance notes'
        items={PROVENANCE_NOTES}
      />
    </div>
  );
}

function GuideSection({
  icon: Icon,
  title,
  items,
}: {
  icon: typeof PanelLeft;
  title: string;
  items: string[];
}): JSX.Element {
  return (
    <div className='rounded-xl border border-border/70 bg-card px-4 py-4'>
      <div className='flex items-center gap-2'>
        <Icon className='h-4 w-4 text-primary' />
        <h3 className='font-semibold'>{title}</h3>
      </div>
      <ul className='mt-3 space-y-2 text-muted-foreground'>
        {items.map((item) => (
          <li key={item} className='flex gap-2'>
            <SquarePen className='mt-0.5 h-3.5 w-3.5 shrink-0 text-primary/80' />
            <span>{item}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
