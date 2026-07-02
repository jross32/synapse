import { useEffect, useMemo, useState } from 'react';
import {
  ArrowDown,
  ArrowUp,
  Eye,
  EyeOff,
  Lock,
  RotateCcw,
} from 'lucide-react';

import type { InstalledPageView } from '@shared/installed-pages-client';
import {
  coreNavItem,
  defaultSidebarLayout,
  loadSidebarLayout,
  normalizeSidebarLayout,
  saveSidebarLayout,
  type SidebarLayout,
} from '@shared/nav';
import { cn } from '@shared/utils';
import { Button } from './ui/button';
import { Modal } from './ui/modal';

export interface SidebarSettingsProps {
  open: boolean;
  onClose: () => void;
  installedPages: InstalledPageView[];
  onChange?: () => void;
}

function moveItem<T>(items: T[], index: number, direction: -1 | 1): T[] {
  const target = index + direction;
  if (target < 0 || target >= items.length) return items;
  const next = [...items];
  const [item] = next.splice(index, 1);
  next.splice(target, 0, item);
  return next;
}

export function SidebarSettings({
  open,
  onClose,
  installedPages,
  onChange,
}: SidebarSettingsProps): JSX.Element | null {
  const installedIds = useMemo(() => installedPages.map((page) => page.id), [installedPages]);
  const [layout, setLayout] = useState<SidebarLayout>(() => loadSidebarLayout(installedIds));

  useEffect(() => {
    if (!open) return;
    setLayout(loadSidebarLayout(installedIds));
  }, [open, installedIds]);

  function commit(next: SidebarLayout): void {
    const normalized = normalizeSidebarLayout(next, installedIds);
    setLayout(normalized);
    saveSidebarLayout(normalized);
    onChange?.();
  }

  function resetToDefault(): void {
    commit(normalizeSidebarLayout(defaultSidebarLayout(), installedIds));
  }

  function toggleCore(id: SidebarLayout['hidden_core'][number]): void {
    const hidden = new Set(layout.hidden_core);
    if (hidden.has(id)) hidden.delete(id);
    else hidden.add(id);
    commit({ ...layout, hidden_core: [...hidden] as SidebarLayout['hidden_core'] });
  }

  function toggleInstalled(id: string): void {
    const visible = new Set(layout.visible_installed_pages);
    if (visible.has(id)) visible.delete(id);
    else visible.add(id);
    commit({ ...layout, visible_installed_pages: [...visible] });
  }

  if (!open) return null;

  const installedById = new Map(installedPages.map((page) => [page.id, page]));
  const installedRows = [
    ...layout.installed_page_order,
    ...installedPages.map((page) => page.id),
  ]
    .filter((id, index, all) => all.indexOf(id) === index)
    .map((id) => installedById.get(id))
    .filter((page): page is InstalledPageView => !!page);

  return (
    <Modal
      open
      onClose={onClose}
      labelledBy='sidebar-settings-title'
      className='max-w-2xl'
    >
      <div className='flex items-center justify-between gap-3'>
        <div>
          <h2 id='sidebar-settings-title' className='text-base font-semibold'>
            Navigation &amp; Installed Pages
          </h2>
          <p className='mt-0.5 text-xs text-muted-foreground'>
            Home and Settings stay locked. Reorder inside each section and choose
            which extra pages appear in the desktop sidebar.
          </p>
        </div>
        <Button
          variant='outline'
          size='sm'
          onClick={resetToDefault}
          aria-label='Reset navigation to default'
        >
          <RotateCcw className='h-3.5 w-3.5' aria-hidden='true' />
          Reset
        </Button>
      </div>

      <div className='grid gap-4 lg:grid-cols-2'>
        <SectionCard
          title='Main'
          description='Desktop main hubs'
          footer='Home stays pinned at the top.'
        >
          <LockedRow label={coreNavItem('home').label} description='Always visible' />
          {layout.main_order.map((id, index) => {
            const item = coreNavItem(id);
            return (
            <CoreRow
              key={id}
              label={item.label}
              description={item.description}
              visible={!layout.hidden_core.includes(id)}
              onToggle={() => toggleCore(id)}
              onMoveUp={() =>
                commit({
                  ...layout,
                  main_order: moveItem(layout.main_order, index, -1) as SidebarLayout['main_order'],
                })
              }
              onMoveDown={() =>
                commit({
                  ...layout,
                  main_order: moveItem(layout.main_order, index, 1) as SidebarLayout['main_order'],
                })
              }
              disableUp={index === 0}
              disableDown={index === layout.main_order.length - 1}
            />
            );
          })}
        </SectionCard>

        <SectionCard
          title='AI'
          description='Desktop AI hubs'
          footer='These can be hidden on desktop, but stay reachable elsewhere.'
        >
          {layout.ai_order.map((id, index) => {
            const item = coreNavItem(id);
            return (
            <CoreRow
              key={id}
              label={item.label}
              description={item.description}
              visible={!layout.hidden_core.includes(id)}
              onToggle={() => toggleCore(id)}
              onMoveUp={() =>
                commit({
                  ...layout,
                  ai_order: moveItem(layout.ai_order, index, -1) as SidebarLayout['ai_order'],
                })
              }
              onMoveDown={() =>
                commit({
                  ...layout,
                  ai_order: moveItem(layout.ai_order, index, 1) as SidebarLayout['ai_order'],
                })
              }
              disableUp={index === 0}
              disableDown={index === layout.ai_order.length - 1}
            />
            );
          })}
        </SectionCard>

        <SectionCard
          title='System'
          description='System navigation'
          footer='Settings stays pinned at the bottom.'
        >
          <LockedRow label={coreNavItem('settings').label} description='Always visible' />
        </SectionCard>

        <SectionCard
          title='Installed'
          description='Optional dedicated pages'
          footer={
            installedRows.length > 0
              ? 'Only visible on desktop when Show in sidebar is enabled.'
              : 'Install an eligible dedicated page first.'
          }
        >
          {installedRows.length === 0 ? (
            <p className='rounded-md border border-dashed border-border px-3 py-3 text-sm text-muted-foreground'>
              No installed dedicated pages are available yet.
            </p>
          ) : (
            installedRows.map((page, index) => (
              <InstalledRow
                key={page.id}
                label={page.label}
                description={page.description}
                visible={layout.visible_installed_pages.includes(page.id)}
                detail={page.detail}
                onToggle={() => toggleInstalled(page.id)}
                onMoveUp={() =>
                  commit({
                    ...layout,
                    installed_page_order: moveItem(
                      installedRows.map((item) => item.id),
                      index,
                      -1
                    ),
                  })
                }
                onMoveDown={() =>
                  commit({
                    ...layout,
                    installed_page_order: moveItem(
                      installedRows.map((item) => item.id),
                      index,
                      1
                    ),
                  })
                }
                disableUp={index === 0}
                disableDown={index === installedRows.length - 1}
              />
            ))
          )}
        </SectionCard>
      </div>
    </Modal>
  );
}

