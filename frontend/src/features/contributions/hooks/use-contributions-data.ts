"use client";

import { useMemo } from "react";

import { useIngestionScope } from "@/features/ingestion/hooks/use-ingestion-scope";
import { useIngestionSync } from "@/features/ingestion/hooks/use-ingestion-sync";
import { summarizeIngestionRuns } from "@/features/ingestion/ingestion-query";
import type { ContributionDataset } from "@/features/contributions/types";
import { useSession } from "@/lib/auth/session";

export function useContributionsData() {
  const { scope } = useIngestionScope();
  const selectedProjectId = scope.selectedProjectId || "";
  // Ingestion run endpoints are faculty-only, so students never trigger the sync.
  const canSync = useSession()?.user?.role === "instructor";
  const { gitRuns, jiraSnapshots, isSyncing, syncError } = useIngestionSync({
    projectId: selectedProjectId,
    courseId: scope.selectedCourseId || undefined,
    enabled: canSync,
  });
  const dataset = useMemo<ContributionDataset>(() => ({ projectId: selectedProjectId, teamLabel: "No team data", projectLabel: selectedProjectId || "No project selected", sprintLabel: scope.selectedSprintId || "No sprint selected", members: [] }), [selectedProjectId, scope.selectedSprintId]);
  const liveTotals = useMemo(() => summarizeIngestionRuns(gitRuns, jiraSnapshots), [gitRuns, jiraSnapshots]);

  return { dataset, liveTotals, isSyncing, syncError };
}
