import { HelpCircle } from 'lucide-react';

import { cn } from '@shared/utils';
import { Tooltip, type TooltipSide } from './ui/tooltip';

// A ? icon that shows explanatory text on hover/focus.
// Drop next to any label, field name, or jargon term.

export interface HelpIconProps {
  content: React.ReactNode;
  side?: TooltipSide;
  className?: string;
  /** Icon size class, default h-3.5 w-3.5 */
  size?: string;
}

export function HelpIcon({ content, side = 'top', className, size = 'h-3.5 w-3.5' }: HelpIconProps): JSX.Element {
  return (
    <Tooltip content={content} side={side}>
      <span
        tabIndex={0}
        role='button'
        aria-label='Help'
        // Stop the click from bubbling: when a HelpIcon sits inside a <label>
        // (e.g. AgentSquadsView fields), a bare click would otherwise redirect
        // focus/activation to the label's form control.
        onClick={(event) => event.stopPropagation()}
        className={cn(
          'inline-flex cursor-default items-center text-muted-foreground/60 hover:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring rounded',
          className
        )}
      >
        <HelpCircle className={size} aria-hidden='true' />
      </span>
    </Tooltip>
  );
}
