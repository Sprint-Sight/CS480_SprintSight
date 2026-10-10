/// <reference types="vitest/globals" />
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AssessmentFeedbackSections } from "@/features/assessment/components/assessment-report-sections";
import type { SprintAssessmentReport } from "@/features/assessment/types";

Object.defineProperty(HTMLTextAreaElement.prototype, "scrollHeight", {
  configurable: true,
  get() {
    return this.value.length * 2;
  },
});

const report: SprintAssessmentReport = {
  reportId: "rpt-123",
  projectId: "project-1",
  sprintId: "sprint-1",
  sprintLabel: "Sprint 1",
  teamLabel: "Team",
  projectLabel: "Project",
  generatedAt: "",
  overallScore: 80,
  overallGrade: "B",
  overallSummary: "Overall summary",
  rubricScores: [
    { categoryKey: "requirements", category: "Requirements", score: 80, justification: "Current requirements note." },
    { categoryKey: "code_quality", category: "Code Quality", score: 70, justification: "Current quality note.", evidenceCitations: ["commit abc"] },
    { categoryKey: "cicd", category: "CI/CD", score: 10, justification: "CI/CD note." },
    { categoryKey: "testing", category: "Testing", score: 100, justification: "Testing note." },
  ],
  strengths: ["Strong testing"],
  weaknesses: ["Improve documentation"],
  recommendations: ["Add a deployment guide"],
  narrativeFeedback: [],
};

describe("AssessmentFeedbackSections editing", () => {
  it("allows edits for endpoint-supported rubric dimensions and keeps citations read-only", () => {
    const onRubricScoreChange = vi.fn();
    render(<AssessmentFeedbackSections report={report} editMode onRubricScoreChange={onRubricScoreChange} />);

    fireEvent.change(screen.getByLabelText("Requirements score"), { target: { value: "85" } });
    fireEvent.change(screen.getByLabelText("Requirements feedback"), { target: { value: "Updated rationale." } });

    expect(onRubricScoreChange).toHaveBeenNthCalledWith(1, "requirements", { score: 85 });
    expect(onRubricScoreChange).toHaveBeenNthCalledWith(2, "requirements", { justification: "Updated rationale." });
    expect(screen.getByText("Evidence: commit abc")).toBeInTheDocument();
    expect(screen.getByLabelText("CI/CD score")).toBeDisabled();
    expect(screen.getByLabelText("Testing feedback")).toBeDisabled();
    expect(screen.getAllByText(/this category cannot be persisted/i)).toHaveLength(2);
  });

  it("shows summary fields as disabled because the existing endpoint cannot save them", () => {
    render(<AssessmentFeedbackSections report={report} editMode />);

    expect(screen.getByLabelText("Strengths")).toBeDisabled();
    expect(screen.getByLabelText("Weaknesses")).toBeDisabled();
    expect(screen.getByLabelText("Recommendations")).toBeDisabled();
  });

  it("sizes editable feedback for its initial content and after edits", async () => {
    const initialFeedback = "Long assessment feedback. ".repeat(12);
    const updatedFeedback = "Updated assessment feedback with additional detail. ".repeat(15);
    const initialReport = {
      ...report,
      rubricScores: report.rubricScores.map((score) =>
        score.categoryKey === "requirements"
          ? { ...score, justification: initialFeedback }
          : score,
      ),
    };
    const onRubricScoreChange = vi.fn();
    const view = render(
      <AssessmentFeedbackSections report={initialReport} editMode onRubricScoreChange={onRubricScoreChange} />,
    );
    const feedback = screen.getByLabelText("Requirements feedback") as HTMLTextAreaElement;

    await waitFor(() => expect(feedback).toHaveStyle({ height: `${initialFeedback.length * 2}px` }));

    fireEvent.change(feedback, { target: { value: updatedFeedback } });
    expect(onRubricScoreChange).toHaveBeenCalledWith("requirements", { justification: updatedFeedback });

    const updatedReport = {
      ...initialReport,
      rubricScores: initialReport.rubricScores.map((score) =>
        score.categoryKey === "requirements"
          ? { ...score, justification: updatedFeedback }
          : score,
      ),
    };
    view.rerender(
      <AssessmentFeedbackSections report={updatedReport} editMode onRubricScoreChange={onRubricScoreChange} />,
    );

    await waitFor(() => expect(feedback).toHaveStyle({ height: `${updatedFeedback.length * 2}px` }));
    expect(feedback).toHaveStyle({ overflowY: "hidden" });
  });

  it("auto-sizes long read-only rubric feedback without enabling editing", async () => {
    const longFeedback = "Read-only assessment feedback. ".repeat(14);
    const longReport = {
      ...report,
      rubricScores: report.rubricScores.map((score) =>
        score.categoryKey === "cicd" ? { ...score, justification: longFeedback } : score,
      ),
    };
    render(<AssessmentFeedbackSections report={longReport} editMode />);

    const feedback = screen.getByLabelText("CI/CD feedback") as HTMLTextAreaElement;
    expect(feedback).toBeDisabled();
    await waitFor(() => expect(feedback).toHaveStyle({ height: `${longFeedback.length * 2}px` }));
  });

  it("renders long read-only feedback in full for student report view", () => {
    const longFeedback = "Full read-only assessment feedback. ".repeat(20);
    const longReport = {
      ...report,
      rubricScores: report.rubricScores.map((score) =>
        score.categoryKey === "requirements" ? { ...score, justification: longFeedback } : score,
      ),
    };
    render(<AssessmentFeedbackSections report={longReport} />);

    const feedback = screen.getByText(
      (_, element) => element?.tagName === "P" && element.textContent === longFeedback,
    );
    expect(feedback).toBeInTheDocument();
  });
});