export type SprintMetricPoint = {
  sprint: string;
  requirements: number;
  codeQuality: number;
  testing: number;
  documentation: number;
  collaboration: number;
};

export type TeamSprintScore = {
  team: string;
  sprint3: number;
  sprint4: number;
  sprint5: number;
};

export type RegressionAlert = {
  id: string;
  team: string;
  category: "Requirements" | "Code Quality" | "Testing" | "Documentation" | "Collaboration";
  fromSprint: string;
  toSprint: string;
  fromScore: number;
  toScore: number;
};

export type ProgressDataset = {
  latestScores: {
    requirements: number;
    codeQuality: number;
    testing: number;
    documentation: number;
    collaboration: number;
  };
  scoreDeltas: {
    requirements: number;
    codeQuality: number;
    testing: number;
    documentation: number;
    collaboration: number;
  };
  categoryTrend: SprintMetricPoint[];
  teamComparison: TeamSprintScore[];
  regressionAlerts: RegressionAlert[];
};
