/// <reference types="vitest/globals" />
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { loginUser, restoreSession, startSession } from "@/features/auth/login-api";
import { getSession, setSession } from "@/lib/auth/session";

const profile = {
  id: "u7",
  email: "prof@example.com",
  full_name: "Prof Seven",
  role: "instructor",
};

function respondWith(body: unknown, status = 200) {
  const fetchMock = vi.fn(
    async () =>
      new Response(JSON.stringify(body), {
        status,
        headers: { "Content-Type": "application/json" },
      }),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("auth session helpers", () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.sessionStorage.clear();
  });

  afterEach(() => vi.unstubAllGlobals());

  it("startSession stores the token with the profile from /auth/me", async () => {
    const fetchMock = respondWith(profile);

    await startSession("fresh-token");

    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toMatch(/\/auth\/me$/);
    expect(new Headers(init.headers).get("Authorization")).toBe("Bearer fresh-token");
    expect(getSession()).toEqual({
      token: "fresh-token",
      user: { id: "u7", role: "instructor", email: "prof@example.com", fullName: "Prof Seven" },
    });
  });

  it("restoreSession loads the user for a token that has none instead of forcing a login", async () => {
    setSession({ token: "kept-token", user: null });
    respondWith(profile);

    const restored = await restoreSession();

    expect(restored?.user?.email).toBe("prof@example.com");
    expect(getSession()?.user?.fullName).toBe("Prof Seven");
  });

  it("restoreSession returns a complete session without a request, and null when signed out", async () => {
    const fetchMock = respondWith(profile);
    await expect(restoreSession()).resolves.toBeNull();

    setSession({
      token: "t",
      user: { id: "u1", role: "student", email: "s@example.com", fullName: "S" },
    });
    await expect(restoreSession()).resolves.toMatchObject({ token: "t" });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("loginUser surfaces the backend's message for bad credentials", async () => {
    respondWith({ error: { code: "http_401", message: "Invalid email or password." } }, 401);
    await expect(loginUser("a@b.c", "wrong")).rejects.toMatchObject({
      status: 401,
      message: "Invalid email or password.",
    });
  });
});
