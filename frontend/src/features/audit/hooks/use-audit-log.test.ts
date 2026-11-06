/// <reference types="vitest/globals" />
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { useAuditLog } from "@/features/audit/hooks/use-audit-log";
import * as auditApi from "@/features/audit/audit-api";
import { setSession, signOut, type SessionRole } from "@/lib/auth/session";

// A stable router object, like Next's real useRouter, so effects keyed on it settle.
const { replace, router } = vi.hoisted(() => {
  const replaceMock = vi.fn();
  return { replace: replaceMock, router: { replace: replaceMock } };
});

vi.mock("@/features/audit/audit-api");
vi.mock("next/navigation", () => ({
  useRouter: () => router,
}));

function signInAs(role: SessionRole) {
  setSession({ token: "token", user: { id: "u1", role, email: `${role}@example.com`, fullName: role } });
}

describe("useAuditLog - Feature Hook", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    signInAs("instructor");
  });

  afterEach(() => {
    signOut();
  });

  it("should initialize with loading state and empty records", () => {
    vi.mocked(auditApi.getActionAuditRecords).mockResolvedValue([]);
    vi.mocked(auditApi.getOverrideAuditRecords).mockResolvedValue([]);

    const { result } = renderHook(() => useAuditLog("instructor"));

    expect(result.current.isLoading).toBe(true);
    expect(result.current.actions).toEqual([]);
    expect(result.current.overrides).toEqual([]);
  });

  it("should have refresh function available", () => {
    vi.mocked(auditApi.getActionAuditRecords).mockResolvedValue([]);
    vi.mocked(auditApi.getOverrideAuditRecords).mockResolvedValue([]);

    const { result } = renderHook(() => useAuditLog("instructor"));

    expect(typeof result.current.refresh).toBe("function");
  });

  it("should initialize error messages as empty strings", () => {
    vi.mocked(auditApi.getActionAuditRecords).mockResolvedValue([]);
    vi.mocked(auditApi.getOverrideAuditRecords).mockResolvedValue([]);

    const { result } = renderHook(() => useAuditLog("instructor"));

    expect(result.current.actionsError).toBe("");
    expect(result.current.overridesError).toBe("");
  });

  it("should redirect if session role does not match hook role", () => {
    signInAs("student");
    const { result } = renderHook(() => useAuditLog("instructor"));

    // Hook should not attempt to load data
    expect(result.current.isLoading).toBe(true);
    expect(replace).toHaveBeenCalledWith("/login");
    expect(auditApi.getActionAuditRecords).not.toHaveBeenCalled();
  });

  it("loads records when the session role matches", async () => {
    vi.mocked(auditApi.getActionAuditRecords).mockResolvedValue([]);
    vi.mocked(auditApi.getOverrideAuditRecords).mockResolvedValue([]);

    const { result } = renderHook(() => useAuditLog("instructor"));

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(replace).not.toHaveBeenCalled();
    expect(auditApi.getActionAuditRecords).toHaveBeenCalledTimes(1);
  });

  it("should export proper data structure from hook", () => {
    vi.mocked(auditApi.getActionAuditRecords).mockResolvedValue([]);
    vi.mocked(auditApi.getOverrideAuditRecords).mockResolvedValue([]);

    const { result } = renderHook(() => useAuditLog("instructor"));

    expect(result.current).toHaveProperty("actions");
    expect(result.current).toHaveProperty("overrides");
    expect(result.current).toHaveProperty("actionsError");
    expect(result.current).toHaveProperty("overridesError");
    expect(result.current).toHaveProperty("isLoading");
    expect(result.current).toHaveProperty("refresh");
  });
});
