import * as React from 'react';

import { cn } from '@shared/utils';

// Lightweight modal primitive. (shadcn's Dialog wraps @radix-ui/react-dialog;
// this hand-rolled version covers Synapse's needs -- backdrop, Esc-to-close,
// click-outside, focus-on-open, focus trap, restore-focus-on-close -- without
// another dependency. Used by the project form, confirm dialogs, log viewer,
// shortcuts help, etc.)

export interface ModalProps {
  open: boolean;
  onClose: () => void;
  labelledBy?: string;
  /** Allow Esc + backdrop click to dismiss. Default true. */
  dismissable?: boolean;
  className?: string;
  children: React.ReactNode;
}

// Tab-stop selector for the focus trap. Mirrors the well-known set used by
// most a11y libraries; covers <a href>, form fields, buttons, contenteditable,
// and anything with a non-negative tabindex.
const FOCUSABLE_SELECTOR = [
  'a[href]:not([disabled])',
  'button:not([disabled])',
  'input:not([disabled]):not([type="hidden"])',
  'textarea:not([disabled])',
  'select:not([disabled])',
  'details>summary',
  '[tabindex]:not([tabindex="-1"]):not([disabled])',
  '[contenteditable="true"]',
].join(',');

export function Modal({
  open,
  onClose,
  labelledBy,
  dismissable = true,
  className,
  children,
}: ModalProps): JSX.Element | null {
  const panelRef = React.useRef<HTMLDivElement | null>(null);

  React.useEffect(() => {
    if (!open) return;
    // Remember where focus came from so we can restore it on close. Without
    // this, the user gets dropped back to the top of the page after a
    // keyboard interaction inside the modal -- breaks the flow badly.
    const previouslyFocused = document.activeElement as HTMLElement | null;

    function focusFirstInPanel(): void {
      const panel = panelRef.current;
      if (!panel) return;
      const focusables = panel.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR);
      // If the panel has at least one focusable element, land on the first;
      // otherwise focus the panel itself so the keyboard isn't stranded.
      if (focusables.length > 0) {
        focusables[0].focus();
      } else {
        panel.focus();
      }
    }

    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape' && dismissable) {
        onClose();
        return;
      }
      if (e.key !== 'Tab') return;
      const panel = panelRef.current;
      if (!panel) return;
      const focusables = Array.from(
        panel.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)
      ).filter((el) => el.offsetParent !== null);
      // No focusable children -> keep focus on the panel (which is
      // tabIndex=-1 so it doesn't intercept Tab from inside).
      if (focusables.length === 0) {
        e.preventDefault();
        panel.focus();
        return;
      }
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      const activeWithinPanel = panel.contains(document.activeElement);
      // Cycle in both directions so Tab never escapes the modal.
      if (e.shiftKey) {
        if (!activeWithinPanel || document.activeElement === first) {
          e.preventDefault();
          last.focus();
        }
      } else {
        if (!activeWithinPanel || document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    }

    window.addEventListener('keydown', onKey);
    // Defer to next tick so React's commit completes and children are
    // measurable before we ask querySelectorAll for focusables.
    const focusTimer = window.setTimeout(focusFirstInPanel, 0);

    return () => {
      window.removeEventListener('keydown', onKey);
      window.clearTimeout(focusTimer);
      // Restore focus only if it's still inside the dismissed modal --
      // otherwise the user has clicked elsewhere and we should respect that.
      if (
        previouslyFocused &&
        typeof previouslyFocused.focus === 'function' &&
        document.activeElement &&
        panelRef.current?.contains(document.activeElement)
      ) {
        previouslyFocused.focus();
      }
    };
  }, [open, dismissable, onClose]);

  if (!open) return null;

  return (
    <div
      role='dialog'
      aria-modal='true'
      aria-labelledby={labelledBy}
      className='fixed inset-0 z-50 flex items-center justify-center bg-background/80 p-6 backdrop-blur-sm'
      onClick={(e) => {
        if (dismissable && e.target === e.currentTarget) onClose();
      }}
    >
      <div
        ref={panelRef}
        tabIndex={-1}
        className={cn(
          'flex max-h-[90vh] w-full max-w-lg flex-col gap-4 overflow-y-auto rounded-lg',
          'border border-border bg-card p-6 shadow-xl outline-none',
          className
        )}
      >
        {children}
      </div>
    </div>
  );
}
