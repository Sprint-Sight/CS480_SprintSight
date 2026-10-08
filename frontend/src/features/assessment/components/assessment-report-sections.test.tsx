/// <reference types="vitest/globals" />
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AssessmentFeedbackSections } from "@/features/assessment/components/assessment-report-sections";
import type { SprintAssessmentReport } from "@/features/assessment/types";

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
});