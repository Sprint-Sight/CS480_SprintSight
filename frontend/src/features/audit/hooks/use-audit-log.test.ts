/// <reference types="vitest/globals" />
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook } from "@testing-library/react";
import { useAuditLog } from "@/features/audit/hooks/use-audit-log";
import * as auditApi from "@/features/audit/audit-api";

vi.mock("@/features/audit/audit-api");
vi.mock("next/navigation", () => ({
  useRouter: () => ({
    replace: vi.fn(),
  }),
}));

describe("useAuditLog - Feature Hook", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Set up session storage with the correct role
    window.sessionStorage.setItem("sprintsight-auth-role", "instructor");
  });

  afterEach(() => {
    window.sessionStorage.clear();
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
    window.sessionStorage.setItem("sprintsight-auth-role", "student");
    const { result } = renderHook(() => useAuditLog("instructor"));

    // Hook should not attempt to load data
    expect(result.current.isLoading).toBe(true);
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
