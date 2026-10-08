import { apiRequest } from "@/features/projects/components/projects-api";
import type { SprintAssessmentReport } from "@/features/assessment/types";

export type BackendRubricScore = {
  score: number;
  justification?: string | null;
  evidence_citations?: string[];
};

export type BackendAssessmentReport = {
  report_id?: string;
  project_id: string;
  sprint_id: string;
  generated_at: string;
  override?: boolean;
  team_score: { score: number; rationale: string; overall_grade?: string };
  rubric_scores: Record<string, BackendRubricScore>;
  strengths: string[];
  weaknesses: string[];
  recommendations: string[];
  requirements_score?: number | null;
  code_quality_score?: number | null;
  documentation_score?: number | null;
  collaboration_score?: number | null;
  requirements_justification?: string | null;
  code_quality_justification?: string | null;
  documentation_justification?: string | null;
  collaboration_justification?: string | null;
};

export type ManualAssessmentPatch = {
  requirements_score: number;
  code_quality_score: number;
  documentation_score: number;
  collaboration_score: number;
  requirements_justification: string;
  code_quality_justification: string;
  documentation_justification: string;
  collaboration_justification: string;
};

type SupportedDimension = {
  categoryKey: string;
  scoreKey: keyof ManualAssessmentPatch;
  justificationKey: keyof ManualAssessmentPatch;
  backendScoreKey: keyof BackendAssessmentReport;
  backendJustificationKey: keyof BackendAssessmentReport;
};

export const supportedAssessmentDimensions: SupportedDimension[] = [
  {
    categoryKey: "requirements",
    scoreKey: "requirements_score",
    justificationKey: "requirements_justification",
    backendScoreKey: "requirements_score",
    backendJustificationKey: "requirements_justification",
  },
  {
    categoryKey: "codequality",
    scoreKey: "code_quality_score",
    justificationKey: "code_quality_justification",
    backendScoreKey: "code_quality_score",
    backendJustificationKey: "code_quality_justification",
  },
  {
    categoryKey: "documentation",
    scoreKey: "documentation_score",
    justificationKey: "documentation_justification",
    backendScoreKey: "documentation_score",
    backendJustificationKey: "documentation_justification",
  },
  {
    categoryKey: "collaboration",
    scoreKey: "collaboration_score",
    justificationKey: "collaboration_justification",
    backendScoreKey: "collaboration_score",
    backendJustificationKey: "collaboration_justification",
  },
];

function normalizeCategoryKey(value: string) {
  return value.toLowerCase().replace(/[^a-z0-9]/g, "");
}

export function getSupportedDimension(categoryKey: string) {
  const normalized = normalizeCategoryKey(categoryKey);
  return supportedAssessmentDimensions.find((dimension) => dimension.categoryKey === normalized);
}

export function buildManualAssessmentPatch(
  report: SprintAssessmentReport,
  backendReport: BackendAssessmentReport,
): ManualAssessmentPatch | null {
  function readDimension(dimension: SupportedDimension) {
    const rubricScore = report.rubricScores.find(
      (item) => normalizeCategoryKey(item.categoryKey || item.category) === dimension.categoryKey,
    );
    const score = rubricScore?.score ?? backendReport[dimension.backendScoreKey];
    const justification = rubricScore?.justification ?? backendReport[dimension.backendJustificationKey];

    if (
      typeof score !== "number" ||
      score < 0 ||
      score > 100 ||
      typeof justification !== "string" ||
      !justification.trim() ||
      justification.trim().length > 500
    ) {
      return null;
    }
    return { score, justification: justification.trim() };
  }

  const requirements = readDimension(supportedAssessmentDimensions[0]);
  const codeQuality = readDimension(supportedAssessmentDimensions[1]);
  const documentation = readDimension(supportedAssessmentDimensions[2]);
  const collaboration = readDimension(supportedAssessmentDimensions[3]);
  if (!requirements || !codeQuality || !documentation || !collaboration) return null;

  return {
    requirements_score: requirements.score,
    requirements_justification: requirements.justification,
    code_quality_score: codeQuality.score,
    code_quality_justification: codeQuality.justification,
    documentation_score: documentation.score,
    documentation_justification: documentation.justification,
    collaboration_score: collaboration.score,
    collaboration_justification: collaboration.justification,
  };
}

export const patchAssessmentReport = (reportId: string, payload: ManualAssessmentPatch) =>
  apiRequest<BackendAssessmentReport>(`/assessments/reports/${encodeURIComponent(reportId)}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });