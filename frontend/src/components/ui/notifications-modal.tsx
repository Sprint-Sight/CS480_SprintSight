"use client";

import React from "react";
import * as Popover from "@radix-ui/react-popover";
import { CheckCheck, Loader2, X } from "lucide-react";
import type { DashboardNotification } from "@/hooks/use-notifications";

interface NotificationsDropdownProps {
  /** The bell button. Used as the Popover trigger, so it must forward refs and props. */
  children: React.ReactElement;
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  notifications: DashboardNotification[];
  unreadCount: number;
  isLoading: boolean;
  error: string;
  announcement: string;
  onMarkAsRead: (notificationId: string) => Promise<void>;
  onMarkAllAsRead: () => Promise<void>;
}

/**
 * Colour and label for each notification event type. Removals are tinted rose
 * so a student can see at a glance that something was taken away from them
 * rather than granted.
 */
const eventTypeLabels: Record<string, { label: string; bgColor: string; textColor: string }> = {
  project_membership: { label: "Project", bgColor: "bg-blue-100", textColor: "text-blue-700" },
  project_unmembership: { label: "Project removed", bgColor: "bg-rose-100", textColor: "text-rose-700" },
  project_deletion: { label: "Project deleted", bgColor: "bg-rose-100", textColor: "text-rose-700" },
  course_enrollment: { label: "Course", bgColor: "bg-emerald-100", textColor: "text-emerald-700" },
  course_unenrollment: { label: "Course removed", bgColor: "bg-rose-100", textColor: "text-rose-700" },
  course_deletion: { label: "Course deleted", bgColor: "bg-rose-100", textColor: "text-rose-700" },
  document_uploaded: { label: "Document", bgColor: "bg-indigo-100", textColor: "text-indigo-700" },
  assignment: { label: "Assignment", bgColor: "bg-amber-100", textColor: "text-amber-700" },
  team: { label: "Team", bgColor: "bg-purple-100", textColor: "text-purple-700" },
  assessment: { label: "Assessment", bgColor: "bg-indigo-100", textColor: "text-indigo-700" },
};

export function NotificationsDropdown({
  children,
  isOpen,
  onOpenChange,
  notifications,
  unreadCount,
  isLoading,
  error,
  announcement,
  onMarkAsRead,
  onMarkAllAsRead,
}: NotificationsDropdownProps) {
  const getEventTypeStyle = (eventType: string) => {
    return eventTypeLabels[eventType] || { label: eventType, bgColor: "bg-slate-100", textColor: "text-slate-700" };
  };


  return (
    <Popover.Root open={isOpen} onOpenChange={onOpenChange}>
      <Popover.Trigger asChild>{children}</Popover.Trigger>
      <span role="status" aria-live="polite" className="sr-only">
        {announcement}
      </span>
      <Popover.Portal>
        <Popover.Content
          align="end"
          side="bottom"
          sideOffset={8}
          collisionPadding={8}
          className="z-50 flex max-h-[min(24rem,70dvh)] w-[calc(100vw-1rem)] flex-col rounded-xl border border-slate-200 bg-white shadow-[0_12px_28px_rgba(15,23,42,0.2)] outline-none sm:w-96"
        >
          {/* Header */}
          <div className="flex items-center justify-between border-b border-slate-100 bg-white px-4 py-3 flex-shrink-0">
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-semibold text-slate-900">Notifications</h2>
              {unreadCount > 0 && (
                <span className="inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-blue-600 px-1 text-xs font-bold text-white">
                  {unreadCount > 99 ? "99+" : unreadCount}
                </span>
              )}
            </div>
            <Popover.Close
              className="rounded-lg p-1 text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-600"
              aria-label="Close notifications"
            >
              <X className="h-4 w-4" />
            </Popover.Close>
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
              <ul className="divide-y divide-slate-100">
                {notifications.map((notification) => {
                  const isUnread = !notification.read_at;
                  const style = getEventTypeStyle(notification.event_type);
                  return (
                    <li
                      key={notification.id}
                      className={`transition-colors hover:bg-slate-50 ${isUnread ? "bg-blue-50" : "bg-white"}`}
                    >
                      <button
                        type="button"
                        onClick={() => void onMarkAsRead(notification.id)}
                        className="flex w-full items-start gap-3 px-4 py-3 text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-blue-500"
                      >
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 mb-1">
                            {isUnread && <span className="sr-only">Unread: </span>}
                            <h3
                              className={`text-xs truncate ${
                                isUnread ? "font-semibold text-slate-900" : "font-normal text-slate-500"
                              }`}
                            >
                              {notification.title}
                            </h3>
                            <span
                              className={`text-xs font-medium px-1.5 py-0.5 rounded-full whitespace-nowrap ${style.bgColor} ${style.textColor}`}
                            >
                              {style.label}
                            </span>
                          </div>
                          <p
                            className={`text-sm leading-5 line-clamp-2 ${
                              isUnread ? "text-slate-600" : "text-slate-500"
                            }`}
                          >
                            {notification.message}
                          </p>
                          <span className="block text-xs text-slate-400 mt-1">
                            {new Date(notification.created_at).toLocaleString()}
                          </span>
                        </div>
                        {isUnread && (
                          <span
                            aria-hidden="true"
                            className="mt-1.5 h-2 w-2 flex-shrink-0 rounded-full bg-blue-600"
                          />
                        )}
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>

          {/* Footer */}
          {unreadCount > 0 && notifications.length > 0 && (
            <div className="border-t border-slate-100 bg-white px-4 py-2 flex-shrink-0">
              <button
                type="button"
                onClick={() => void onMarkAllAsRead()}
                className="w-full flex items-center justify-center gap-1 text-xs font-medium text-blue-600 hover:text-blue-700 hover:bg-blue-50 rounded-lg px-2 py-1.5 transition-colors"
              >
                <CheckCheck className="h-3 w-3" />
                Mark all as read
              </button>
            </div>
          )}
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}

