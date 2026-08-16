export type RubricCategory =
  | "Requirements"
  | "Code Quality"
  | "Testing"
  | "Documentation"
  | "Collaboration";

export type RubricScore = {
  category: RubricCategory;
  score: number;
  justification: string;
};

export type SprintAssessmentReport = {
  projectId: string;
  sprintId: string;
  sprintLabel: string;
  teamLabel: string;
  projectLabel: string;
  generatedAt: string;
  overallScore: number;
  overallGrade: string;
  overallSummary: string;
  rubricScores: RubricScore[];
  strengths: string[];
  weaknesses: string[];
  recommendations: string[];
  narrativeFeedback: string[];
};
