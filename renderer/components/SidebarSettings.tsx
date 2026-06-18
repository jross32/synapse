// Sidebar customize modal (v0.1.36 A6).
//
// Lets the user reorder + hide nav items they don't use. Home and
// Settings are locked (always visible, top + bottom).
//
// HTML5 drag-and-drop -- no library. Drag a row to a new slot;
// reorder snaps. Per-row checkbox toggles visibility.

import { useState } from 'react';
import { GripVertical, Lock, RotateCcw } from 'lucide-react';

import {
  NAV_ITEMS,
  applySidebarLayout,
  loadSidebarLayout,
  saveSidebarLayout,
  type PageId,
  type SidebarLayout,
} from '@shared/nav';
import { cn } from '@shared/utils';
import { Button } from './ui/button';
import { Modal } from './ui/modal';

export interface SidebarSettingsProps {
  open: boolean;
  onClose: () => void;
  onChange?: () => void;
}

function defaultLayout(): SidebarLayout {
  return { order: NAV_ITEMS.map((n) => n.id), hidden: [] };
}

export function SidebarSettings({
  open,
  onClose,
  onChange,
}: SidebarSettingsProps): JSX.Element | null {
  const [layout, setLayout] = useState<SidebarLayout>(() => loadSidebarLayout());
  const [dragId, setDragId] = useState<PageId | null>(null);

  function commit(next: SidebarLayout): void {
    setLayout(next);
    saveSidebarLayout(next);
    onChange?.();
  }

  function toggleHidden(id: PageId): void {
    const willHide = !layout.hidden.includes(id);
    commit({
      ...layout,
      hidden: willHide
        ? [...layout.hidden, id]
        : layout.hidden.filter((h) => h !== id),
    });
  }

  function handleDrop(targetId: PageId): void {
    if (!dragId || dragId === targetId) return;
    const filtered = layout.order.filter((id) => id !== dragId);
    const insertAt = filtered.indexOf(targetId);
    const next = [
      ...filtered.slice(0, insertAt),
      dragId,
      ...filtered.slice(insertAt),
    ];
    commit({ ...layout, order: next });
    setDragId(null);
  }

  function resetToDefault(): void {
    commit(defaultLayout());
  }

  if (!open) return null;

  // Display NAV_ITEMS in their persisted order, falling back to
  // declaration order for unknown ids (defensive).
  const knownIds = new Set(NAV_ITEMS.map((n) => n.id));
  const ordered: PageId[] = [];
  for (const id of layout.order) if (knownIds.has(id)) ordered.push(id);
  for (const item of NAV_ITEMS) if (!ordered.includes(item.id)) ordered.push(item.id);

  return (
    <Modal
      open
      onClose={onClose}
      labelledBy='sidebar-settings-title'
      className='max-w-md'
    >
      <div className='flex items-center justify-between gap-3'>
        <div>
          <h2 id='sidebar-settings-title' className='text-base font-semibold'>
            Customize sidebar
          </h2>
          <p className='mt-0.5 text-xs text-muted-foreground'>
            Drag to reorder. Uncheck to hide. Home + Settings stay locked.
          </p>
        </div>
        <Button
          variant='outline'
          size='sm'
          onClick={resetToDefault}
          aria-label='Reset sidebar to default'
        >
          <RotateCcw className='h-3.5 w-3.5' aria-hidden='true' />
          Reset
        </Button>
      </div>
      <ul className='flex flex-col gap-1'>
        {ordered.map((id) => {
          const item = NAV_ITEMS.find((n) => n.id === id);
          if (!item) return null;
          const Icon = item.icon;
          const isHidden = layout.hidden.includes(id);
          const isDragging = dragId === id;
          const locked = !!item.locked;
          return (
            <li
              key={id}
              draggable={!locked}
              onDragStart={() => setDragId(id)}
              onDragOver={(e) => {
                if (!locked && dragId && dragId !== id) e.preventDefault();
              }}
              onDrop={() => handleDrop(id)}
              onDragEnd={() => setDragId(null)}
              className={cn(
                'flex items-center gap-2 rounded-md border border-border bg-secondary/30 px-2 py-1.5',
                isDragging && 'opacity-50',
                locked && 'bg-secondary/10'
              )}
            >
              {locked ? (
                <Lock className='h-3.5 w-3.5 shrink-0 text-muted-foreground' aria-hidden='true' />
              ) : (
                <GripVertical
                  className='h-3.5 w-3.5 shrink-0 cursor-grab text-muted-foreground'
                  aria-hidden='true'
                />
              )}
              <Icon className='h-4 w-4 shrink-0 text-foreground' aria-hidden='true' />
              <span className='grow text-sm'>{item.label}</span>
              {locked ? (
                <span className='text-xs text-muted-foreground'>locked</span>
              ) : (
                <label className='flex shrink-0 items-center gap-1 text-xs text-muted-foreground'>
                  <input
                    type='checkbox'
                    checked={!isHidden}
                    onChange={() => toggleHidden(id)}
                    aria-label={`Show ${item.label} in sidebar`}
                  />
                  Visible
                </label>
              )}
            </li>
          );
        })}
      </ul>
      <p className='text-[10px] text-muted-foreground'>
        Layout is saved to this browser only ({applySidebarLayout(layout).length}{' '}
        visible).
      </p>
    </Modal>
  );
}
