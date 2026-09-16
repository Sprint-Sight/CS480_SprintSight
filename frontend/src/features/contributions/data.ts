import { PROJECTS } from "@/features/projects/data";

import type { ContributionDataset } from "@/features/contributions/types";

const DATASETS: ContributionDataset[] = [
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

export function getContributionProjectOptions() {
  return PROJECTS.map((project) => ({ id: project.id, label: `${project.teamName} - ${project.name}` }));
}

export function getContributionDataset(projectId: string) {
  return DATASETS.find((dataset) => dataset.projectId === projectId) ?? DATASETS[0];
}
