// Client for the AI-activity feed (ADR-0028). Types mirror
// daemon/synapse_daemon/activity.py + routes_activity.py.

import { apiFetch } from './api-client';

/** A renderer NavigationIntent, passed straight to the app's navigate() flow. */
export type NotificationIntent = Record<string, unknown>;

export interface NotificationLink {
  label: string;
  intent: NotificationIntent;
}

/** green | yellow | red | info — drives the status dot colour. */
export type ActivityLevel = 'green' | 'yellow' | 'red' | 'info';

export interface ActivityNotification {
  id: string;
  session_id: string | null;
  seq: number | null;
  kind: string;
  level: ActivityLevel;
  title: string;
  body_md: string;
  links: NotificationLink[];
  token_usage: Record<string, unknown> | null;
  created_at: string;
  read_at: string | null;
}

export interface ActivityFeed {
  notifications: ActivityNotification[];
  unread_count: number;
}

export interface ActivitySession {
  id: string;
  seq: number;
  project_id: string | null;
  runtime_id: string;
  agent_label: string;
  task: string;
  status: string;
  connection_level: ActivityLevel;
  connection_code: string;
  registered_at: string;
  last_heartbeat_at: string;
  ended_at: string | null;
  stale: boolean;
}

export interface ActivitySessionDetail {
  session: ActivitySession;
  squads: Array<{
    squad: Record<string, unknown>;
    work_items: Array<Record<string, unknown>>;
    token_usage: Record<string, unknown>;
  }>;
  notifications: ActivityNotification[];
}

export function getActivityNotifications(unread = false, limit = 50): Promise<ActivityFeed> {
  return apiFetch<ActivityFeed>(
    `/activity/notifications?unread=${unread ? 'true' : 'false'}&limit=${limit}`,
    { method: 'GET' }
  );
}

export function markNotificationRead(id: string): Promise<ActivityNotification> {
  return apiFetch<ActivityNotification>(`/activity/notifications/${encodeURIComponent(id)}/read`, {
    method: 'POST',
  });
}

export function markAllNotificationsRead(): Promise<{ marked_read: number }> {
  return apiFetch<{ marked_read: number }>('/activity/notifications/read-all', { method: 'POST' });
}

export function getActivitySessions(): Promise<{ sessions: ActivitySession[] }> {
  return apiFetch<{ sessions: ActivitySession[] }>('/activity/sessions', { method: 'GET' });
}

export function getActivitySessionDetail(id: string): Promise<ActivitySessionDetail> {
  return apiFetch<ActivitySessionDetail>(`/activity/sessions/${encodeURIComponent(id)}`, {
    method: 'GET',
  });
}
