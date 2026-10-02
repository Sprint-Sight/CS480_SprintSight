"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import {
  getActionAuditRecords,
  getOverrideAuditRecords,
  type ActionAuditRecord,
  type OverrideAuditRecord,
} from "@/features/audit/audit-api";

type AuditRole = "instructor" | "admin";

type AuditLogData = {
  actions: ActionAuditRecord[];
  overrides: OverrideAuditRecord[];
  actionsError: string;
  overridesError: string;
  isLoading: boolean;
  refresh: () => void;
};

function getErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Could not load audit records.";
}

export function useAuditLog(role: AuditRole): AuditLogData {
  const router = useRouter();
  const [actions, setActions] = useState<ActionAuditRecord[]>([]);
  const [overrides, setOverrides] = useState<OverrideAuditRecord[]>([]);
  const [actionsError, setActionsError] = useState("");
  const [overridesError, setOverridesError] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [refreshCount, setRefreshCount] = useState(0);

  useEffect(() => {
    if (sessionStorage.getItem("sprintsight-auth-role") !== role) {
      router.replace("/login");
      return;
    }

    let cancelled = false;
    setIsLoading(true);
    setActionsError("");
    setOverridesError("");

    async function loadAuditRecords() {
      const [actionsResult, overridesResult] = await Promise.allSettled([
        getActionAuditRecords(),
        getOverrideAuditRecords(),
      ]);

      if (cancelled) return;
      if (actionsResult.status === "fulfilled") {
        setActions(actionsResult.value);
      } else {
        setActionsError(getErrorMessage(actionsResult.reason));
      }
      if (overridesResult.status === "fulfilled") {
        setOverrides(overridesResult.value);
      } else {
        setOverridesError(getErrorMessage(overridesResult.reason));
      }
      setIsLoading(false);
    }

    void loadAuditRecords();
    return () => {
      cancelled = true;
    };
  }, [refreshCount, role, router]);

  return {
    actions,
    overrides,
    actionsError,
    overridesError,
    isLoading,
    refresh: () => setRefreshCount((count) => count + 1),
  };
}
