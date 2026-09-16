import { PROJECTS } from "@/features/projects/data";
import type { CollaborationDataset, ContributionDataset } from "@/features/collaboration/types";

const CONTRIBUTION_DATASETS: ContributionDataset[] = [
  {
    projectId: "ecommerce-platform",
    teamLabel: "Team Alpha",
    projectLabel: "E-Commerce Platform",
    sprintLabel: "Sprint 5",
    members: [
      {
        id: "m1",
        name: "Alice Chen",
        role: "Team Lead / Backend",
        initials: "AC",
        githubScore: 92,
        jiraScore: 88,
        peerScore: 4.7,
        overallScore: 90,
        recommendedGrade: "A",
        gradeAdjustmentPercent: 2,
        aiAssessment: "Consistently high contributions across all metrics. Strong leadership and code quality.",
      },
      {
        id: "m2",
        name: "Bob Martinez",
        role: "Backend Developer",
        initials: "BM",
        githubScore: 78,
        jiraScore: 82,
        peerScore: 4.1,
        overallScore: 79,
        recommendedGrade: "B+",
        gradeAdjustmentPercent: 0,
        aiAssessment: "Solid contributions. Good testing practices, slightly below average in documentation updates.",
      },
      {
        id: "m3",
        name: "Charlie Wang",
        role: "Frontend Developer",
        initials: "CW",
        githubScore: 86,
        jiraScore: 90,
        peerScore: 4.5,
        overallScore: 88,
        recommendedGrade: "A-",
        gradeAdjustmentPercent: 1,
        aiAssessment: "High implementation throughput with strong review quality and effective sprint planning support.",
      },
      {
        id: "m4",
        name: "Diana Patel",
        role: "QA and Documentation",
        initials: "DP",
        githubScore: 65,
        jiraScore: 72,
        peerScore: 3.9,
        overallScore: 70,
        recommendedGrade: "B",
        gradeAdjustmentPercent: -1,
        aiAssessment: "Reliable support work but fewer core code contributions; increase test ownership for balance.",
      },
    ],
  },
  {
    projectId: "chat-application",
    teamLabel: "Team Beta",
    projectLabel: "Chat Application",
    sprintLabel: "Sprint 5",
    members: [
      {
        id: "b1",
        name: "Eve Johnson",
        role: "Team Lead",
        initials: "EJ",
        githubScore: 88,
        jiraScore: 84,
        peerScore: 4.6,
        overallScore: 86,
        recommendedGrade: "A-",
        gradeAdjustmentPercent: 1,
        aiAssessment: "Strong ownership and sustained code delivery with healthy collaboration behavior.",
      },
      {
        id: "b2",
        name: "Frank Lee",
        role: "Full Stack",
        initials: "FL",
        githubScore: 82,
        jiraScore: 79,
        peerScore: 4.2,
        overallScore: 80,
        recommendedGrade: "B+",
        gradeAdjustmentPercent: 0,
        aiAssessment: "Good contribution consistency, but should improve sprint planning participation.",
      },
      {
        id: "b3",
        name: "Grace Kim",
        role: "QA",
        initials: "GK",
        githubScore: 69,
        jiraScore: 74,
        peerScore: 3.8,
        overallScore: 71,
        recommendedGrade: "B",
        gradeAdjustmentPercent: -1,
        aiAssessment: "Testing support is valuable; execution depth needs improvement on complex cases.",
      },
    ],
  },
];

const COLLABORATION_DATASETS: CollaborationDataset[] = [
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
  return COLLABORATION_DATASETS.find((item) => item.projectId === projectId) ?? COLLABORATION_DATASETS[0];
}

export function getContributionDataset(projectId: string) {
  return CONTRIBUTION_DATASETS.find((dataset) => dataset.projectId === projectId) ?? CONTRIBUTION_DATASETS[0];
}