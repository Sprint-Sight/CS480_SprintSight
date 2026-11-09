"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { apiRequest, getErrorMessage } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";

export type DashboardNotification = {
  id: string;
  event_type: string;
  title: string;
  message: string;
  created_at: string;
  read_at: string | null;
};

type NotificationResponse = {
  notifications: DashboardNotification[];
  unread_count: number;
};

const POLL_INTERVAL_MS = 30_000;

type UseNotificationsReturn = {
  notifications: DashboardNotification[];
  unreadCount: number;
  isLoading: boolean;
  error: string;
  /** Polite screen-reader message describing newly arrived unread notifications. */
  announcement: string;
  refresh: () => Promise<void>;
  markAsRead: (notificationId: string) => Promise<void>;
  markAllAsRead: () => Promise<void>;
};

export function useNotifications(): UseNotificationsReturn {
  const [notifications, setNotifications] = useState<DashboardNotification[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");
  const [announcement, setAnnouncement] = useState("");
  const refreshIntervalRef = useRef<number | null>(null);
  // Null until the first successful load, so existing notifications are not announced on page load.
  const seenUnreadIdsRef = useRef<Set<string> | null>(null);
  const pendingReadIdsRef = useRef<Set<string>>(new Set());

  const refresh = useCallback(async () => {
    const token = getSessionToken();
    if (!token) {
      setError("You are not signed in. Please log in again.");
      setIsLoading(false);
      return;
    }

    setIsLoading(true);
    try {
      const response = await apiRequest<NotificationResponse>("/notifications");
      const unreadIds = response.notifications.filter((n) => !n.read_at).map((n) => n.id);
      const seen = seenUnreadIdsRef.current;
      if (seen) {
        const freshCount = unreadIds.filter((id) => !seen.has(id)).length;
        if (freshCount > 0) {
          setAnnouncement(
            freshCount === 1 ? "1 new notification" : `${freshCount} new notifications`,
          );
        }
      }
      seenUnreadIdsRef.current = new Set([...(seen ?? []), ...unreadIds]);
      setNotifications(response.notifications);
      setUnreadCount(response.unread_count);
      setError("");
    } catch (err) {
      const message = getErrorMessage(err, "Could not load notifications.");
      setError(message);
      console.error("Failed to load notifications:", err);
    } finally {
      setIsLoading(false);
    }
  }, []);

  const markAsRead = useCallback(
    async (notificationId: string) => {
      const target = notifications.find((n) => n.id === notificationId);
      if (!target || target.read_at || pendingReadIdsRef.current.has(notificationId)) return;

      pendingReadIdsRef.current.add(notificationId);
      try {
        await apiRequest(`/notifications/${notificationId}/read`, {
          method: "PATCH",
        });
        // Keep the item so it can be read again; mark it read in place.
        const readAt = new Date().toISOString();
        setNotifications((prev) =>
          prev.map((n) => (n.id === notificationId ? { ...n, read_at: readAt } : n)),
        );
        setUnreadCount((prev) => Math.max(0, prev - 1));
      } catch (err) {
        console.error(`Failed to mark notification ${notificationId} as read:`, err);
      } finally {
        pendingReadIdsRef.current.delete(notificationId);
      }
    },
    [notifications],
  );

  const markAllAsRead = useCallback(async () => {
    const unread = notifications.filter((n) => !n.read_at);
    if (unread.length === 0) return;

    // Optimistically mark everything read; failed requests are restored below.
    const readAt = new Date().toISOString();
    const unreadIds = new Set(unread.map((n) => n.id));
    setNotifications((prev) =>
      prev.map((n) => (unreadIds.has(n.id) ? { ...n, read_at: readAt } : n)),
    );
    setUnreadCount((prev) => Math.max(0, prev - unread.length));

    const results = await Promise.allSettled(
      unread.map((n) => apiRequest(`/notifications/${n.id}/read`, { method: "PATCH" })),
    );

    const failed = unread.filter((_, index) => results[index].status === "rejected");
    if (failed.length === 0) return;

    results.forEach((result, index) => {
      if (result.status === "rejected") {
        console.error(`Failed to mark notification ${unread[index].id} as read:`, result.reason);
      }
    });
    const failedIds = new Set(failed.map((f) => f.id));
    setNotifications((prev) =>
      prev.map((n) => (failedIds.has(n.id) ? { ...n, read_at: null } : n)),
    );
    setUnreadCount((prev) => prev + failed.length);
  }, [notifications]);

  useEffect(() => {
    if (typeof window === "undefined") return;

    const stopPolling = () => {
      if (refreshIntervalRef.current === null) return;
      window.clearInterval(refreshIntervalRef.current);
      refreshIntervalRef.current = null;
    };

    const startPolling = () => {
      if (refreshIntervalRef.current !== null) return;
      refreshIntervalRef.current = window.setInterval(() => void refresh(), POLL_INTERVAL_MS);
    };

    // Pause polling in hidden tabs and catch up immediately when the tab becomes visible again.
    const handleVisibilityChange = () => {
      if (document.visibilityState === "hidden") {
        stopPolling();
        return;
      }
      void refresh();
      startPolling();
    };

    void refresh();
    if (document.visibilityState !== "hidden") startPolling();
    document.addEventListener("visibilitychange", handleVisibilityChange);

    return () => {
      document.removeEventListener("visibilitychange", handleVisibilityChange);
      stopPolling();
    };
  }, [refresh]);

  return {
    notifications,
    unreadCount,
    isLoading,
    error,
    announcement,
    refresh,
    markAsRead,
    markAllAsRead,
  };
}

