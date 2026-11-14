/// <reference types="vitest/globals" />
import "@testing-library/jest-dom";
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { RunsTable, UNLOCKS_AFTER_OVERRIDE } from "@/features/insights/components/runs-table";
import type { RunItem } from "@/features/insights/types";

const run = (patch: Partial<RunItem> = {}): RunItem => ({
  reportId: "r-1",
  teamName: "Team A",
  courseId: "c-1",
  courseCode: "CS480",
  section: "G1",
  sprintId: "sprint-1",
  modelName: "sprintsight-qwen",
  generatedAt: "2026-11-12T10:00:00Z",
  labelsDone: 0,
  judgeStatus: "complete",
  aiScore: null,
  aiScoreHidden: true,
  insightsUnlocked: false,
  overridden: false,
  citationCheck: null,
  ...patch,
});

describe("RunsTable (blind labelling)", () => {
  it("hides the AI score until all six dimensions are labelled", () => {
    render(<RunsTable items={[run()]} />);
    expect(screen.getAllByText("Hidden until labelled").length).toBeGreaterThan(0);
    expect(screen.getByText("0 of 6")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Label" })).toBeInTheDocument();
  });

  it("shows the score and results link once labelled", () => {
    render(
      <RunsTable
        items={[
          run({
            labelsDone: 6,
            aiScore: 6.8,
            aiScoreHidden: false,
            insightsUnlocked: true,
            citationCheck: { status: "flagged", groundedRate: 0.31 },
          }),
        ]}
      />,
    );
    expect(screen.getByText("6.8 / 10")).toBeInTheDocument();
    expect(screen.getByText(/31% grounded/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View insights" })).toBeInTheDocument();
  });
});

describe("RunsTable (override gate)", () => {
  it("shows the AI score but keeps the judge checks locked before an override", () => {
    render(
      <RunsTable
        mode="override_gate"
        items={[run({ aiScore: 7.2, aiScoreHidden: false, insightsUnlocked: false })]}
      />,
    );
    expect(screen.getByText("7.2 / 10")).toBeInTheDocument();
    expect(screen.queryByText("Hidden until labelled")).not.toBeInTheDocument();
    expect(screen.getByText(UNLOCKS_AFTER_OVERRIDE)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Override to unlock" })).toHaveAttribute(
      "href",
      "/assessment-report",
    );
  });

  it("unlocks the citation check and links to the insights after an override", () => {
    render(
      <RunsTable
        mode="override_gate"
        items={[
          run({
            aiScore: 7.2,
            aiScoreHidden: false,
            insightsUnlocked: true,
            overridden: true,
            citationCheck: { status: "ok", groundedRate: 0.9 },
          }),
        ]}
      />,
    );
    expect(screen.queryByText(UNLOCKS_AFTER_OVERRIDE)).not.toBeInTheDocument();
    expect(screen.getByText(/90% grounded/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View insights" })).toHaveAttribute(
      "href",
      "/insights/reports/r-1",
    );
  });
});
