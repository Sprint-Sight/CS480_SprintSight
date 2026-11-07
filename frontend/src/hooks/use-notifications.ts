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

type UseNotificationsReturn = {
  notifications: DashboardNotification[];
  unreadCount: number;
  isLoading: boolean;
  error: string;
  refresh: () => Promise<void>;
  markAsRead: (notificationId: string) => Promise<void>;
  markAllAsRead: () => Promise<void>;
};

export function useNotifications(): UseNotificationsReturn {
  const [notifications, setNotifications] = useState<DashboardNotification[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");
  const refreshIntervalRef = useRef<NodeJS.Timeout | null>(null);

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
      try {
        await apiRequest(`/notifications/${notificationId}/read`, {
          method: "PATCH",
        });
        // Remove notification from list and update unread count immediately
        setNotifications((prev) => prev.filter((n) => n.id !== notificationId));
        setUnreadCount((prev) => Math.max(0, prev - 1));
      } catch (err) {
        console.error(`Failed to mark notification ${notificationId} as read:`, err);
      }
    },
    []
  );

  const markAllAsRead = useCallback(async () => {
    const unread = notifications.filter((n) => !n.read_at);

    // Optimistically clear the list; failed requests are restored below.
    setNotifications([]);
    setUnreadCount(0);

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
    setNotifications((prev) => [
      ...prev,
      ...failed.filter((f) => !prev.some((p) => p.id === f.id)),
    ]);
    setUnreadCount((prev) => prev + failed.length);
  }, [notifications]);

  useEffect(() => {
    if (typeof window === "undefined") return;

    void refresh();
    refreshIntervalRef.current = window.setInterval(() => void refresh(), 30_000) as unknown as NodeJS.Timeout;

    return () => {
      if (refreshIntervalRef.current) {
        window.clearInterval(refreshIntervalRef.current as unknown as number);
      }
    };
  }, [refresh]);

  return {
    notifications,
    unreadCount,
    isLoading,
    error,
    refresh,
    markAsRead,
    markAllAsRead,
  };
}
