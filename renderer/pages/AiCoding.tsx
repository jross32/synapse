import { Blocks, Bot, Cpu, Inbox, MessagesSquare, Sparkles, Users } from 'lucide-react';

import type { AiCodingSection } from '@shared/nav';
import { cn } from '@shared/utils';
import { handleTablistKeydown } from '@shared/tablist';
import { PageHeader } from '../components/PageHeader';
import { BlueprintsPage } from './Blueprints';
import { LocalAiPage } from './LocalAi';
import { AssistantPage } from './Assistant';
import { ChatgptCompanionPage } from './ChatgptCompanion';
import { CoderWorkspacePage } from './CoderWorkspace';
import { ReviewPage } from './Review';
import { SessionsPage } from './Sessions';

export interface AiCodingPageProps {
  section?: AiCodingSection;
  onSectionChange?: (section: AiCodingSection) => void;
  pendingSessionId?: string | null;
  onConsumedPendingSession?: () => void;
}

export function AiCodingPage({
  section = 'sessions',
  onSectionChange,
  pendingSessionId,
  onConsumedPendingSession,
}: AiCodingPageProps): JSX.Element {
  return (
    <div className='flex h-full min-h-0 flex-col gap-3 overflow-hidden'>
      <div className='shrink-0'>
        <PageHeader
          title='AI Coding'
          subtitle='One workspace for project threads, AI runtimes, squads, tools, and review.'
          helpText='Start in Workspace for a chat-first coding loop. Synapse keeps the selected project, runtime, files, reviews, and linked terminal work together while Squads, Assistant, Review, and ChatGPT remain one click away.'
        />
      </div>

      <div
        role='tablist'
        aria-label='AI Coding sections'
        onKeyDown={handleTablistKeydown}
        className='scrollbar-thin flex shrink-0 gap-1 overflow-x-auto rounded-lg border border-border bg-secondary/30 p-1'
      >
        <TopTab
          active={section === 'sessions'}
          onClick={() => onSectionChange?.('sessions')}
          icon={Sparkles}
          label='Workspace'
        />
        <TopTab
          active={section === 'squads'}
          onClick={() => onSectionChange?.('squads')}
          icon={Users}
          label='Squads'
        />
        <TopTab
          active={section === 'local'}
          onClick={() => onSectionChange?.('local')}
          icon={Cpu}
          label='Local AI'
        />
        <TopTab
          active={section === 'blueprints'}
          onClick={() => onSectionChange?.('blueprints')}
          icon={Blocks}
          label='Blueprints'
        />
        <TopTab
          active={section === 'assistant'}
          onClick={() => onSectionChange?.('assistant')}
          icon={Bot}
          label='Assistant'
        />
        <TopTab
          active={section === 'review'}
          onClick={() => onSectionChange?.('review')}
          icon={Inbox}
          label='Review'
        />
        <TopTab
          active={section === 'chatgpt'}
          onClick={() => onSectionChange?.('chatgpt')}
          icon={MessagesSquare}
          label='ChatGPT'
        />
      </div>

      <div
        className={cn(
          'min-h-0 flex-1',
          section === 'sessions' ? 'overflow-hidden' : 'scrollbar-thin overflow-y-auto'
        )}
      >
        {section === 'sessions' && (
          <CoderWorkspacePage
            headerless
            initialSessionId={pendingSessionId}
            onConsumedInitial={onConsumedPendingSession}
          />
        )}
        {section === 'squads' && <SessionsPage headerless defaultMode='squads' />}
        {section === 'local' && <LocalAiPage headerless />}
        {section === 'blueprints' && <BlueprintsPage headerless />}
        {section === 'assistant' && <AssistantPage headerless />}
        {section === 'review' && <ReviewPage headerless />}
        {section === 'chatgpt' && <ChatgptCompanionPage headerless />}
      </div>
    </div>
  );
}

function TopTab({
  active,
  onClick,
  icon: Icon,
  label,
}: {
  active: boolean;
  onClick: () => void;
  icon: typeof Sparkles;
  label: string;
}): JSX.Element {
  return (
    <button
      type='button'
      role='tab'
      aria-selected={active}
      tabIndex={active ? 0 : -1}
      onClick={onClick}
      className={cn(
        'flex shrink-0 items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors',
        active
          ? 'bg-card text-foreground shadow-sm'
          : 'text-muted-foreground hover:text-foreground'
      )}
    >
      <Icon className='h-4 w-4' />
      {label}
    </button>
  );
}
