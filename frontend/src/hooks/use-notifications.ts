"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { apiRequest, getAuthToken } from "@/features/projects/components/projects-api";

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
    const token = getAuthToken();
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
      const message = err instanceof Error ? err.message : "Could not load notifications.";
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
    // Filter to get unread notifications from current state
    setNotifications((prev) => {
      const unreadNotifications = prev.filter((n) => !n.read_at);
      
      // Send PATCH requests for all unread notifications
      unreadNotifications.forEach((n) => {
        void apiRequest(`/notifications/${n.id}/read`, { method: "PATCH" }).catch((err) => {
          console.error(`Failed to mark notification ${n.id} as read:`, err);
        });
      });

      // Remove all notifications from the list
      return [];
    });

    // Reset unread count
    setUnreadCount(0);
  }, []);

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
