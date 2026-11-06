"use client";

import { useMemo } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { isUuid } from "@/features/projects/components/projects-api";
import { scopeProjectsQueryOptions } from "@/features/projects/course-projects-api";
import { indexIngestionRuns, projectIngestionQueryOptions } from "@/features/ingestion/ingestion-query";
import { getErrorMessage } from "@/lib/api/client";

type UseIngestionSyncOptions = {
  projectId: string;
  /** Optional; resolved from the shared course cache when not known (e.g. deep links). */
  courseId?: string;
  enabled?: boolean;
};

/**
 * Loads the project's Git and Jira runs through the query cache. Pages read from the
 * returned `runs` index, so they work on a fresh browser without visiting the Artifact Viewer.
 */
export function useIngestionSync({ projectId, courseId, enabled = true }: UseIngestionSyncOptions) {
  const queryClient = useQueryClient();
  const canQuery = enabled && isUuid(projectId);

  const scopeQuery = useQuery({
    ...scopeProjectsQueryOptions(queryClient),
    enabled: canQuery && !courseId,
  });
  const resolvedCourseId =
    courseId ||
    scopeQuery.data?.find(({ projects }) => projects.some((project) => project.id === projectId))?.course.id ||
    "";

  const ingestionQuery = useQuery({
    ...projectIngestionQueryOptions(projectId, resolvedCourseId),
    enabled: canQuery && Boolean(resolvedCourseId),
  });

  const runs = useMemo(() => indexIngestionRuns(ingestionQuery.data), [ingestionQuery.data]);

  const courseMissing = canQuery && !courseId && scopeQuery.isSuccess && !resolvedCourseId;
  const syncError = courseMissing
    ? "Could not find the course for this project."
    : ingestionQuery.error
      ? getErrorMessage(ingestionQuery.error, "Could not load ingestion data.")
      : (ingestionQuery.data?.errors.join(" ") ?? "");

  return {
    runs,
    gitRuns: ingestionQuery.data?.gitRuns ?? [],
    jiraSnapshots: ingestionQuery.data?.jiraSnapshots ?? [],
    isSyncing: ingestionQuery.isFetching || scopeQuery.isFetching,
    syncError,
    refetch: ingestionQuery.refetch,
  };
}
