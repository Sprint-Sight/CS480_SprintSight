"use client";

import { useMemo } from "react";

import { useIngestionScope } from "@/features/ingestion/hooks/use-ingestion-scope";
import { useIngestionSync } from "@/features/ingestion/hooks/use-ingestion-sync";
import { summarizeIngestionRuns } from "@/features/ingestion/ingestion-query";
import { sprintLabel } from "@/features/ingestion/scope-options";
import { useScopeProjects } from "@/features/projects/hooks/use-course-projects";
import type { ContributionDataset } from "@/features/contributions/types";
import { useSession } from "@/lib/auth/session";

const EMPTY_LABEL = "—";

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
  // Same cached course/project list the scope bar uses, so this adds no extra request.
  const scopeQuery = useScopeProjects(canSync);

  const project = useMemo(
    () =>
      scopeQuery.data
        ?.flatMap(({ projects }) => projects)
        .find((candidate) => candidate.id === selectedProjectId),
    [scopeQuery.data, selectedProjectId],
  );

  const dataset = useMemo<ContributionDataset>(
    () => ({
      projectId: selectedProjectId,
      teamLabel: project?.team_name || EMPTY_LABEL,
      projectLabel: project?.project_name || EMPTY_LABEL,
      sprintLabel: scope.selectedSprintId ? sprintLabel(scope.selectedSprintId) : EMPTY_LABEL,
      members: [],
    }),
    [selectedProjectId, project, scope.selectedSprintId],
  );
  const liveTotals = useMemo(
    () => summarizeIngestionRuns(gitRuns, jiraSnapshots),
    [gitRuns, jiraSnapshots],
  );

  return { dataset, liveTotals, isSyncing, syncError };
}