function SectionCard({
  title,
  description,
  footer,
  children,
}: {
  title: string;
  description: string;
  footer: string;
  children: React.ReactNode;
}): JSX.Element {
  return (
    <div className='flex flex-col gap-3 rounded-xl border border-border bg-secondary/20 p-4'>
      <div>
        <h3 className='text-sm font-semibold'>{title}</h3>
        <p className='mt-1 text-xs text-muted-foreground'>{description}</p>
      </div>
      <div className='flex flex-col gap-2'>{children}</div>
      <p className='text-[11px] text-muted-foreground'>{footer}</p>
    </div>
  );
}

function LockedRow({
  label,
  description,
}: {
  label: string;
  description: string;
}): JSX.Element {
  return (
    <div className='flex items-center gap-3 rounded-md border border-border bg-card/60 px-3 py-2'>
      <Lock className='h-3.5 w-3.5 shrink-0 text-muted-foreground' aria-hidden='true' />
      <div className='min-w-0 grow'>
        <p className='text-sm font-medium'>{label}</p>
        <p className='text-xs text-muted-foreground'>{description}</p>
      </div>
      <span className='text-xs text-muted-foreground'>locked</span>
    </div>
  );
}

function CoreRow({
  label,
  description,
  visible,
  onToggle,
  onMoveUp,
  onMoveDown,
  disableUp,
  disableDown,
}: {
  label: string;
  description: string;
  visible: boolean;
  onToggle: () => void;
  onMoveUp: () => void;
  onMoveDown: () => void;
  disableUp: boolean;
  disableDown: boolean;
}): JSX.Element {
  return (
    <div className='flex items-center gap-3 rounded-md border border-border bg-card/60 px-3 py-2'>
      <div className='min-w-0 grow'>
        <p className='text-sm font-medium'>{label}</p>
        <p className='text-xs text-muted-foreground'>{description}</p>
      </div>
      <div className='flex items-center gap-1'>
        <RowButton
          label={`Move ${label} up`}
          disabled={disableUp}
          onClick={onMoveUp}
          icon={ArrowUp}
        />
        <RowButton
          label={`Move ${label} down`}
          disabled={disableDown}
          onClick={onMoveDown}
          icon={ArrowDown}
        />
      </div>
      <button
        type='button'
        onClick={onToggle}
        className={cn(
          'inline-flex items-center gap-1 rounded-md border px-2 py-1 text-xs',
          visible
            ? 'border-primary/40 text-primary'
            : 'border-border text-muted-foreground'
        )}
      >
        {visible ? <Eye className='h-3.5 w-3.5' /> : <EyeOff className='h-3.5 w-3.5' />}
        {visible ? 'Visible' : 'Hidden'}
      </button>
    </div>
  );
}

