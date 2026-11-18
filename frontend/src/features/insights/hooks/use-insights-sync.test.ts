/// <reference types="vitest/globals" />
import { describe, it, expect } from "vitest";
import { SYNC_POLL_MS, overrideSyncRefetchInterval } from "@/features/insights/hooks/use-insights";

describe("overrideSyncRefetchInterval", () => {
  it("polls every 10 s while any override is pending", () => {
    expect(SYNC_POLL_MS).toBe(10_000);
    expect(overrideSyncRefetchInterval(["synced", "pending", null])).toBe(10_000);
  });

  it("stops once nothing is pending", () => {
    expect(
      overrideSyncRefetchInterval(["synced", "failed", "no_trace", "not_needed", null]),
    ).toBe(false);
    expect(overrideSyncRefetchInterval([])).toBe(false);
  });
});
