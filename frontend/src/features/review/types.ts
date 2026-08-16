export type ReviewCriterion = {
  id: string;
  category: "Requirements" | "Code Quality" | "Testing" | "Documentation" | "Collaboration";
  score: number;
  feedback: string;
};

export type AuditEventType = "generated" | "modified" | "saved" | "approved";

export type ReviewAuditEvent = {
  id: string;
  type: AuditEventType;
  title: string;
  detail: string;
  actor: string;
  timestamp: string;
};
