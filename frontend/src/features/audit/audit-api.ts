import { apiRequest } from "@/features/projects/components/projects-api";

export type ActionAuditRecord = {
  audit_id: string;
  actor_id: string;
  actor_role: "admin" | "instructor" | "student";
  action: string;
  target_type: string;
  target_id: string;
  details: Record<string, unknown>;
  created_at: string;
};

export type OverrideAuditRecord = {
  override_id: string;
  timestamp: string;
  instructor_id: string;
  student_id: string;
  report_id: string;
  original_score: number;
  new_score: number;
  reason_comment: string;
};

export const getActionAuditRecords = () => apiRequest<ActionAuditRecord[]>("/audit/actions");
export const getOverrideAuditRecords = () => apiRequest<OverrideAuditRecord[]>("/audit/overrides");
