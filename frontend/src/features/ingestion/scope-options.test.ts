import { describe, expect, it } from "vitest";

import { buildSprintOptions, semesterLabel } from "@/features/ingestion/scope-options";

describe("buildSprintOptions", () => {
  it("labels numbered sprints as Sprint N and sorts them numerically", () => {
    expect(buildSprintOptions(["sprint-10", "sprint-2", "sprint-3"])).toEqual([
      { value: "sprint-2", label: "Sprint 2" },
      { value: "sprint-3", label: "Sprint 3" },
      { value: "sprint-10", label: "Sprint 10" },
    ]);
  });

  it("removes duplicate sprint IDs", () => {
    expect(buildSprintOptions(["sprint-1", "sprint-1", "sprint-2"])).toHaveLength(2);
  });

  it("places non-numeric IDs after numbered sprints and keeps their raw value", () => {
    expect(buildSprintOptions(["backlog", "sprint-1"])).toEqual([
      { value: "sprint-1", label: "Sprint 1" },
      { value: "backlog", label: "backlog" },
    ]);
  });

  it("returns an empty list when there are no runs", () => {
    expect(buildSprintOptions([])).toEqual([]);
  });
});

describe("semesterLabel", () => {
  it("joins term and year", () => {
    expect(semesterLabel({ term: "Fall", year: 2025 })).toBe("Fall 2025");
  });
});
