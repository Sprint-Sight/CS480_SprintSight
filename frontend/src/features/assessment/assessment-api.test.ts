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
    { categoryKey: "testing", category: "Testing", score: 100, justification: "Current testing justification.", evidenceCitations: ["test report"] },
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
  rubric_scores: {
    cicd: { score: 1, justification: "Uneditable CI/CD justification.", evidence_citations: ["commit abc"] },
    testing: { score: 10, justification: "Current testing justification.", evidence_citations: ["test report"] },
  },
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
  it("builds the confirmed PATCH contract with fixed dimensions, dynamic rubrics, summaries, and citations", () => {
    expect(buildManualAssessmentPatch(baseReport, backendReport)).toEqual({
      requirements_score: 90,
      requirements_justification: "Updated requirement justification.",
      code_quality_score: 80,
      code_quality_justification: "Updated quality justification.",
      documentation_score: 70,
      documentation_justification: "Updated documentation justification.",
      collaboration_score: 60,
      collaboration_justification: "Updated collaboration justification.",
      rubric_scores: {
        cicd: {
          score: 1,
          justification: "Uneditable CI/CD justification.",
          evidence_citations: ["commit abc"],
        },
        testing: {
          score: 10,
          justification: "Current testing justification.",
          evidence_citations: ["test report"],
        },
      },
      strengths: ["Strength"],
      weaknesses: ["Weakness"],
      recommendations: ["Recommendation"],
    });
    expect(baseReport.rubricScores[4].evidenceCitations).toEqual(["commit abc"]);
  });

  it("includes changed dynamic category values while preserving evidence citations", () => {
    const editedReport = {
      ...baseReport,
      rubricScores: baseReport.rubricScores.map((item) =>
        item.categoryKey === "cicd"
          ? { ...item, score: 70, justification: "Updated CI/CD feedback." }
          : item,
      ),
    };

    expect(buildManualAssessmentPatch(editedReport, backendReport)?.rubric_scores.cicd).toEqual({
      score: 7,
      justification: "Updated CI/CD feedback.",
      evidence_citations: ["commit abc"],
    });
  });

  it("refuses to build a request when any required fixed backend field is missing", () => {
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
      strengths: ["Saved strength"],
      weaknesses: ["Saved weakness"],
      recommendations: ["Saved recommendation"],
      rubric_scores: {
        requirements: { score: 8, justification: "AI rationale.", evidence_citations: ["ticket TYH-16"] },
        cicd: { score: 7, justification: "Updated CI/CD rationale.", evidence_citations: ["commit abc"] },
        testing: { score: 9, justification: "Updated testing rationale.", evidence_citations: ["test report"] },
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
      score: 70,
      justification: "Updated CI/CD rationale.",
      evidenceCitations: ["commit abc"],
    });
    expect(savedReport.rubricScores[2]).toMatchObject({
      category: "Testing",
      score: 90,
      justification: "Updated testing rationale.",
      evidenceCitations: ["test report"],
    });
    expect(savedReport).toMatchObject({
      strengths: ["Saved strength"],
      weaknesses: ["Saved weakness"],
      recommendations: ["Saved recommendation"],
    });
  });
});
