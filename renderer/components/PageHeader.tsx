// Shared page header -- title + subtitle + optional right-aligned action.

export interface PageHeaderProps {
  title: string;
  subtitle?: string;
  action?: React.ReactNode;
}

export function PageHeader({ title, subtitle, action }: PageHeaderProps): JSX.Element {
  return (
    <header className='flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between'>
      <div className='min-w-0'>
        <h1 className='text-2xl font-semibold tracking-tight'>{title}</h1>
        {subtitle && <p className='mt-1 text-sm text-muted-foreground'>{subtitle}</p>}
      </div>
      {action && <div className='w-full sm:w-auto sm:shrink-0'>{action}</div>}
    </header>
  );
}
