/// <reference types="vitest/globals" />
import { describe, expect, it } from "vitest";
import { buildManualAssessmentPatch, type BackendAssessmentReport } from "@/features/assessment/assessment-api";
import { toSprintAssessmentReport } from "@/features/assessment/hooks/use-assessment-report";
import type { SprintAssessmentReport } from "@/features/assessment/types";

const baseReport: SprintAssessmentReport = {
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
    { categoryKey: "requirements", category: "Requirements", score: 90, justification: "Updated requirement justification." },
    { categoryKey: "code_quality", category: "Code Quality", score: 80, justification: "Updated quality justification." },
    { categoryKey: "documentation", category: "Documentation", score: 70, justification: "Updated documentation justification." },
    { categoryKey: "collaboration", category: "Collaboration", score: 60, justification: "Updated collaboration justification." },
    { categoryKey: "cicd", category: "CI/CD", score: 10, justification: "Uneditable CI/CD justification.", evidenceCitations: ["commit abc"] },
  ],
  strengths: ["Strength"],
  weaknesses: ["Weakness"],
  recommendations: ["Recommendation"],
  narrativeFeedback: [],
};

const backendReport: BackendAssessmentReport = {
  report_id: "rpt-123",
  project_id: "project-1",
  sprint_id: "sprint-1",
  generated_at: "2026-01-01T00:00:00Z",
  override: false,
  team_score: { score: 80, rationale: "Summary" },
  rubric_scores: {},
  strengths: ["Strength"],
  weaknesses: ["Weakness"],
  recommendations: ["Recommendation"],
  requirements_score: 50,
  code_quality_score: 50,
  documentation_score: 50,
  collaboration_score: 50,
  requirements_justification: "Original requirement justification.",
  code_quality_justification: "Original quality justification.",
  documentation_justification: "Original documentation justification.",
  collaboration_justification: "Original collaboration justification.",
};

describe("assessment report API mapping", () => {
  it("maps only supported rubric overrides to the existing endpoint contract", () => {
    expect(buildManualAssessmentPatch(baseReport, backendReport)).toEqual({
      requirements_score: 90,
      requirements_justification: "Updated requirement justification.",
      code_quality_score: 80,
      code_quality_justification: "Updated quality justification.",
      documentation_score: 70,
      documentation_justification: "Updated documentation justification.",
      collaboration_score: 60,
      collaboration_justification: "Updated collaboration justification.",
    });
    expect(baseReport.rubricScores[4].evidenceCitations).toEqual(["commit abc"]);
  });

  it("refuses to build a request when any required backend field is missing", () => {
    const reportWithoutCollaboration = {
      ...baseReport,
      rubricScores: baseReport.rubricScores.filter((item) => item.categoryKey !== "collaboration"),
    };
    expect(buildManualAssessmentPatch(reportWithoutCollaboration, {
      ...backendReport,
      collaboration_justification: null,
      collaboration_score: null,
    })).toBeNull();
  });

  it("reflects saved supported overrides without changing other rubric evidence", () => {
    const savedReport = toSprintAssessmentReport({
      ...backendReport,
      override: true,
      requirements_score: 96,
      requirements_justification: "Instructor-saved rationale.",
      rubric_scores: {
        requirements: { score: 8, justification: "AI rationale.", evidence_citations: ["ticket TYH-16"] },
        cicd: { score: 1, justification: "Original CI/CD rationale.", evidence_citations: ["commit abc"] },
      },
    });

    expect(savedReport.rubricScores[0]).toMatchObject({
      category: "Requirements",
      score: 96,
      justification: "Instructor-saved rationale.",
      evidenceCitations: ["ticket TYH-16"],
    });
    expect(savedReport.rubricScores[1]).toMatchObject({
      category: "CI/CD",
      score: 10,
      justification: "Original CI/CD rationale.",
      evidenceCitations: ["commit abc"],
    });
  });
});
