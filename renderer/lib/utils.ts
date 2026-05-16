// shadcn/ui's class-merge helper. Combines clsx (conditional classes) with
// tailwind-merge (dedupes conflicting Tailwind utilities). Every shadcn
// component imports `cn` from here.

import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
