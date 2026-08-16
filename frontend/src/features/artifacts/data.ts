import { PROJECTS } from "@/features/projects/data";

import type { ArtifactProjectDataset } from "./types";

const DATASETS: ArtifactProjectDataset[] = [
  {
    projectId: "ecommerce-platform",
    github: [
      { id: "gh-1", title: "feat: add user authentication module", author: "Alice", date: "2026-03-25", ref: "a3f7b2c", type: "commit" },
      { id: "gh-2", title: "fix: resolve cart calculation bug", author: "Bob", date: "2026-03-24", ref: "e1d9f4a", type: "commit" },
      { id: "gh-3", title: "PR #42: Implement payment gateway integration", author: "Charlie", date: "2026-03-23", ref: "#42", type: "pr", status: "merged" },
      { id: "gh-4", title: "docs: update API documentation", author: "Diana", date: "2026-03-23", ref: "b8c2e1f", type: "commit" },
      { id: "gh-5", title: "PR #41: Add product search functionality", author: "Alice", date: "2026-03-22", ref: "#41", type: "pr", status: "merged" },
      { id: "gh-6", title: "test: add unit tests for order service", author: "Bob", date: "2026-03-21", ref: "f47c3d", type: "commit" },
    ],
    jira: [
      { id: "j-1", key: "ECP-201", title: "Implement JWT middleware", assignee: "Alice", sprint: "Sprint 5", status: "Done", points: 5 },
      { id: "j-2", key: "ECP-207", title: "Fix pricing edge cases", assignee: "Bob", sprint: "Sprint 5", status: "In Progress", points: 3 },
      { id: "j-3", key: "ECP-214", title: "Finalize checkout UX", assignee: "Charlie", sprint: "Sprint 5", status: "To Do", points: 8 },
      { id: "j-4", key: "ECP-216", title: "Payment gateway callback handler", assignee: "Diana", sprint: "Sprint 5", status: "In Progress", points: 5 },
    ],
    documents: [
      { id: "d-1", fileName: "Sprint-5-Design-Notes.pdf", fileType: "PDF", uploadedBy: "Alice", uploadedAt: "2026-03-22", size: "2.1 MB" },
      { id: "d-2", fileName: "Checkout-Flow-ADR.md", fileType: "MD", uploadedBy: "Charlie", uploadedAt: "2026-03-21", size: "124 KB" },
      { id: "d-3", fileName: "API-Spec-v3.docx", fileType: "DOCX", uploadedBy: "Diana", uploadedAt: "2026-03-20", size: "890 KB" },
    ],
    communication: [
      { id: "c-1", channel: "Slack #team-alpha", summary: "Discussed payment retry handling and timeout strategy.", capturedAt: "2026-03-24" },
      { id: "c-2", channel: "Meeting Transcript", summary: "Sprint planning update and risk alignment.", capturedAt: "2026-03-23" },
    ],
    peerEvaluation: [
      { id: "p-1", reviewer: "Alice", target: "Bob", score: 84, sprint: "Sprint 5" },
      { id: "p-2", reviewer: "Bob", target: "Charlie", score: 88, sprint: "Sprint 5" },
      { id: "p-3", reviewer: "Diana", target: "Alice", score: 91, sprint: "Sprint 5" },
    ],
    sources: [
      { source: "GitHub", records: 148, lastSyncedAt: "2026-03-25 09:45", parserStatus: "Healthy", evaluationUsage: "Code quality, ownership, delivery cadence" },
      { source: "Jira", records: 92, lastSyncedAt: "2026-03-25 09:40", parserStatus: "Healthy", evaluationUsage: "Task completion, planning reliability" },
      { source: "Documents", records: 37, lastSyncedAt: "2026-03-25 09:30", parserStatus: "Warning", evaluationUsage: "Evidence quality, documentation completeness" },
    ],
  },
  {
    projectId: "chat-application",
    github: [
      { id: "gh-b1", title: "feat: add threaded replies", author: "Eve", date: "2026-03-24", ref: "82bc11", type: "commit" },
      { id: "gh-b2", title: "PR #27: Notification settings page", author: "Frank", date: "2026-03-23", ref: "#27", type: "pr", status: "open" },
    ],
    jira: [
      { id: "j-b1", key: "CHAT-88", title: "Rate limit websocket events", assignee: "Eve", sprint: "Sprint 5", status: "In Progress", points: 5 },
      { id: "j-b2", key: "CHAT-91", title: "Refine mentions parsing", assignee: "Grace", sprint: "Sprint 5", status: "To Do", points: 2 },
    ],
    documents: [
      { id: "d-b1", fileName: "Realtime-Architecture.pdf", fileType: "PDF", uploadedBy: "Frank", uploadedAt: "2026-03-21", size: "1.6 MB" },
    ],
    communication: [
      { id: "c-b1", channel: "Discord Team Room", summary: "Debugged websocket disconnection issue.", capturedAt: "2026-03-24" },
    ],
    peerEvaluation: [
      { id: "p-b1", reviewer: "Eve", target: "Frank", score: 79, sprint: "Sprint 5" },
    ],
    sources: [
      { source: "GitHub", records: 89, lastSyncedAt: "2026-03-25 09:00", parserStatus: "Healthy", evaluationUsage: "Contribution volume and PR quality" },
      { source: "Jira", records: 61, lastSyncedAt: "2026-03-25 08:54", parserStatus: "Healthy", evaluationUsage: "Backlog hygiene and cycle time" },
      { source: "Documents", records: 15, lastSyncedAt: "2026-03-25 08:40", parserStatus: "Healthy", evaluationUsage: "Design rationale and requirements mapping" },
    ],
  },
];

export function getArtifactProjectOptions() {
  return PROJECTS.map((project) => ({ id: project.id, label: `${project.teamName} - ${project.name}` }));
}

export function getArtifactDataset(projectId: string) {
  return DATASETS.find((dataset) => dataset.projectId === projectId) ?? DATASETS[0];
}
