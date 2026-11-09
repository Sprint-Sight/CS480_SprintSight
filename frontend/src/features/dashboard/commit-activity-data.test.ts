/// <reference types="vitest/globals" />
import { describe, it, expect } from "vitest";
import {
  describeCommitActivity,
  groupCommitsByDay,
} from "@/features/dashboard/commit-activity-data";

// Local noon avoids timezone edges when the ISO string is parsed back.
const at = (year: number, monthIndex: number, day: number) =>
  new Date(year, monthIndex, day, 12).toISOString();

describe("groupCommitsByDay", () => {
  it("counts commits made on the same local day", () => {
    const days = groupCommitsByDay([
      { timestamp: at(2024, 10, 6) },
      { timestamp: new Date(2024, 10, 6, 18).toISOString() },
      { timestamp: at(2024, 10, 7) },
    ]);
    expect(days.map((day) => [day.key, day.commits])).toEqual([
      ["2024-11-06", 2],
      ["2024-11-07", 1],
    ]);
  });

  it("keeps the same month and day from different years separate", () => {
    const days = groupCommitsByDay([
      { timestamp: at(2025, 0, 5) },
      { timestamp: at(2024, 0, 5) },
    ]);
    expect(days.map((day) => day.key)).toEqual(["2024-01-05", "2025-01-05"]);
    expect(days[0].name).toContain("2024");
    expect(days[1].name).toContain("2025");
  });

  it("sorts chronologically regardless of input order", () => {
    const days = groupCommitsByDay([
      { timestamp: at(2024, 11, 1) },
      { timestamp: at(2023, 11, 31) },
      { timestamp: at(2024, 0, 15) },
    ]);
    expect(days.map((day) => day.key)).toEqual(["2023-12-31", "2024-01-15", "2024-12-01"]);
  });

  it("skips timestamps that cannot be parsed", () => {
    const days = groupCommitsByDay([{ timestamp: "not-a-date" }, { timestamp: at(2024, 2, 3) }]);
    expect(days).toHaveLength(1);
    expect(days[0].key).toBe("2024-03-03");
  });

  it("returns an empty list when there are no commits", () => {
    expect(groupCommitsByDay([])).toEqual([]);
  });
});

describe("describeCommitActivity", () => {
  it("summarises the total and date range", () => {
    const days = groupCommitsByDay([
      { timestamp: at(2024, 10, 6) },
      { timestamp: at(2024, 10, 6) },
      { timestamp: at(2024, 10, 8) },
    ]);
    const summary = describeCommitActivity(days);
    expect(summary).toContain("3 commits");
    expect(summary).toContain(days[0].name);
    expect(summary).toContain(days[days.length - 1].name);
  });

  it("reports when there are no commits", () => {
    expect(describeCommitActivity([])).toBe("Commit activity: no commits");
  });
});
