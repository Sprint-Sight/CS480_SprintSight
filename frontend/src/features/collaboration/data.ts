import { PROJECTS } from "@/features/projects/data";

import type { CollaborationDataset } from "./types";

const DATASETS: CollaborationDataset[] = [
  {
    projectId: "ecommerce-platform",
    projectLabel: "Team Alpha",
    subtitle: "Analyze team collaboration patterns and identify contribution imbalances",
    commitsByMember: [
      { member: "Alice", commits: 45 },
      { member: "Bob", commits: 38 },
      { member: "Charlie", commits: 32 },
      { member: "Diana", commits: 28 },
      { member: "Eve", commits: 41 },
      { member: "Frank", commits: 12 },
    ],
    workloadDistribution: [
      { name: "Code", value: 35, color: "#1E3A8A" },
      { name: "Testing", value: 22, color: "#2F6690" },
      { name: "Documentation", value: 18, color: "#3E87B8" },
      { name: "Design", value: 15, color: "#7CB9E8" },
      { name: "Project Mgmt", value: 10, color: "#A7D8F5" },
    ],
    participationHeatmap: [
      { member: "Alice", week1: 8, week2: 12, week3: 10, week4: 15 },
      { member: "Bob", week1: 6, week2: 9, week3: 11, week4: 12 },
      { member: "Charlie", week1: 10, week2: 7, week3: 8, week4: 7 },
      { member: "Diana", week1: 5, week2: 8, week3: 8, week4: 8 },
      { member: "Eve", week1: 11, week2: 13, week3: 9, week4: 8 },
      { member: "Frank", week1: 2, week2: 3, week3: 4, week4: 3 },
    ],
    riskIndicators: [
      { team: "Team Alpha", risk: "Low", summary: "Well-balanced contributions", balanceScore: 85 },
      { team: "Team Beta", risk: "Medium", summary: "One member contributing less", balanceScore: 68 },
      { team: "Team Delta", risk: "High", summary: "Significant contribution imbalance", balanceScore: 42 },
      { team: "Team Zeta", risk: "High", summary: "Free-rider pattern detected", balanceScore: 38 },
    ],
  },
  {
    projectId: "chat-application",
    projectLabel: "Team Beta",
    subtitle: "Analyze team collaboration patterns and identify contribution imbalances",
    commitsByMember: [
      { member: "Eve", commits: 31 },
      { member: "Frank", commits: 27 },
      { member: "Grace", commits: 19 },
      { member: "Helen", commits: 24 },
    ],
    workloadDistribution: [
      { name: "Code", value: 44, color: "#1E3A8A" },
      { name: "Testing", value: 21, color: "#2F6690" },
      { name: "Documentation", value: 12, color: "#3E87B8" },
      { name: "Design", value: 13, color: "#7CB9E8" },
      { name: "Project Mgmt", value: 10, color: "#A7D8F5" },
    ],
    participationHeatmap: [
      { member: "Eve", week1: 8, week2: 9, week3: 8, week4: 6 },
      { member: "Frank", week1: 6, week2: 8, week3: 7, week4: 6 },
      { member: "Grace", week1: 4, week2: 5, week3: 5, week4: 5 },
      { member: "Helen", week1: 7, week2: 6, week3: 6, week4: 5 },
    ],
    riskIndicators: [
      { team: "Team Beta", risk: "Medium", summary: "One member contributing less", balanceScore: 66 },
      { team: "Team Alpha", risk: "Low", summary: "Strong collaboration rhythm", balanceScore: 82 },
      { team: "Team Zeta", risk: "High", summary: "Task ownership concentrated", balanceScore: 40 },
    ],
  },
];

export function getCollaborationProjectOptions() {
  return PROJECTS.map((project) => ({ id: project.id, label: `${project.teamName} - ${project.name}` }));
}

export function getCollaborationDataset(projectId: string) {
  return DATASETS.find((item) => item.projectId === projectId) ?? DATASETS[0];
}
