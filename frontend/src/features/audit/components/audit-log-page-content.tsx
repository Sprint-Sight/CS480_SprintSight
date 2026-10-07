"use client";

import { AuditLogPage } from "@/features/audit/components/audit-log-page";
import { useAuditLog } from "@/features/audit/hooks/use-audit-log";

type AuditLogPageContentProps = {
  role: "instructor" | "admin";
};

export function AuditLogPageContent({ role }: AuditLogPageContentProps) {
  const auditLog = useAuditLog(role);
  return <AuditLogPage role={role} actions={auditLog.actions} overrides={auditLog.overrides} actionsError={auditLog.actionsError} overridesError={auditLog.overridesError} isLoading={auditLog.isLoading} onRefresh={auditLog.refresh} />;
}
