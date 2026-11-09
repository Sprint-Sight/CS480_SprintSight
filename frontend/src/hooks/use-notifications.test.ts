/// <reference types="vitest/globals" />
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { apiRequest } from "@/lib/api/client";
import { useNotifications, type DashboardNotification } from "@/hooks/use-notifications";

const POLL_INTERVAL_MS = 30_000;

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

  it("sends one PATCH per unread notification and marks each read in place", async () => {
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
    expect(result.current.notifications).toHaveLength(2);
    expect(result.current.notifications.every((n) => n.read_at !== null)).toBe(true);
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

    expect(result.current.notifications.map((n) => [n.id, n.read_at !== null])).toEqual([
      ["a", true],
      ["b", false],
    ]);
    expect(result.current.unreadCount).toBe(1);
    unmount();
  });
});

describe("useNotifications.markAsRead", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("keeps a read notification in the list and does not send a second PATCH", async () => {
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
      await result.current.markAsRead("a");
    });
    await act(async () => {
      await result.current.markAsRead("a");
    });

    const patchCalls = mockedRequest.mock.calls.filter(([, init]) => init?.method === "PATCH");
    expect(patchCalls).toHaveLength(1);
    expect(result.current.notifications).toHaveLength(2);
    expect(result.current.notifications[0].read_at).not.toBeNull();
    expect(result.current.unreadCount).toBe(1);
    unmount();
  });
});

describe("useNotifications polling and announcements", () => {
  let visibilityState: DocumentVisibilityState = "visible";

  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
    visibilityState = "visible";
    Object.defineProperty(document, "visibilityState", {
      configurable: true,
      get: () => visibilityState,
    });
  });

  afterEach(() => {
    vi.useRealTimers();
    delete (document as unknown as { visibilityState?: unknown }).visibilityState;
  });

  it("pauses polling while the tab is hidden and refreshes when it becomes visible", async () => {
    const mockedRequest = vi.mocked(apiRequest);
    mockedRequest.mockResolvedValue({ notifications: [], unread_count: 0 });

    const { unmount } = renderHook(() => useNotifications());
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(mockedRequest).toHaveBeenCalledTimes(1);

    visibilityState = "hidden";
    await act(async () => {
      document.dispatchEvent(new Event("visibilitychange"));
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 2);
    });
    expect(mockedRequest).toHaveBeenCalledTimes(1);

    visibilityState = "visible";
    await act(async () => {
      document.dispatchEvent(new Event("visibilitychange"));
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(mockedRequest).toHaveBeenCalledTimes(2);
    unmount();
  });

  it("announces only notifications that arrive after the first load", async () => {
    const mockedRequest = vi.mocked(apiRequest);
    let list = [makeNotification("a")];
    mockedRequest.mockImplementation(async (path: string) => {
      if (path === "/notifications") {
        return { notifications: list, unread_count: list.length };
      }
      return {};
    });

    const { result, unmount } = renderHook(() => useNotifications());
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(result.current.announcement).toBe("");

    list = [makeNotification("a"), makeNotification("b")];
    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);
    });
    expect(result.current.announcement).toBe("1 new notification");
    unmount();
  });
});
