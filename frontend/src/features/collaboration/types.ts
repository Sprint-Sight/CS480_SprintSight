export type MemberCommitMetric = {
  id: string;
  student_id: string | null;
  member: string;
  commits: number;
  linesChanged: number;
};

export type CollaborationMetric = "commits" | "linesChanged";

export type WorkloadSlice = {
  id: string;
  student_id: string | null;
  name: string;
  value: number;
  color: string;
};

export type HeatmapRow = {
  id: string;
  student_id: string | null;
  member: string;
  week1: number;
  week2: number;
  week3: number;
  week4: number;
};

export type UnmatchedCommit = {
  sha: string;
  author: string;
  timestamp: string;
  linesAdded: number;
  linesDeleted: number;
};

export type TeamRiskIndicator = {
  team: string;
  risk: "Low" | "Medium" | "High";
  summary: string;
  balanceScore: number;
};

export type ContributionMember = {
  id: string;
  name: string;
  role: string;
  initials: string;
  githubScore: number;
  jiraScore: number;
  peerScore: number;
  overallScore: number;
  recommendedGrade: string;
  gradeAdjustmentPercent: number;
  aiAssessment: string;
};

export type ContributionDataset = {
  projectId: string;
  teamLabel: string;
  projectLabel: string;
  sprintLabel: string;
  members: ContributionMember[];
};

export type CollaborationDataset = {
  projectId: string;
  projectLabel: string;
  subtitle: string;
  commitsByMember: MemberCommitMetric[];
  unmatchedCommits: UnmatchedCommit[];
  workloadDistribution: WorkloadSlice[];
  participationHeatmap: HeatmapRow[];
  riskIndicators: TeamRiskIndicator[];
  contributionDetails?: ContributionDataset;
};