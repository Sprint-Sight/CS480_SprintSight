import type { ProgressDataset } from "@/features/progress/types";

export const PROGRESS_DATA: ProgressDataset = {
  latestScores: {
    requirements: 85,
    codeQuality: 78,
    testing: 72,
    documentation: 80,
    collaboration: 88,
  },
  scoreDeltas: {
    requirements: 5,
    codeQuality: 4,
    testing: 4,
    documentation: 4,
    collaboration: 4,
  },
  categoryTrend: [
    { sprint: "Sprint 1", requirements: 65, codeQuality: 60, testing: 58, documentation: 53, collaboration: 70 },
    { sprint: "Sprint 2", requirements: 70, codeQuality: 64, testing: 62, documentation: 58, collaboration: 74 },
    { sprint: "Sprint 3", requirements: 73, codeQuality: 68, testing: 67, documentation: 62, collaboration: 78 },
    { sprint: "Sprint 4", requirements: 79, codeQuality: 73, testing: 71, documentation: 68, collaboration: 83 },
    { sprint: "Sprint 5", requirements: 85, codeQuality: 78, testing: 72, documentation: 80, collaboration: 88 },
  ],
  teamComparison: [
    { team: "Alpha", sprint3: 74, sprint4: 80, sprint5: 82 },
    { team: "Beta", sprint3: 68, sprint4: 72, sprint5: 75 },
    { team: "Gamma", sprint3: 78, sprint4: 84, sprint5: 89 },
    { team: "Delta", sprint3: 62, sprint4: 65, sprint5: 68 },
    { team: "Epsilon", sprint3: 80, sprint4: 86, sprint5: 92 },
  ],
  regressionAlerts: [
    {
      id: "r1",
      team: "Team Delta",
      category: "Testing",
      fromSprint: "Sprint 4",
      toSprint: "Sprint 5",
      fromScore: 58,
      toScore: 52,
    },
    {
      id: "r2",
      team: "Team Beta",
      category: "Documentation",
      fromSprint: "Sprint 4",
      toSprint: "Sprint 5",
      fromScore: 69,
      toScore: 65,
    },
  ],
};
