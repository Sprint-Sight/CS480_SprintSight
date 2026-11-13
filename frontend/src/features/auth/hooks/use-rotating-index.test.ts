/// <reference types="vitest/globals" />
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ROTATION_INTERVAL_MS, useRotatingIndex } from "@/features/auth/hooks/use-rotating-index";

function stubReducedMotion(reduce: boolean) {
  vi.stubGlobal(
    "matchMedia",
    vi.fn((query: string) => ({
      matches: reduce && query.includes("prefers-reduced-motion"),
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })),
  );
}

describe("useRotatingIndex", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("advances every interval and wraps around", () => {
    stubReducedMotion(false);
    const { result } = renderHook(() => useRotatingIndex(3));

    expect(result.current).toBe(0);
    act(() => vi.advanceTimersByTime(ROTATION_INTERVAL_MS));
    expect(result.current).toBe(1);
    act(() => vi.advanceTimersByTime(ROTATION_INTERVAL_MS));
    expect(result.current).toBe(2);
    act(() => vi.advanceTimersByTime(ROTATION_INTERVAL_MS));
    expect(result.current).toBe(0);
  });

  it("stays on the first item when the user prefers reduced motion", () => {
    stubReducedMotion(true);
    const { result } = renderHook(() => useRotatingIndex(3));

    act(() => vi.advanceTimersByTime(ROTATION_INTERVAL_MS * 3));
    expect(result.current).toBe(0);
    expect(vi.getTimerCount()).toBe(0);
  });

  it("clears its timer on unmount", () => {
    stubReducedMotion(false);
    const { unmount } = renderHook(() => useRotatingIndex(3));

    expect(vi.getTimerCount()).toBe(1);
    unmount();
    expect(vi.getTimerCount()).toBe(0);
  });
});
