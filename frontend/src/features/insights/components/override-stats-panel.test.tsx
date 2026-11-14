/// <reference types="vitest/globals" />
import "@testing-library/jest-dom";
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { OverrideStatsView } from "@/features/insights/components/override-stats-panel";
import type { OverrideStats } from "@/features/insights/types";

const stats: OverrideStats = {
  reports: 4,
  reportsOverridden: 3,
  overrideRate: 0.75,
  reportsWithChanges: 2,
  byDimension: [
    {
      dimension: "requirements",
      overridesSaved: 3,
      changed: 2,
      changeRate: 0.667,
      meanAdjustment: -1.5,
      meanAbsAdjustment: 1.5,
      direction: "lowered",
    },
    {
      dimension: "cicd",
      overridesSaved: 3,
      changed: 0,
      changeRate: 0,
      meanAdjustment: null,
      meanAbsAdjustment: null,
      direction: null,
    },
  ],
  notice:
    "Overrides are not blind: the instructor saw the AI score first. They are not a measure of AI accuracy.",
};

describe("OverrideStatsView", () => {
  it("shows override rate and adjustments with the not-accuracy notice", () => {
    render(<OverrideStatsView stats={stats} />);
    expect(screen.getByText(/3 of 4 reports overridden \(75%\)/)).toBeInTheDocument();
    expect(screen.getByText("-1.50")).toBeInTheDocument();
    expect(screen.getByText("lowered")).toBeInTheDocument();
    expect(screen.getByText(/not a measure of AI accuracy/)).toBeInTheDocument();
  });

  it("never presents agreement or accuracy figures", () => {
    render(<OverrideStatsView stats={stats} />);
    expect(screen.queryByText(/within 1/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/exact match/i)).not.toBeInTheDocument();
  });
});
