import Link from "next/link";
import { ArrowLeft, RefreshCw, Settings } from "lucide-react";

import type { ActionAuditRecord, OverrideAuditRecord, AuditRetentionConfig } from "@/features/audit/audit-api";
import { ActionAuditTable } from "@/features/audit/components/action-audit-table";
import { OverrideAuditTable } from "@/features/audit/components/override-audit-table";
import { AuditRetentionModal } from "@/features/audit/components/audit-retention-modal";

type AuditLogPageProps = {
  role: "instructor" | "admin";
  actions: ActionAuditRecord[];
  overrides: OverrideAuditRecord[];
  actionsError: string;
  overridesError: string;
  isLoading: boolean;
  onRefresh: () => void;
  retentionConfig: AuditRetentionConfig | null;
  retentionIsLoading: boolean;
  retentionError: string | null;
  retentionIsSaving: boolean;
  retentionSaveError: string | null;
  isRetentionModalOpen: boolean;
  onRetentionModalOpen: () => void;
  onRetentionModalClose: () => void;
  onLoadRetentionConfig: () => Promise<void>;
  onSaveRetentionConfig: (payload: { hot_retention_days: number; action_archive_retention_days: number; override_archive_retention_days: number }) => Promise<void>;
};

export function AuditLogPage({
  role,
  actions,
  overrides,
  actionsError,
  overridesError,
  isLoading,
  onRefresh,
  retentionConfig,
  retentionIsLoading,
  retentionError,
  retentionIsSaving,
  retentionSaveError,
  isRetentionModalOpen,
  onRetentionModalOpen,
  onRetentionModalClose,
  onLoadRetentionConfig,
  onSaveRetentionConfig,
}: AuditLogPageProps) {
  const returnHref = role === "admin" ? "/admin" : "/";
  const returnLabel = role === "admin" ? "User Directory" : "Dashboard";
  const isAdmin = role === "admin";

  return (
    <main className="mx-auto min-h-screen max-w-7xl space-y-6 bg-slate-50 p-6 text-slate-900 sm:p-8">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-blue-950">Audit Log</h1>
          <p className="mt-1 text-sm text-slate-500">Review recorded system actions and assessment score overrides.</p>
        </div>
        <div className="flex items-center gap-2">
          {isAdmin && (
            <button
              onClick={onRetentionModalOpen}
              className="inline-flex h-10 items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 text-sm font-medium text-slate-700 hover:bg-slate-50 transition-colors"
              title="Configure retention settings"
            >
              <Settings className="h-4 w-4" />
              Retention Settings
            </button>
          )}
          <Link href={returnHref} className="inline-flex h-10 items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 text-sm font-medium text-slate-700 hover:bg-slate-50">
            <ArrowLeft className="h-4 w-4" />
            Back to {returnLabel}
          </Link>
          <button type="button" onClick={onRefresh} disabled={isLoading} className="inline-flex h-10 items-center gap-2 rounded-lg bg-blue-900 px-3 text-sm font-semibold text-white hover:bg-blue-800 disabled:opacity-60">
            <RefreshCw className={`h-4 w-4 ${isLoading ? "animate-spin" : ""}`} />
            Refresh
          </button>
        </div>
      </header>
      <ActionAuditTable records={actions} error={actionsError} isLoading={isLoading} />
      <OverrideAuditTable records={overrides} error={overridesError} isLoading={isLoading} />

      {/* Retention Settings Modal - Admin only */}
      {isAdmin && (
        <AuditRetentionModal
          isOpen={isRetentionModalOpen}
          config={retentionConfig}
          isLoading={retentionIsLoading}
          isSaving={retentionIsSaving}
          error={retentionError}
          saveError={retentionSaveError}
          onClose={onRetentionModalClose}
          onSave={onSaveRetentionConfig}
          onLoadConfig={onLoadRetentionConfig}
        />
      )}
    </main>
  );
}
