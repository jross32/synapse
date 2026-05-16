// Navigation model for the Synapse shell. The app is a single Electron
// window, so "routing" is just an active-page enum -- no URL router needed.

import { Activity, House, LayoutGrid, Settings, Wrench, type LucideIcon } from 'lucide-react';

export type PageId = 'home' | 'apps' | 'tools' | 'processes' | 'settings';

export interface NavItem {
  id: PageId;
  label: string;
  icon: LucideIcon;
  description: string;
}

export const NAV_ITEMS: NavItem[] = [
  { id: 'home', label: 'Home', icon: House, description: 'Featured projects + tools, recent activity' },
  { id: 'apps', label: 'Apps', icon: LayoutGrid, description: 'Launch + manage your projects' },
  { id: 'tools', label: 'Tools', icon: Wrench, description: 'Synapse tools, agents + workflows' },
  { id: 'processes', label: 'Processes', icon: Activity, description: 'Everything running right now' },
  { id: 'settings', label: 'Settings', icon: Settings, description: 'Daemon, theme + about' },
];

export const DEFAULT_PAGE: PageId = 'home';
