/// <reference types="vitest/globals" />
import { renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ restoreSession: vi.fn(), replace: vi.fn() }));
vi.mock("@/features/auth/login-api", () => ({ restoreSession: mocks.restoreSession }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: mocks.replace }) }));

import { useRequireAdmin } from "@/features/auth/hooks/use-require-admin";

describe("useRequireAdmin", () => {
  beforeEach(() => vi.clearAllMocks());

  it("allows an admin through without redirecting", async () => {
    mocks.restoreSession.mockResolvedValue({ user: { role: "admin" } });
    const { result } = renderHook(() => useRequireAdmin());
    expect(result.current).toBe(false); // nothing renders until the check finishes
    await waitFor(() => expect(result.current).toBe(true));
    expect(mocks.replace).not.toHaveBeenCalled();
  });

  it("sends an instructor to /login and never allows them", async () => {
    mocks.restoreSession.mockResolvedValue({ user: { role: "instructor" } });
    const { result } = renderHook(() => useRequireAdmin());
    await waitFor(() => expect(mocks.replace).toHaveBeenCalledWith("/login"));
    expect(result.current).toBe(false);
  });

  it("sends a signed-out visitor to /login", async () => {
    mocks.restoreSession.mockResolvedValue(null);
    renderHook(() => useRequireAdmin());
    await waitFor(() => expect(mocks.replace).toHaveBeenCalledWith("/login"));
  });
});
