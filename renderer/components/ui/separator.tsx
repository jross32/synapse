import * as React from 'react';

import { cn } from '@shared/utils';

// Lightweight Separator -- a plain styled divider. (The full shadcn version
// wraps @radix-ui/react-separator; a div carries the same visual weight and
// avoids another dependency for what is just a 1px line.)

export interface SeparatorProps extends React.HTMLAttributes<HTMLDivElement> {
  orientation?: 'horizontal' | 'vertical';
}

const Separator = React.forwardRef<HTMLDivElement, SeparatorProps>(
  ({ className, orientation = 'horizontal', ...props }, ref) => (
    <div
      ref={ref}
      role='separator'
      aria-orientation={orientation}
      className={cn(
        'shrink-0 bg-border',
        orientation === 'horizontal' ? 'h-px w-full' : 'h-full w-px',
        className
      )}
      {...props}
    />
  )
);
Separator.displayName = 'Separator';

export { Separator };
