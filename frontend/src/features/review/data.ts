import type { ReviewAuditEvent, ReviewCriterion } from "@/features/review/types";

export const INITIAL_REVIEW_CRITERIA: ReviewCriterion[] = [
  { id: "requirements", category: "Requirements", score: 0, feedback: "" },
  { id: "code-quality", category: "Code Quality", score: 0, feedback: "" },
  { id: "testing", category: "Testing", score: 0, feedback: "" },
  { id: "documentation", category: "Documentation", score: 0, feedback: "" },
  { id: "collaboration", category: "Collaboration", score: 0, feedback: "" },
];

export const INITIAL_AUDIT_HISTORY: ReviewAuditEvent[] = [];
