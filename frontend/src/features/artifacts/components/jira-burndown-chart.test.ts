import { describe, expect, it } from "vitest";

import { buildBurndownChartData } from "./jira-burndown-chart";

describe("buildBurndownChartData", () => {
  it("merges actual and ideal series in chronological order", () => {
    expect(
      buildBurndownChartData({
        sprint_id: "sprint-2",
        total_story_points: 10,
        total_tickets: 2,
        start_date: "2024-10-01",
        end_date: "2024-10-03",
        daily_points: [
          {
            date: "2024-10-02",
            remaining_points: 5,
            completed_tickets: 1,
            completed_points: 5,
          },
        ],
        ideal_line: [
          { date: "2024-10-01", remaining_points: 10 },
          { date: "2024-10-02", remaining_points: 5 },
          { date: "2024-10-03", remaining_points: 0 },
        ],
      }),
    ).toEqual([
      { date: "2024-10-01", actual_remaining: null, ideal_remaining: 10 },
      { date: "2024-10-02", actual_remaining: 5, ideal_remaining: 5 },
      { date: "2024-10-03", actual_remaining: null, ideal_remaining: 0 },
    ]);
  });
});
