import { apiFetch } from './api-client';

export type InstalledPageStatus = 'connected' | 'available' | 'offline' | 'error';

export interface InstalledPageView {
  id: string;
  label: string;
  description: string;
  icon: string;
  route_kind: string;
  source_kind: string;
  source_id: string;
  default_visible: boolean;
  status: InstalledPageStatus;
  detail: string | null;
}

export interface InstalledPageList {
  pages: InstalledPageView[];
}

export interface WebScraperOverview {
  id: string;
  label: string;
  status: InstalledPageStatus;
  detail: string | null;
  source_id: string;
  source_url: string | null;
  base_url: string | null;
  docs_url: string | null;
  ui_url: string | null;
  tool_count: number | null;
  prompt_count: number | null;
}

export function listInstalledPages(): Promise<InstalledPageList> {
  return apiFetch<InstalledPageList>('/installed-pages', { method: 'GET' });
}

export function getWebScraperOverview(): Promise<WebScraperOverview> {
  return apiFetch<WebScraperOverview>('/installed-pages/web-scraper', { method: 'GET' });
}

export function getWebScraperSaves(): Promise<unknown> {
  return apiFetch('/installed-pages/web-scraper/saves', { method: 'GET' });
}

export function getWebScraperSchedules(): Promise<unknown> {
  return apiFetch('/installed-pages/web-scraper/schedules', { method: 'GET' });
}

export function getWebScraperActive(): Promise<unknown> {
  return apiFetch('/installed-pages/web-scraper/active', { method: 'GET' });
}

export function scrapeWebScraperUrl(body: Record<string, unknown>): Promise<unknown> {
  return apiFetch('/installed-pages/web-scraper/scrape-url', {
    method: 'POST',
    body,
  });
}
