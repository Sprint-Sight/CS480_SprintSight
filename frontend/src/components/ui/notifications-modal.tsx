"use client";

import React from "react";
import { CheckCheck, Loader2, X } from "lucide-react";
import type { DashboardNotification } from "@/hooks/use-notifications";

interface NotificationsDropdownProps {
  isOpen: boolean;
  onClose: () => void;
  notifications: DashboardNotification[];
  unreadCount: number;
  isLoading: boolean;
  error: string;
  onMarkAsRead: (notificationId: string) => Promise<void>;
  onMarkAllAsRead: () => Promise<void>;
}

const eventTypeLabels: Record<string, { label: string; bgColor: string; textColor: string }> = {
  project_membership: { label: "Project", bgColor: "bg-blue-100", textColor: "text-blue-700" },
  course_enrollment: { label: "Course", bgColor: "bg-emerald-100", textColor: "text-emerald-700" },
  assignment: { label: "Assignment", bgColor: "bg-amber-100", textColor: "text-amber-700" },
  team: { label: "Team", bgColor: "bg-purple-100", textColor: "text-purple-700" },
  assessment: { label: "Assessment", bgColor: "bg-indigo-100", textColor: "text-indigo-700" },
};

export function NotificationsDropdown({
  isOpen,
  onClose,
  notifications,
  unreadCount,
  isLoading,
  error,
  onMarkAsRead,
  onMarkAllAsRead,
}: NotificationsDropdownProps) {
  const getEventTypeStyle = (eventType: string) => {
    return eventTypeLabels[eventType] || { label: eventType, bgColor: "bg-slate-100", textColor: "text-slate-700" };
  };


  if (!isOpen) return null;

  return (
    <div
      className="absolute right-0 top-full z-50 mt-2 w-80 max-h-96 flex flex-col rounded-xl border border-slate-200 bg-white shadow-[0_12px_28px_rgba(15,23,42,0.2)]"
    >
      {/* Header */}
      <div className="flex items-center justify-between border-b border-slate-100 bg-white px-4 py-3 flex-shrink-0">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-semibold text-slate-900">Notifications</h2>
          {unreadCount > 0 && (
            <span className="inline-flex items-center justify-center h-5 w-5 rounded-full bg-blue-600 text-xs font-bold text-white">
              {unreadCount > 99 ? "99+" : unreadCount}
            </span>
          )}
        </div>
        <button
          type="button"
          onClick={onClose}
          className="rounded-lg p-1 text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-600"
          aria-label="Close notifications"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      {/* Error State */}
      {error && (
        <div className="px-4 py-3 bg-rose-50 border-b border-rose-200 flex-shrink-0">
          <p className="text-xs text-rose-700">{error}</p>
        </div>
      )}

      {/* Content */}
      <div className="flex-1 overflow-y-auto min-h-0">
        {isLoading && notifications.length === 0 ? (
          <div className="flex items-center justify-center py-6">
            <Loader2 className="h-4 w-4 animate-spin text-slate-400" />
            <span className="ml-2 text-xs text-slate-500">Loading...</span>
          </div>
        ) : notifications.length === 0 ? (
          <div className="flex items-center justify-center py-6">
            <p className="text-xs text-slate-500">You are all caught up.</p>
          </div>
        ) : (
          <div className="divide-y divide-slate-100">
            {notifications.map((notification) => (
              <div
                key={notification.id}
                className={`flex items-start gap-3 px-4 py-3 transition-colors hover:bg-slate-50 ${
                  notification.read_at ? "bg-white" : "bg-blue-50"
                }`}
              >
                <div className="flex-1 min-w-0">
                  <button
                    type="button"
                    onClick={() => void onMarkAsRead(notification.id)}
                    className="w-full text-left focus:outline-none"
                  >
                    <div className="flex items-center gap-2 mb-1">
                      <h3 className="text-xs font-medium text-slate-900 truncate">
                        {notification.title}
                      </h3>
                      <span
                        className={`text-[10px] font-medium px-1.5 py-0.5 rounded-full whitespace-nowrap ${
                          getEventTypeStyle(notification.event_type).bgColor
                        } ${getEventTypeStyle(notification.event_type).textColor}`}
                      >
                        {getEventTypeStyle(notification.event_type).label}
                      </span>
                    </div>
                    <p className="text-[11px] leading-4 text-slate-600 line-clamp-2">
                      {notification.message}
                    </p>
                    <span className="block text-[10px] text-slate-400 mt-1">
                      {new Date(notification.created_at).toLocaleString()}
                    </span>
                  </button>
                </div>
                <div className="flex flex-col items-end gap-1 flex-shrink-0">
                  {!notification.read_at && (
                    <span className="h-1.5 w-1.5 rounded-full bg-blue-600" />
                  )}
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      void onMarkAsRead(notification.id);
                    }}
                    className="rounded-lg p-1 text-slate-400 transition-colors hover:bg-slate-200 hover:text-slate-600"
                    aria-label={`Remove notification: ${notification.title}`}
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Footer */}
      {unreadCount > 0 && notifications.length > 0 && (
        <div className="border-t border-slate-100 bg-white px-4 py-2 flex-shrink-0">
          <button
            onClick={() => void onMarkAllAsRead()}
            className="w-full flex items-center justify-center gap-1 text-xs font-medium text-blue-600 hover:text-blue-700 hover:bg-blue-50 rounded-lg px-2 py-1.5 transition-colors"
          >
            <CheckCheck className="h-3 w-3" />
            Mark all as read
          </button>
        </div>
      )}
    </div>
  );
}
