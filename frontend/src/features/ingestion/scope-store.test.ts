import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  INGESTION_SCOPE_EVENT,
  SCOPE_STORAGE_KEY,
  migrateLegacyScope,
  readScope,
  writeScope,
} from "@/features/ingestion/scope-store";

const LEGACY_KEY = "sprintsight-ingestion-state-v1";

describe("scope-store", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("copies the selection from the legacy blob once and removes the old key", () => {
    window.localStorage.setItem(
      LEGACY_KEY,
      JSON.stringify({ selectedProjectId: "p1", selectedCourseId: "c1", selectedSprintId: "sprint-3", gitBySprint: {} }),
    );

    migrateLegacyScope();

    expect(window.localStorage.getItem(LEGACY_KEY)).toBeNull();
    expect(readScope()).toEqual({ selectedProjectId: "p1", selectedCourseId: "c1", selectedSprintId: "sprint-3" });
  });

  it("does not overwrite an existing v2 scope during migration", () => {
    window.localStorage.setItem(SCOPE_STORAGE_KEY, JSON.stringify({ selectedProjectId: "new" }));
    window.localStorage.setItem(LEGACY_KEY, JSON.stringify({ selectedProjectId: "old" }));

    migrateLegacyScope();

    expect(readScope().selectedProjectId).toBe("new");
    expect(window.localStorage.getItem(LEGACY_KEY)).toBeNull();
  });

  it("falls back to defaults when the stored value is corrupt", () => {
    window.localStorage.setItem(SCOPE_STORAGE_KEY, "{not json");

    expect(readScope()).toEqual({ selectedProjectId: "", selectedCourseId: "", selectedSprintId: "sprint-1" });
  });

  it("merges patches and dispatches the scope event on success", () => {
    const listener = vi.fn();
    window.addEventListener(INGESTION_SCOPE_EVENT, listener);

    writeScope({ selectedProjectId: "p2" });

    expect(readScope().selectedProjectId).toBe("p2");
    expect(listener).toHaveBeenCalledTimes(1);
    window.removeEventListener(INGESTION_SCOPE_EVENT, listener);
  });

  it("does not throw when storage rejects the write", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("quota", "QuotaExceededError");
    });
    vi.spyOn(console, "warn").mockImplementation(() => {});

    expect(() => writeScope({ selectedProjectId: "p3" })).not.toThrow();
  });
});
