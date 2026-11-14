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
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

import {
  LOCKED_MESSAGE,
  ReportInsightsContent,
} from "@/features/insights/components/report-insights-content";

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
});