function InstalledRow({
  label,
  description,
  detail,
  visible,
  onToggle,
  onMoveUp,
  onMoveDown,
  disableUp,
  disableDown,
}: {
  label: string;
  description: string;
  detail: string | null;
  visible: boolean;
  onToggle: () => void;
  onMoveUp: () => void;
  onMoveDown: () => void;
  disableUp: boolean;
  disableDown: boolean;
}): JSX.Element {
  return (
    <div className='flex items-center gap-3 rounded-md border border-border bg-card/60 px-3 py-2'>
      <div className='min-w-0 grow'>
        <p className='text-sm font-medium'>{label}</p>
        <p className='text-xs text-muted-foreground'>
          {detail ? `${description} ${detail}` : description}
        </p>
      </div>
      <div className='flex items-center gap-1'>
        <RowButton
          label={`Move ${label} up`}
          disabled={disableUp}
          onClick={onMoveUp}
          icon={ArrowUp}
        />
        <RowButton
          label={`Move ${label} down`}
          disabled={disableDown}
          onClick={onMoveDown}
          icon={ArrowDown}
        />
      </div>
      <button
        type='button'
        onClick={onToggle}
        className={cn(
          'inline-flex items-center gap-1 rounded-md border px-2 py-1 text-xs',
          visible
            ? 'border-primary/40 text-primary'
            : 'border-border text-muted-foreground'
        )}
      >
        {visible ? <Eye className='h-3.5 w-3.5' /> : <EyeOff className='h-3.5 w-3.5' />}
        {visible ? 'Shown' : 'Show'}
      </button>
    </div>
  );
}

function RowButton({
  label,
  disabled,
  onClick,
  icon: Icon,
}: {
  label: string;
  disabled: boolean;
  onClick: () => void;
  icon: typeof ArrowUp;
}): JSX.Element {
  return (
    <button
      type='button'
      aria-label={label}
      disabled={disabled}
      onClick={onClick}
      className='rounded-md border border-border p-1 text-muted-foreground transition-colors hover:border-primary hover:text-foreground disabled:opacity-40'
    >
      <Icon className='h-3.5 w-3.5' aria-hidden='true' />
    </button>
  );
}
