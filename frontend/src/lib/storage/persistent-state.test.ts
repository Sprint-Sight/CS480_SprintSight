import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { isString, readPersistentState, usePersistentState, writePersistentState } from "@/lib/storage/persistent-state";

const KEY = "test-key-v1";

describe("persistent state", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("returns the fallback when the key is missing", () => {
    expect(readPersistentState(KEY, "fallback", isString)).toBe("fallback");
  });

  it("returns the stored value when it passes validation", () => {
    window.localStorage.setItem(KEY, JSON.stringify("Fall 2025"));
    expect(readPersistentState(KEY, "", isString)).toBe("Fall 2025");
  });

  it("returns the fallback when the stored value fails validation", () => {
    window.localStorage.setItem(KEY, JSON.stringify(42));
    expect(readPersistentState(KEY, "", isString)).toBe("");
  });

  it("returns the fallback when the stored JSON is corrupt", () => {
    window.localStorage.setItem(KEY, "{not json");
    expect(readPersistentState(KEY, "fallback", isString)).toBe("fallback");
  });

  it("returns the fallback when storage reads throw", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(readPersistentState(KEY, "fallback", isString)).toBe("fallback");
  });

  it("returns false instead of throwing when the write is blocked", () => {
    vi.spyOn(console, "warn").mockImplementation(() => undefined);
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("quota exceeded", "QuotaExceededError");
    });
    expect(writePersistentState(KEY, "value")).toBe(false);
  });

  it("writes the value as JSON on success", () => {
    expect(writePersistentState(KEY, "value")).toBe(true);
    expect(window.localStorage.getItem(KEY)).toBe(JSON.stringify("value"));
  });

  it("persists state changes made through the hook", () => {
    const { result } = renderHook(() => usePersistentState(KEY, "", isString));
    expect(result.current[0]).toBe("");

    act(() => {
      result.current[1]("course-2");
    });

    expect(result.current[0]).toBe("course-2");
    expect(window.localStorage.getItem(KEY)).toBe(JSON.stringify("course-2"));
  });
});
