"use client";

import { useMemo } from "react";

import { useIngestionScope } from "@/features/ingestion/hooks/use-ingestion-scope";
import { useIngestionSync } from "@/features/ingestion/hooks/use-ingestion-sync";
import { summarizeIngestionRuns } from "@/features/ingestion/ingestion-query";
import { useSession } from "@/lib/auth/session";

export function useProgressData() {
  const session = useSession();
  const role: "student" | "instructor" | null = session ? (session.user?.role === "instructor" ? "instructor" : "student") : null;
  const { scope } = useIngestionScope();
  const selectedProjectId = scope.selectedProjectId || "";
  const { gitRuns, jiraSnapshots, isSyncing, syncError } = useIngestionSync({
    projectId: selectedProjectId,
    courseId: scope.selectedCourseId || undefined,
    enabled: role === "instructor",
  });
  const progressSignals = useMemo(() => summarizeIngestionRuns(gitRuns, jiraSnapshots), [gitRuns, jiraSnapshots]);

  return { role, progressSignals, isSyncing, syncError };
}
