/// <reference types="vitest/globals" />
import { describe, it, expect } from "vitest";
import {
  describeMemberChart,
  describeWorkloadChart,
  getCategoryAxisWidth,
} from "@/features/collaboration/chart-layout";
import type { MemberCommitMetric, WorkloadSlice } from "@/features/collaboration/types";

const members: MemberCommitMetric[] = [
  { id: "1", student_id: null, member: "Ada", commits: 4, linesChanged: 120 },
  { id: "2", student_id: null, member: "Grace Hopper", commits: 9, linesChanged: 40 },
];

describe("getCategoryAxisWidth", () => {
  it("uses the minimum width for short names", () => {
    expect(getCategoryAxisWidth(["Al"])).toBe(72);
  });

  it("grows with the longest label", () => {
    expect(getCategoryAxisWidth(["Ada", "Grace Hopper Lovelace"])).toBeGreaterThan(120);
  });

  it("caps the width so the chart keeps room for bars", () => {
    expect(getCategoryAxisWidth(["x".repeat(100)])).toBe(200);
  });

  it("returns the minimum width when there are no labels", () => {
    expect(getCategoryAxisWidth([])).toBe(72);
  });
});

describe("describeMemberChart", () => {
  it("names the top contributor for the selected metric", () => {
    expect(describeMemberChart("Commits", members, "commits")).toBe(
      "Commits by member for 2 contributors. Highest: Grace Hopper with 9.",
    );
  });

  it("uses the lines-changed metric when selected", () => {
    expect(describeMemberChart("Lines changed", members, "linesChanged")).toContain("Highest: Ada with 120.");
  });

  it("reports when there is no data", () => {
    expect(describeMemberChart("Commits", [], "commits")).toBe("Commits by member: no data");
  });
});

describe("describeWorkloadChart", () => {
  it("lists each slice with its share", () => {
    const slices: WorkloadSlice[] = [
      { id: "a", student_id: null, name: "Ada", value: 60, color: "red" },
      { id: "b", student_id: null, name: "Grace", value: 40, color: "blue" },
    ];
    expect(describeWorkloadChart(slices)).toBe("Workload distribution: Ada 60%, Grace 40%.");
  });

  it("reports when there are no tickets", () => {
    expect(describeWorkloadChart([])).toBe("Workload distribution: no Jira ticket data");
  });
});
