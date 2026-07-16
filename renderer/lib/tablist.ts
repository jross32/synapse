// Keyboard navigation for a `role="tablist"` row of `role="tab"` buttons (the
// shared TopTab pattern). Attach to the tablist container's onKeyDown: Arrow
// Left/Right move between tabs (wrapping), Home/End jump to the first/last, and
// the focused tab is activated (matching the click-to-select behavior). Generic
// and DOM-based, so it works for any tablist without threading the tab list in.

import type { KeyboardEvent } from 'react';

const NAV_KEYS = new Set(['ArrowRight', 'ArrowLeft', 'Home', 'End']);

export function handleTablistKeydown(event: KeyboardEvent<HTMLElement>): void {
  if (!NAV_KEYS.has(event.key)) return;
  const tabs = Array.from(
    event.currentTarget.querySelectorAll<HTMLButtonElement>('[role="tab"]:not([disabled])')
  );
  if (tabs.length === 0) return;

  const current = tabs.findIndex((tab) => tab === document.activeElement);
  let next = current < 0 ? 0 : current;
  switch (event.key) {
    case 'ArrowRight':
      next = (current + 1) % tabs.length;
      break;
    case 'ArrowLeft':
      next = (current - 1 + tabs.length) % tabs.length;
      break;
    case 'Home':
      next = 0;
      break;
    case 'End':
      next = tabs.length - 1;
      break;
  }

  event.preventDefault();
  const target = tabs[next];
  target.focus();
  target.click();
}
