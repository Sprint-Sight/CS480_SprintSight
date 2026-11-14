/// <reference types="vitest/globals" />
import { describe, it, expect } from "vitest";
import { JUDGE_POLL_MS, judgeStatusRefetchInterval } from "@/features/insights/hooks/use-insights";

describe("judgeStatusRefetchInterval", () => {
  it("polls every 10 s only while the judge is open", () => {
    expect(JUDGE_POLL_MS).toBe(10_000);
    expect(judgeStatusRefetchInterval("pending")).toBe(10_000);
    expect(judgeStatusRefetchInterval("unknown")).toBe(10_000);
  });

  it("stops polling once the judge finished, failed or never will", () => {
    for (const status of ["complete", "failed", "stale", "no_trace"] as const) {
      expect(judgeStatusRefetchInterval(status)).toBe(false);
    }
    expect(judgeStatusRefetchInterval(undefined)).toBe(false);
  });
});
