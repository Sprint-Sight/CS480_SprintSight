/// <reference types="vitest/globals" />
import "@testing-library/jest-dom";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const hooks = vi.hoisted(() => ({
  useInsightsConfig: vi.fn(),
  useMyCourses: vi.fn(),
  useRuns: vi.fn(),
  useOverrideStats: vi.fn(),
}));
vi.mock("@/features/insights/hooks/use-insights", () => hooks);
vi.mock("@/features/insights/components/runs-table", () => ({ RunsTable: () => <p>runs table</p> }));
vi.mock("@/features/insights/components/run-filters", () => ({ RunFiltersBar: () => null }));
vi.mock("@/features/insights/components/course-cards", () => ({ CourseCards: () => null }));
vi.mock("@/features/insights/components/override-stats-panel", () => ({
  OverrideStatsView: () => <p>override stats</p>,
}));

import { InsightsPageContent } from "@/features/insights/components/insights-page-content";

const runsPage = (total: number) => ({ items: [], total, facets: undefined });

describe("InsightsPageContent", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    hooks.useMyCourses.mockReturnValue({ data: undefined });
    hooks.useRuns.mockReturnValue({ isLoading: false, error: null, data: runsPage(10) });
    hooks.useOverrideStats.mockReturnValue({ isLoading: false, error: null, data: { reports: 1 } });
  });

  it("does not request override statistics in blind_label mode", () => {
    hooks.useInsightsConfig.mockReturnValue({ data: { mode: "blind_label" } });
    render(<InsightsPageContent />);
    expect(hooks.useOverrideStats).toHaveBeenCalledWith(false);
    expect(screen.queryByText("override stats")).not.toBeInTheDocument();
  });

  it("loads override statistics in the container and passes them down in override_gate mode", () => {
    hooks.useInsightsConfig.mockReturnValue({ data: { mode: "override_gate" } });
    render(<InsightsPageContent />);
    expect(hooks.useOverrideStats).toHaveBeenCalledWith(true);
    expect(screen.getByText("override stats")).toBeInTheDocument();
  });

  it("pages through runs with the pagination controls", () => {
    hooks.useInsightsConfig.mockReturnValue({ data: { mode: "blind_label" } });
    hooks.useRuns.mockReturnValue({ isLoading: false, error: null, data: runsPage(60) });
    render(<InsightsPageContent />);
    expect(screen.getByText("Page 1 of 3")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(hooks.useRuns).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2 }));
  });
});
