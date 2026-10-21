"use client";

import { useState } from "react";
import { AuditLogPage } from "@/features/audit/components/audit-log-page";
import { useAuditLog } from "@/features/audit/hooks/use-audit-log";
import { useAuditRetention } from "@/features/audit/hooks/use-audit-retention";

type AuditLogPageContentProps = {
  role: "instructor" | "admin";
};

export function AuditLogPageContent({ role }: AuditLogPageContentProps) {
  const auditLog = useAuditLog(role);
  const retention = useAuditRetention();
  const [isRetentionModalOpen, setIsRetentionModalOpen] = useState(false);

  const handleRetentionModalOpen = () => {
    setIsRetentionModalOpen(true);
  };

  const handleRetentionModalClose = () => {
    setIsRetentionModalOpen(false);
    retention.clearErrors();
  };

  const handleSaveRetentionConfig = async (payload: { hot_retention_days: number; action_archive_retention_days: number; override_archive_retention_days: number }) => {
    await retention.saveConfig(payload);
  };

  return (
    <AuditLogPage
      role={role}
      actions={auditLog.actions}
      overrides={auditLog.overrides}
      actionsError={auditLog.actionsError}
      overridesError={auditLog.overridesError}
      isLoading={auditLog.isLoading}
      onRefresh={auditLog.refresh}
      retentionConfig={retention.config}
      retentionIsLoading={retention.isLoading}
      retentionError={retention.error}
      retentionIsSaving={retention.isSaving}
      retentionSaveError={retention.saveError}
      isRetentionModalOpen={isRetentionModalOpen}
      onRetentionModalOpen={handleRetentionModalOpen}
      onRetentionModalClose={handleRetentionModalClose}
      onLoadRetentionConfig={retention.loadConfig}
      onSaveRetentionConfig={handleSaveRetentionConfig}
    />
  );
}
