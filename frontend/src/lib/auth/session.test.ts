/// <reference types="vitest/globals" />
import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  SESSION_STORAGE_KEY,
  getSession,
  getSessionToken,
  setSession,
  signOut,
  subscribeToSession,
  useSession,
} from "@/lib/auth/session";

const instructor = {
  token: "token-abc",
  user: {
    id: "u1",
    role: "instructor" as const,
    email: "prof@example.com",
    fullName: "Prof Example",
  },
};

describe("session store", () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.sessionStorage.clear();
  });

  it("stores the token and user under a single localStorage key", () => {
    expect(getSession()).toBeNull();
    setSession(instructor);

    expect(JSON.parse(window.localStorage.getItem(SESSION_STORAGE_KEY) ?? "null")).toEqual(
      instructor,
    );
    expect(getSessionToken()).toBe("token-abc");
    // Stable reference while unchanged (required by useSyncExternalStore).
    expect(getSession()).toBe(getSession());
  });

  it("migrates an older login (token + per-tab identity keys) and removes the old keys", () => {
    window.localStorage.setItem("sprintsight-access-token", "legacy-token");
    window.sessionStorage.setItem("sprintsight-access-token", "legacy-token");
    window.sessionStorage.setItem("sprintsight-auth-role", "student");
    window.sessionStorage.setItem("sprintsight-auth-email", "kid@example.com");
    window.sessionStorage.setItem("sprintsight-auth-name", "Kid");

    expect(getSession()).toEqual({
      token: "legacy-token",
      user: { id: "", role: "student", email: "kid@example.com", fullName: "Kid" },
    });
    expect(window.localStorage.getItem("sprintsight-access-token")).toBeNull();
    expect(window.sessionStorage.getItem("sprintsight-auth-role")).toBeNull();
  });

  it("keeps a migrated token without a user so it can be restored from /auth/me", () => {
    window.localStorage.setItem("sprintsight-access-token", "legacy-token");
    expect(getSession()).toEqual({ token: "legacy-token", user: null });
  });

  it("ignores corrupted or incomplete stored values", () => {
    window.localStorage.setItem(SESSION_STORAGE_KEY, "{not json");
    expect(getSession()).toBeNull();
    window.localStorage.setItem(
      SESSION_STORAGE_KEY,
      JSON.stringify({ token: "t", user: { role: "superuser" } }),
    );
    expect(getSession()).toEqual({ token: "t", user: null });
  });

  it("signOut clears everything and notifies subscribers", () => {
    setSession(instructor);
    window.sessionStorage.setItem("sprintsight-auth-role", "instructor");
    const listener = vi.fn();
    const unsubscribe = subscribeToSession(listener);

    signOut();

    expect(getSession()).toBeNull();
    expect(window.sessionStorage.getItem("sprintsight-auth-role")).toBeNull();
    expect(listener).toHaveBeenCalledTimes(1);
    unsubscribe();
  });

  it("notifies subscribers when another tab changes the session", () => {
    const listener = vi.fn();
    const unsubscribe = subscribeToSession(listener);

    window.dispatchEvent(new StorageEvent("storage", { key: SESSION_STORAGE_KEY }));
    window.dispatchEvent(new StorageEvent("storage", { key: "unrelated" }));

    expect(listener).toHaveBeenCalledTimes(1);
    unsubscribe();
  });

  it("useSession re-renders on sign-in and sign-out", () => {
    const { result } = renderHook(() => useSession());
    expect(result.current).toBeNull();

    act(() => setSession(instructor));
    expect(result.current?.user?.role).toBe("instructor");

    act(() => signOut());
    expect(result.current).toBeNull();
  });
});
