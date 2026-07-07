// Shared page header -- title + subtitle + optional right-aligned action.
// helpText renders a ? tooltip next to the subtitle for any non-obvious page.

import { HelpIcon } from './HelpIcon';

export interface PageHeaderProps {
  title: string;
  subtitle?: string;
  /** Short explanation shown as a ? tooltip next to the subtitle. */
  helpText?: string;
  action?: React.ReactNode;
}

export function PageHeader({ title, subtitle, helpText, action }: PageHeaderProps): JSX.Element {
  return (
    <header className='flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between'>
      <div className='min-w-0'>
        <h1 className='text-2xl font-semibold tracking-tight'>{title}</h1>
        {subtitle && (
          <p className='mt-1 flex items-center gap-1.5 text-sm text-muted-foreground'>
            {subtitle}
            {helpText && <HelpIcon content={helpText} side='right' />}
          </p>
        )}
      </div>
      {action && <div className='w-full sm:w-auto sm:shrink-0'>{action}</div>}
    </header>
  );
}
