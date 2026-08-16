import { PROJECTS } from "@/features/projects/data";

import type { SprintAssessmentReport } from "./types";

const REPORTS: SprintAssessmentReport[] = [
  {
    projectId: "ecommerce-platform",
    sprintId: "s5",
    sprintLabel: "Sprint 5",
    teamLabel: "Team Alpha",
    projectLabel: "E-Commerce Platform",
    generatedAt: "2026-03-30 14:22",
    overallScore: 81,
    overallGrade: "B+",
    overallSummary:
      "The sprint delivered meaningful feature progress with stable collaboration. Test depth and architecture documentation still need improvement before release hardening.",
    rubricScores: [
      {
        category: "Requirements",
        score: 85,
        justification: "Most acceptance criteria were completed and traceable to Jira tasks.",
      },
      {
        category: "Code Quality",
        score: 78,
        justification: "Implementation quality is solid, but several modules still carry duplicated logic.",
      },
      {
        category: "Testing",
        score: 72,
        justification: "Core flows are covered, while edge-case and integration coverage remains thin.",
      },
      {
        category: "Documentation",
        score: 80,
        justification: "Architecture and API notes exist, but not all changes were documented consistently.",
      },
      {
        category: "Collaboration",
        score: 88,
        justification: "Commit rhythm and review participation were balanced across most team members.",
      },
    ],
    strengths: [
      "Excellent collaboration with balanced contributions across most members.",
      "Requirements were translated into implementation tasks with clear ownership.",
      "Consistent sprint velocity improvement across the last three sprint cycles.",
      "Code reviews were timely and reduced defect leakage before merge.",
    ],
    weaknesses: [
      "Unit test coverage is below the 80% threshold for core service modules.",
      "Some code modules still miss in-line design rationale comments.",
      "Integration tests are limited for checkout and payment fallback flows.",
      "Technical debt is growing in authentication-related helper utilities.",
    ],
    recommendations: [
      "Increase unit test coverage to at least 80% by Sprint 6.",
      "Adopt a short review checklist for docs and edge-case validation.",
      "Schedule one technical debt task for auth helper consolidation.",
      "Add integration tests for login, checkout, and payment callbacks.",
    ],
    narrativeFeedback: [
      "LLM analysis indicates that requirement alignment improved compared to the previous sprint, with fewer untracked work items.",
      "Repository activity shows healthy collaboration patterns and relatively even review participation.",
      "Risk remains in testing maturity because high-impact edge cases are not fully represented in automated suites.",
    ],
  },
  {
    projectId: "chat-application",
    sprintId: "s5",
    sprintLabel: "Sprint 5",
    teamLabel: "Team Beta",
    projectLabel: "Chat Application",
    generatedAt: "2026-03-30 14:25",
    overallScore: 74,
    overallGrade: "B",
    overallSummary:
      "Delivery quality is acceptable, but testing and documentation consistency should improve to reduce release risk.",
    rubricScores: [
      { category: "Requirements", score: 76, justification: "Most user stories were delivered with minor scope drift." },
      { category: "Code Quality", score: 73, justification: "Code is readable but includes unresolved refactor opportunities." },
      { category: "Testing", score: 68, justification: "Regression checks cover common paths, not enough failure paths." },
      { category: "Documentation", score: 71, justification: "Key decisions are captured, but update cadence is uneven." },
      { category: "Collaboration", score: 82, justification: "Standups and PR interactions indicate good team communication." },
    ],
    strengths: [
      "Clear team communication and predictable standup throughput.",
      "Feature milestones were delivered without major blocking defects.",
    ],
    weaknesses: [
      "Insufficient integration tests for realtime failure scenarios.",
      "Documentation updates lag behind implementation changes.",
    ],
    recommendations: [
      "Add failure-path integration tests for reconnect and rate-limiting.",
      "Set a docs update gate in the pull request workflow.",
    ],
    narrativeFeedback: [
      "LLM reasoning highlights stable delivery pace with moderate quality risk tied to incomplete testing.",
    ],
  },
];

export function getAssessmentProjectOptions() {
  return PROJECTS.map((project) => ({ id: project.id, label: `${project.teamName} - ${project.name}` }));
}

export function getAssessmentReport(projectId: string) {
  return REPORTS.find((report) => report.projectId === projectId) ?? REPORTS[0];
}
