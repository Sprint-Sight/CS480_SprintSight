/// <reference types="vitest/globals" />
import "@testing-library/jest-dom";
import { beforeEach, describe, it, expect, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

const hooks = vi.hoisted(() => ({
  useInsightsConfig: vi.fn(),
  useReveal: vi.fn(),
  useEvidence: vi.fn(),
  useSaveLabels: vi.fn(),
  useJudgeStatus: vi.fn(),
  useTrace: vi.fn(),
  usePromptDetail: vi.fn(),
}));
vi.mock("@/features/insights/hooks/use-insights", () => hooks);
vi.mock("@/features/insights/components/reveal-report", () => ({
  RevealReport: ({
    judgeStatus,
    onOpenPrompt,
  }: {
    judgeStatus: string;
    onOpenPrompt: (name: string) => void;
  }) => (
    <>
      <p>reveal report: {judgeStatus}</p>
      <button onClick={() => onOpenPrompt("Evaluate_Scope")}>open prompt</button>
    </>
  ),
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
    hooks.usePromptDetail.mockReturnValue({ isLoading: false, isError: false, data: undefined });
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

  it("fetches a prompt's detail only after that prompt is opened", () => {
    const reveal = {
      teamName: "Team Kiwi",
      courseCode: "CS480",
      sprintId: "S2",
      judgeStatus: "pending",
      dimensions: [],
    };
    hooks.useReveal.mockReturnValue({ isLoading: false, isSuccess: true, error: null, data: reveal });
    hooks.useJudgeStatus.mockReturnValue({ data: undefined });
    hooks.useTrace.mockReturnValue({ data: undefined });
    render(<ReportInsightsContent reportId="r-1" />);
    expect(hooks.usePromptDetail).toHaveBeenLastCalledWith("r-1", "", false);

    fireEvent.click(screen.getByRole("button", { name: "open prompt" }));
    expect(hooks.usePromptDetail).toHaveBeenLastCalledWith("r-1", "Evaluate_Scope", true);
  });
});
