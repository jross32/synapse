// Shared page header -- title + subtitle + optional right-aligned action.

export interface PageHeaderProps {
  title: string;
  subtitle?: string;
  action?: React.ReactNode;
}

export function PageHeader({ title, subtitle, action }: PageHeaderProps): JSX.Element {
  return (
    <header className='flex items-start justify-between gap-4'>
      <div>
        <h1 className='text-2xl font-semibold tracking-tight'>{title}</h1>
        {subtitle && <p className='mt-1 text-sm text-muted-foreground'>{subtitle}</p>}
      </div>
      {action && <div className='shrink-0'>{action}</div>}
    </header>
  );
}
