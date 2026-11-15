/// <reference types="vitest/globals" />
import "@testing-library/jest-dom";
import { beforeEach, describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";

const hooks = vi.hoisted(() => ({
  useInsightsConfig: vi.fn(),
  useReveal: vi.fn(),
  useEvidence: vi.fn(),
  useSaveLabels: vi.fn(),
  useJudgeStatus: vi.fn(),
  useTrace: vi.fn(),
}));
vi.mock("@/features/insights/hooks/use-insights", () => hooks);
vi.mock("@/features/insights/components/reveal-report", () => ({
  RevealReport: ({ judgeStatus }: { judgeStatus: string }) => <p>reveal report: {judgeStatus}</p>,
}));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

import { LOCKED_MESSAGE } from "@/features/insights/components/insights-locked-notice";
import { ReportInsightsContent } from "@/features/insights/components/report-insights-content";

const httpError = (status: number) => Object.assign(new Error(`http ${status}`), { status });

describe("ReportInsightsContent in override_gate mode", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    hooks.useInsightsConfig.mockReturnValue({ isLoading: false, data: { mode: "override_gate" } });
  });

  it("shows the locked panel with a link to the Assessment Report on a 409", () => {
    hooks.useReveal.mockReturnValue({ isLoading: false, error: httpError(409), data: undefined });
    render(<ReportInsightsContent reportId="r-1" />);
    expect(screen.getByText("AI Insights are locked for this report")).toBeInTheDocument();
    expect(screen.getByText(LOCKED_MESSAGE)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open Assessment Report" })).toHaveAttribute(
      "href",
      "/assessment-report",
    );
    expect(hooks.useEvidence).not.toHaveBeenCalled(); // no blind evidence step in this mode
  });

  it("treats an out-of-scope report like an unknown one (404)", () => {
    hooks.useReveal.mockReturnValue({ isLoading: false, error: httpError(404), data: undefined });
    render(<ReportInsightsContent reportId="r-1" />);
    expect(screen.getByText(/not found, or not in your courses/i)).toBeInTheDocument();
  });

  it("shows the report header and hands the AI results to RevealReport", () => {
    const reveal = { teamName: "Team Kiwi", courseCode: "CS480", sprintId: "S2", judgeStatus: "pending" };
    hooks.useReveal.mockReturnValue({ isLoading: false, isSuccess: true, error: null, data: reveal });
    hooks.useJudgeStatus.mockReturnValue({ data: { judgeStatus: "complete" } });
    hooks.useTrace.mockReturnValue({ data: undefined });
    render(<ReportInsightsContent reportId="r-1" />);
    expect(screen.getByRole("heading", { level: 1, name: "Team Kiwi" })).toBeInTheDocument();
    expect(screen.getByText("CS480 · S2")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "← All runs" })).toHaveAttribute("href", "/insights");
    // The polled judge status wins over the one stored with the report.
    expect(screen.getByText("reveal report: complete")).toBeInTheDocument();
  });
});
