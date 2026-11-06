"use client";

import { useEffect, useState } from "react";

import { isUuid } from "@/features/projects/components/projects-api";
import { getProjectGitMetrics, mergeIngestionRuns } from "@/features/ingestion/state";
import { fetchProjectIngestion, resolveProjectCourseId } from "@/features/ingestion/ingestion-api";
import { getErrorMessage } from "@/lib/api/client";

type UseIngestionSyncOptions = {
  projectId: string;
  /** Optional; resolved from the course list when not known (e.g. deep links). */
  courseId?: string;
  enabled?: boolean;
};

/**
 * Pulls the project's Git and Jira runs from the backend into the shared ingestion
 * store, so pages that derive their view from that store work on a fresh browser
 * instead of only after the Artifact Viewer has been opened.
 */
export function useIngestionSync({ projectId, courseId, enabled = true }: UseIngestionSyncOptions) {
  const [isSyncing, setIsSyncing] = useState(false);
  const [syncError, setSyncError] = useState("");

  useEffect(() => {
    if (!enabled || !isUuid(projectId)) {
      setIsSyncing(false);
      setSyncError("");
      return;
    }

    let isCurrent = true;
    setIsSyncing(true);
    setSyncError("");

    async function sync() {
      try {
        const resolvedCourseId = courseId || (await resolveProjectCourseId(projectId));
        if (!isCurrent) return;
        if (!resolvedCourseId) {
          setSyncError("Could not find the course for this project.");
          return;
        }

        const knownSprintIds = getProjectGitMetrics(projectId).map((run) => run.sprint_id);
        const result = await fetchProjectIngestion(projectId, resolvedCourseId, knownSprintIds);
        if (!isCurrent) return;

        mergeIngestionRuns(result.gitRuns, result.jiraSnapshots);
        setSyncError(result.errors.join(" "));
      } catch (error) {
        if (isCurrent) setSyncError(getErrorMessage(error, "Could not load ingestion data."));
      } finally {
        if (isCurrent) setIsSyncing(false);
      }
    }

    void sync();
    return () => {
      isCurrent = false;
    };
  }, [projectId, courseId, enabled]);

  return { isSyncing, syncError };
}
