// Shared AI-activity feed state for the Notification Center (ADR-0028).
//
// Keeps the unread count + the recent notification list live: the daemon
// re-announces every new notification as `v1.activity.notification`, so the bell
// badge lights up the moment an AI connects, spins up a squad, or files an idea —
// no polling, no refresh button.

import { useCallback, useEffect, useState } from 'react';

import {
  getActivityNotifications,
  markAllNotificationsRead,
  markNotificationRead,
  type ActivityNotification,
} from './activity-client';
import { useDaemon } from './daemon-context';

export interface ActivityState {
  notifications: ActivityNotification[];
  unreadCount: number;
  loaded: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  markRead: (id: string) => Promise<void>;
  markAllRead: () => Promise<void>;
}

export function useActivity(limit = 30): ActivityState {
  const { subscribeRaw, connState } = useDaemon();
  const [notifications, setNotifications] = useState<ActivityNotification[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const feed = await getActivityNotifications(false, limit);
      setNotifications(feed.notifications);
      setUnreadCount(feed.unread_count);
      setError(null);
    } catch (e) {
      // Keep the last known feed on a transient error rather than flashing empty.
      setError((e as Error).message || 'Could not load activity.');
    } finally {
      setLoaded(true);
    }
  }, [limit]);

  useEffect(() => {
    if (connState !== 'open') return;
    void refresh();
  }, [connState, refresh]);

  useEffect(
    () =>
      subscribeRaw((event) => {
        if (event.name === 'v1.activity.notification') void refresh();
      }),
    [subscribeRaw, refresh]
  );

  const markRead = useCallback(async (id: string) => {
    // Optimistic: drop the unread dot immediately, then reconcile with the daemon.
    setNotifications((list) =>
      list.map((n) => (n.id === id && !n.read_at ? { ...n, read_at: new Date().toISOString() } : n))
    );
    setUnreadCount((c) => Math.max(0, c - 1));
    try {
      await markNotificationRead(id);
    } catch {
      /* the next refresh reconciles */
    }
  }, []);

  const markAllRead = useCallback(async () => {
    setNotifications((list) =>
      list.map((n) => (n.read_at ? n : { ...n, read_at: new Date().toISOString() }))
    );
    setUnreadCount(0);
    try {
      await markAllNotificationsRead();
    } catch {
      /* the next refresh reconciles */
    }
  }, []);

  return { notifications, unreadCount, loaded, error, refresh, markRead, markAllRead };
}
