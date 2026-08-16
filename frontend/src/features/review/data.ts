import type { ReviewAuditEvent, ReviewCriterion } from "@/features/review/types";

export const INITIAL_REVIEW_CRITERIA: ReviewCriterion[] = [
  {
    id: "requirements",
    category: "Requirements",
    score: 85,
    feedback:
      "Requirements are well-documented and traceable to implementation. User stories are clear and acceptance criteria are defined.",
  },
  {
    id: "code-quality",
    category: "Code Quality",
    score: 78,
    feedback:
      "Code follows consistent patterns. Some modules could benefit from better documentation. Cyclomatic complexity is within acceptable range.",
  },
  {
    id: "testing",
    category: "Testing",
    score: 72,
    feedback:
      "Unit test coverage is at 68%. Integration tests are minimal. Recommend increasing coverage to 80% threshold.",
  },
  {
    id: "documentation",
    category: "Documentation",
    score: 80,
    feedback:
      "API documentation is comprehensive. README is well-maintained. Some inline code comments are missing.",
  },
  {
    id: "collaboration",
    category: "Collaboration",
    score: 88,
    feedback:
      "Excellent team collaboration. Balanced contributions and active code review participation.",
  },
];

export const INITIAL_AUDIT_HISTORY: ReviewAuditEvent[] = [
  {
    id: "audit-1",
    type: "generated",
    title: "AI Assessment Generated",
    detail: "Initial scores generated for Sprint 5.",
    actor: "System",
    timestamp: "Mar 25, 2026 14:32",
  },
  {
    id: "audit-2",
    type: "modified",
    title: "Score Modified",
    detail: "Testing score adjusted from 70 to 72 after reviewing integration evidence.",
    actor: "Dr. Sarah Chen",
    timestamp: "Mar 25, 2026 15:10",
  },
  {
    id: "audit-3",
    type: "saved",
    title: "Review Draft Saved",
    detail: "Feedback notes saved with rationale updates.",
    actor: "Dr. Sarah Chen",
    timestamp: "Mar 25, 2026 15:18",
  },
];
