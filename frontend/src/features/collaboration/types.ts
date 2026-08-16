export type MemberCommitMetric = {
  member: string;
  commits: number;
};

export type WorkloadSlice = {
  name: string;
  value: number;
  color: string;
};

export type HeatmapRow = {
  member: string;
  week1: number;
  week2: number;
  week3: number;
  week4: number;
};

export type TeamRiskIndicator = {
  team: string;
  risk: "Low" | "Medium" | "High";
  summary: string;
  balanceScore: number;
};

export type CollaborationDataset = {
  projectId: string;
  projectLabel: string;
  subtitle: string;
  commitsByMember: MemberCommitMetric[];
  workloadDistribution: WorkloadSlice[];
  participationHeatmap: HeatmapRow[];
  riskIndicators: TeamRiskIndicator[];
};
