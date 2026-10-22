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
