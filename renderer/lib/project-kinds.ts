// Shared metadata for project kinds (v0.1.19).
//
// Single source of truth for human labels, badge tone, and icons -- every
// surface that renders a kind (Apps filter, tile badge, edit form, discovery
// row) reads from here so a new kind drops in one place.

import {
  Boxes,
  Code2,
  FileCode,
  Globe,
  Layers,
  ServerCog,
  Shapes,
  type LucideIcon,
} from 'lucide-react';

import type { ProjectKind } from './generated-types';

export interface KindMeta {
  id: ProjectKind;
  label: string;          // user-facing
  short: string;          // 2-3 char label for tight chips
  icon: LucideIcon;
  /** Tailwind classes for the small filled badge on a tile. */
  badgeClass: string;
}

export const KIND_ORDER: ProjectKind[] = [
  'app',
  'ui',
  'service',
  'mcp-server',
  'library',
  'script',
  'other',
];

export const KIND_META: Record<ProjectKind, KindMeta> = {
  app: {
    id: 'app',
    label: 'App',
    short: 'App',
    icon: Boxes,
    badgeClass: 'bg-secondary text-secondary-foreground',
  },
  ui: {
    id: 'ui',
    label: 'UI',
    short: 'UI',
    icon: Globe,
    badgeClass: 'bg-sky-500/15 text-sky-300 dark:text-sky-300',
  },
  service: {
    id: 'service',
    label: 'Service',
    short: 'Svc',
    icon: ServerCog,
    badgeClass: 'bg-emerald-500/15 text-emerald-300 dark:text-emerald-300',
  },
  'mcp-server': {
    id: 'mcp-server',
    label: 'MCP server',
    short: 'MCP',
    icon: Layers,
    badgeClass: 'bg-violet-500/20 text-violet-300 dark:text-violet-200',
  },
  library: {
    id: 'library',
    label: 'Library',
    short: 'Lib',
    icon: Code2,
    badgeClass: 'bg-amber-500/15 text-amber-300 dark:text-amber-300',
  },
  script: {
    id: 'script',
    label: 'Script',
    short: 'Sh',
    icon: FileCode,
    badgeClass: 'bg-orange-500/15 text-orange-300 dark:text-orange-300',
  },
  other: {
    id: 'other',
    label: 'Other',
    short: 'Oth',
    icon: Shapes,
    badgeClass: 'bg-muted text-muted-foreground',
  },
};

export function kindMeta(kind: ProjectKind | string | null | undefined): KindMeta {
  const key = (kind ?? 'app') as ProjectKind;
  return KIND_META[key] ?? KIND_META.app;
}
