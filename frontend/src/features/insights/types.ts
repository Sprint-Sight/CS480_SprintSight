export const DIMENSIONS = [
  "requirements",
  "code_quality",
  "testing",
  "documentation",
  "collaboration",
  "cicd",
] as const;
export type Dimension = (typeof DIMENSIONS)[number];
export const DIMENSION_LABELS: Record<Dimension, string> = {
  requirements: "Requirements",
  code_quality: "Code Quality",
  testing: "Testing",
  documentation: "Documentation",
  collaboration: "Collaboration",
  cicd: "CI/CD",
};
export const MAX_REASON = 1000;

export type JudgeStatus = "unknown" | "pending" | "complete" | "failed" | "stale" | "no_trace";
export type LabelStatusFilter = "all" | "labelled" | "unlabelled";

// blind_label: score blind, then reveal. override_gate: Insights unlock once the report is overridden.
export type InsightsMode = "blind_label" | "override_gate";
export type InsightsConfig = { mode: InsightsMode };

export type InsightsCourse = {
  courseId: string;
  code: string;
  name: string;
  section: string;
  term: string;
  year: number;
  reports: number;
  labelledByYou: number;
  overridden: number;
  judgePending: number;
  lastEvaluationAt: string | null;
};
export type CitationCheck = { status: "ok" | "flagged"; groundedRate: number };
export type RunItem = {
  reportId: string;
  teamName: string;
  courseId: string;
  courseCode: string;
  section: string;
  sprintId: string;
  modelName: string;
  generatedAt: string;
  labelsDone: number;
  judgeStatus: JudgeStatus;
  aiScore: number | null;
  aiScoreHidden: boolean;
  insightsUnlocked: boolean;
  overridden: boolean;
  citationCheck: CitationCheck | null;
};
export type RunFilters = {
  courseId?: string;
  sprintId?: string;
  model?: string;
  labelStatus: LabelStatusFilter;
  page: number;
  pageSize: number;
};
export type RunsPage = {
  items: RunItem[];
  total: number;
  page: number;
  pageSize: number;
  facets: {
    courses: { courseId: string; courseCode: string; section: string }[];
    sprints: string[];
    models: string[];
  };
};

export type LabelDraft = { dimension: Dimension; score: number; reason?: string | null };
export type SavedLabel = LabelDraft & { syncStatus: "pending" | "synced" | "failed" | "no_trace" };
export type Evidence = {
  reportId: string;
  teamName: string;
  courseCode: string;
  section: string;
  sprintId: string;
  generatedAt: string | null;
  labels: SavedLabel[];
  labelsDone: number;
  canReveal: boolean;
  locked: boolean;
  dimensions: { dimension: Dimension; label: string; sources: string[] }[];
  metrics: {
    commitFrequency: number;
    codeChurn: number;
    prTurnaroundHours: number | null;
    assignedStoryPoints: number | null;
    completionPercent: number | null;
  } | null;
  commitsTotal: number;
  commits: {
    sha: string;
    author: string;
    message: string;
    timestamp: string;
    linesAdded: number;
    linesDeleted: number;
    filesChanged: number;
  }[];
  jira: {
    key: string;
    summary: string;
    status: string | null;
    assignee: string | null;
    storyPoints: number | null;
    issueType: string | null;
  }[];
  documents: { filename: string; uploadedAt: string | null }[];
  peer: { rater: string; rated: string; score: number; remarks: string | null }[];
};
export type SaveLabelsResult = { labelsDone: number; canReveal: boolean; isBlind: boolean };

export type Tile = {
  key: string;
  label: string;
  value: string;
  detail: string | null;
  severity: "ok" | "warn" | "bad" | "na";
};
export type UnacceptedCitation = {
  citationId: string;
  dimension: string;
  claim: string | null;
  verdict: string;
  severity: string;
  reasoning: string;
};
export type JudgePanel = {
  available: boolean;
  notice: string | null;
  tiles: Tile[];
  unacceptedCitations: UnacceptedCitation[];
  citationsTruncated: boolean;
};
export type RevealDimension = {
  dimension: Dimension;
  label: string;
  aiScore: number | null;
  aiScoreCurrent: number | null;
  overridden: boolean;
  yourScore: number | null;
  yourReason: string | null;
  diff: number | null;
  within1: boolean | null;
};
export type Reveal = {
  reportId: string;
  teamName: string;
  courseCode: string;
  sprintId: string;
  modelName: string;
  overallAiScore: number;
  judgeStatus: JudgeStatus;
  comparison: "blind_label" | "override";
  dimensions: RevealDimension[];
  judge: JudgePanel;
  promptVersions: { name: string; version: string }[];
};
export type TraceView = {
  available: boolean;
  notice: string | null;
  durationMs: number;
  llmCallCount: number;
  spans: {
    name: string;
    parent: string | null;
    startOffsetMs: number;
    durationMs: number;
    status: string;
  }[];
};
export type JudgeStatusView = {
  reportId: string;
  judgeStatus: JudgeStatus;
  checkedAt: string | null;
};
export type InsightsHealth = {
  mlflow: {
    reachable: boolean;
    serverVersion: string | null;
    clientVersion: string | null;
    versionsMatch: boolean;
  };
  labelsPendingSync: number;
  overridesPendingSync: number;
  reportsAwaitingJudge: number;
  telemetryDisabled: boolean;
  generatedAt: string;
};

export type OverrideDimensionStats = {
  dimension: Dimension;
  overridesSaved: number;
  changed: number;
  changeRate: number | null;
  meanAdjustment: number | null;
  meanAbsAdjustment: number | null;
  direction: "raised" | "lowered" | "mixed" | null;
};
export type OverrideStats = {
  reports: number;
  reportsOverridden: number;
  overrideRate: number | null;
  reportsWithChanges: number;
  byDimension: OverrideDimensionStats[];
  notice: string;
};
