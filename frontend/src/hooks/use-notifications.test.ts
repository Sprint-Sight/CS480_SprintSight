/// <reference types="vitest/globals" />
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { apiRequest } from "@/lib/api/client";
import { useNotifications, type DashboardNotification } from "@/hooks/use-notifications";

vi.mock("@/lib/api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/client")>()),
  apiRequest: vi.fn(),
}));

vi.mock("@/lib/auth/session", () => ({
  getSessionToken: () => "test-token",
}));

const makeNotification = (id: string): DashboardNotification => ({
  id,
  event_type: "info",
  title: `Title ${id}`,
  message: "message",
  created_at: "2024-01-01T00:00:00Z",
  read_at: null,
});

describe("useNotifications.markAllAsRead", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("sends one PATCH per unread notification and clears the list on success", async () => {
    const mockedRequest = vi.mocked(apiRequest);
    mockedRequest.mockImplementation(async (path: string) => {
      if (path === "/notifications") {
        return { notifications: [makeNotification("a"), makeNotification("b")], unread_count: 2 };
      }
      return {};
    });

    const { result, unmount } = renderHook(() => useNotifications());
    await waitFor(() => expect(result.current.notifications).toHaveLength(2));

    await act(async () => {
      await result.current.markAllAsRead();
    });

    const patchCalls = mockedRequest.mock.calls.filter(([, init]) => init?.method === "PATCH");
    expect(patchCalls).toHaveLength(2);
    expect(result.current.notifications).toHaveLength(0);
    expect(result.current.unreadCount).toBe(0);
    unmount();
  });

  it("restores only the notifications whose PATCH failed", async () => {
    const mockedRequest = vi.mocked(apiRequest);
    mockedRequest.mockImplementation(async (path: string, init?: RequestInit) => {
      if (path === "/notifications") {
        return { notifications: [makeNotification("a"), makeNotification("b")], unread_count: 2 };
      }
      if (init?.method === "PATCH" && path === "/notifications/b/read") {
        throw new Error("network down");
      }
      return {};
    });
    vi.spyOn(console, "error").mockImplementation(() => undefined);

    const { result, unmount } = renderHook(() => useNotifications());
    await waitFor(() => expect(result.current.notifications).toHaveLength(2));

    await act(async () => {
      await result.current.markAllAsRead();
    });

    expect(result.current.notifications.map((n) => n.id)).toEqual(["b"]);
    expect(result.current.unreadCount).toBe(1);
    unmount();
  });
});
