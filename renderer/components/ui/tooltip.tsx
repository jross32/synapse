import * as React from 'react';

import { cn } from '@shared/utils';

// Hand-rolled Tooltip (no extra Radix dep). Appears on hover/focus after a
// short delay; hidden on pointer-leave and blur. Accessible: role="tooltip" +
// aria-describedby wiring. Side defaults to 'top'.

export type TooltipSide = 'top' | 'bottom' | 'left' | 'right';

export interface TooltipProps {
  content: React.ReactNode;
  side?: TooltipSide;
  /** Extra classes on the bubble. */
  className?: string;
  children: React.ReactElement;
  /** Delay before showing, ms. Default 300. */
  delayMs?: number;
}

const OFFSET = 8; // px gap between trigger and bubble

export function Tooltip({
  content,
  side = 'top',
  className,
  children,
  delayMs = 300,
}: TooltipProps): JSX.Element {
  const [visible, setVisible] = React.useState(false);
  const timerRef = React.useRef<ReturnType<typeof setTimeout> | null>(null);
  const id = React.useId();

  function show(): void {
    timerRef.current = setTimeout(() => setVisible(true), delayMs);
  }
  function hide(): void {
    if (timerRef.current) clearTimeout(timerRef.current);
    setVisible(false);
  }

  React.useEffect(() => () => { if (timerRef.current) clearTimeout(timerRef.current); }, []);

  // Clone the trigger to inject aria-describedby and event handlers.
  const trigger = React.cloneElement(children, {
    'aria-describedby': visible ? id : undefined,
    onMouseEnter: (e: React.MouseEvent) => {
      show();
      children.props.onMouseEnter?.(e);
    },
    onMouseLeave: (e: React.MouseEvent) => {
      hide();
      children.props.onMouseLeave?.(e);
    },
    onFocus: (e: React.FocusEvent) => {
      show();
      children.props.onFocus?.(e);
    },
    onBlur: (e: React.FocusEvent) => {
      hide();
      children.props.onBlur?.(e);
    },
  });

  const bubbleClasses = cn(
    'pointer-events-none absolute z-50 max-w-[240px] rounded-md border border-border/50',
    'bg-popover px-2.5 py-1.5 text-xs text-popover-foreground shadow-md',
    'animate-in fade-in-0 zoom-in-95',
    // positional anchor classes
    side === 'top' && 'bottom-full left-1/2 -translate-x-1/2',
    side === 'bottom' && 'top-full left-1/2 -translate-x-1/2',
    side === 'left' && 'right-full top-1/2 -translate-y-1/2',
    side === 'right' && 'left-full top-1/2 -translate-y-1/2',
    className
  );

  const offsetStyle: React.CSSProperties = {
    [side === 'top' ? 'marginBottom' : side === 'bottom' ? 'marginTop' : side === 'left' ? 'marginRight' : 'marginLeft']: OFFSET,
  };

  return (
    <span className='relative inline-flex'>
      {trigger}
      {visible && content && (
        <span id={id} role='tooltip' className={bubbleClasses} style={offsetStyle}>
          {content}
        </span>
      )}
    </span>
  );
}
