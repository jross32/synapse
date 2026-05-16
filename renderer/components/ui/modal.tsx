import * as React from 'react';

import { cn } from '@shared/utils';

// Lightweight modal primitive. (shadcn's Dialog wraps @radix-ui/react-dialog;
// this hand-rolled version covers Synapse's needs -- backdrop, Esc-to-close,
// click-outside, focus-on-open -- without another dependency. Used by the
// project form, confirm dialogs, and the log viewer.)

export interface ModalProps {
  open: boolean;
  onClose: () => void;
  labelledBy?: string;
  /** Allow Esc + backdrop click to dismiss. Default true. */
  dismissable?: boolean;
  className?: string;
  children: React.ReactNode;
}

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
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape' && dismissable) onClose();
    }
    window.addEventListener('keydown', onKey);
    // Focus the panel so screen readers + keyboard land inside it.
    panelRef.current?.focus();
    return () => window.removeEventListener('keydown', onKey);
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
