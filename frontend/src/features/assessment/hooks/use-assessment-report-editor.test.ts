/// <reference types="vitest/globals" />
import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  patchAssessmentReport,
  type BackendAssessmentReport,
} from "@/features/assessment/assessment-api";
import { useAssessmentReportEditor } from "@/features/assessment/hooks/use-assessment-report-editor";
import type { SprintAssessmentReport } from "@/features/assessment/types";

vi.mock("@/features/assessment/assessment-api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/features/assessment/assessment-api")>();
  return { ...actual, patchAssessmentReport: vi.fn() };
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
  overallSummary: "Summary",
  rubricScores: [
    { categoryKey: "requirements", category: "Requirements", score: 80, justification: "Requirements feedback." },
    { categoryKey: "code_quality", category: "Code Quality", score: 80, justification: "Quality feedback." },
    { categoryKey: "documentation", category: "Documentation", score: 80, justification: "Documentation feedback." },
    { categoryKey: "collaboration", category: "Collaboration", score: 80, justification: "Collaboration feedback." },
    { categoryKey: "cicd", category: "CI/CD", score: 10, justification: "CI/CD feedback.", evidenceCitations: ["commit abc"] },
  ],
  strengths: ["Original strength"],
  weaknesses: ["Original weakness"],
  recommendations: ["Original recommendation"],
  narrativeFeedback: [],
};

const backendReport: BackendAssessmentReport = {
  report_id: "rpt-123",
  project_id: "project-1",
  sprint_id: "sprint-1",
  generated_at: "2026-01-01T00:00:00Z",
  override: false,
  team_score: { score: 80, rationale: "Summary" },
  rubric_scores: {
    cicd: { score: 1, justification: "CI/CD feedback.", evidence_citations: ["commit abc"] },
  },
  strengths: ["Original strength"],
  weaknesses: ["Original weakness"],
  recommendations: ["Original recommendation"],
  requirements_score: 80,
  code_quality_score: 80,
  documentation_score: 80,
  collaboration_score: 80,
  requirements_justification: "Requirements feedback.",
  code_quality_justification: "Quality feedback.",
  documentation_justification: "Documentation feedback.",
  collaboration_justification: "Collaboration feedback.",
};

describe("useAssessmentReportEditor", () => {
  afterEach(() => vi.clearAllMocks());

  it("sends edits and accepts the updated report returned by PATCH", async () => {
    const savedReport: BackendAssessmentReport = {
      ...backendReport,
      override: true,
      strengths: ["Updated strength"],
      weaknesses: ["Updated weakness"],
      recommendations: ["Updated recommendation"],
      rubric_scores: {
        cicd: { score: 7, justification: "Updated CI/CD feedback.", evidence_citations: ["commit abc"] },
      },
    };
    vi.mocked(patchAssessmentReport).mockResolvedValue(savedReport);
    const onSaved = vi.fn();
    const { result } = renderHook(() =>
      useAssessmentReportEditor({ report, backendReport, onSaved }),
    );

    act(() => {
      result.current.beginEditing();
      result.current.updateRubricScore("cicd", {
        score: 70,
        justification: "Updated CI/CD feedback.",
      });
      result.current.updateSummary("strengths", "Updated strength");
      result.current.updateSummary("weaknesses", "Updated weakness");
      result.current.updateSummary("recommendations", "Updated recommendation");
    });
    expect(result.current.hasChanges).toBe(true);

    await act(async () => {
      await result.current.saveChanges();
    });

    expect(patchAssessmentReport).toHaveBeenCalledWith("rpt-123", expect.objectContaining({
      rubric_scores: {
        cicd: { score: 7, justification: "Updated CI/CD feedback.", evidence_citations: ["commit abc"] },
      },
      strengths: ["Updated strength"],
      weaknesses: ["Updated weakness"],
      recommendations: ["Updated recommendation"],
    }));
    expect(onSaved).toHaveBeenCalledWith(savedReport);
    expect(result.current.isEditing).toBe(false);
    expect(result.current.saveMessage).toBe("Assessment report changes saved.");
  });
});
