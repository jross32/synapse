import { useEffect, useState } from 'react';
import { Bot, Inbox, Sparkles } from 'lucide-react';

import type { AiCodingSection } from '@shared/nav';
import { cn } from '@shared/utils';
import { PageHeader } from '../components/PageHeader';
import { AssistantPage } from './Assistant';
import { CoderWorkspacePage } from './CoderWorkspace';
import { ReviewPage } from './Review';

export interface AiCodingPageProps {
  initialSection?: AiCodingSection;
  pendingSessionId?: string | null;
  onConsumedPendingSession?: () => void;
}

export function AiCodingPage({
  initialSection = 'sessions',
  pendingSessionId,
  onConsumedPendingSession,
}: AiCodingPageProps): JSX.Element {
  const [section, setSection] = useState<AiCodingSection>(initialSection);

  useEffect(() => {
    setSection(initialSection);
  }, [initialSection]);

  return (
    <div className='flex flex-col gap-6'>
      <PageHeader
        title='AI Coding'
        subtitle='Your coder workspace: project threads, live runtimes, your private assistant, and the review inbox in one place.'
      />

      <div
        role='tablist'
        aria-label='AI Coding sections'
        className='inline-flex w-fit gap-1 rounded-lg border border-border bg-secondary/30 p-1'
      >
        <TopTab
          active={section === 'sessions'}
          onClick={() => setSection('sessions')}
          icon={Sparkles}
          label='Workspace'
        />
        <TopTab
          active={section === 'assistant'}
          onClick={() => setSection('assistant')}
          icon={Bot}
          label='Assistant'
        />
        <TopTab
          active={section === 'review'}
          onClick={() => setSection('review')}
          icon={Inbox}
          label='Review'
        />
      </div>

      {section === 'sessions' && (
        <CoderWorkspacePage
          headerless
          initialSessionId={pendingSessionId}
          onConsumedInitial={onConsumedPendingSession}
        />
      )}
      {section === 'assistant' && <AssistantPage headerless />}
      {section === 'review' && <ReviewPage headerless />}
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
      onClick={onClick}
      className={cn(
        'flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors',
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
