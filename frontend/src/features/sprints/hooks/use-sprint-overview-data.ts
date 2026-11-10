"use client";

import { useMemo } from "react";

import { useIngestionScope } from "@/features/ingestion/hooks/use-ingestion-scope";
import { useIngestionSync } from "@/features/ingestion/hooks/use-ingestion-sync";
import { sprintLabel } from "@/features/ingestion/scope-options";
import { summarizeIngestionRuns } from "@/features/ingestion/ingestion-query";
import { useScopeProjects } from "@/features/projects/hooks/use-course-projects";
import type { SprintOverviewPayload, SprintOverviewRow } from "@/features/sprints/types";

const EMPTY_LABEL = "—";

export function useSprintOverviewData() {
  const { scope } = useIngestionScope();
  const selectedProjectId = scope.selectedProjectId || "";
  const { gitRuns, jiraSnapshots, isSyncing, syncError } = useIngestionSync({
    projectId: selectedProjectId,
    courseId: scope.selectedCourseId || undefined,
  });
  const scopeQuery = useScopeProjects();

  const projectInfo = useMemo(
    () =>
      scopeQuery.data
        ?.flatMap(({ projects }) => projects)
        .find((project) => project.id === selectedProjectId),
    [scopeQuery.data, selectedProjectId],
  );
  const projectName = projectInfo?.project_name || EMPTY_LABEL;
  const projectTeam = projectInfo?.team_name || EMPTY_LABEL;

  // This page intentionally aggregates every captured sprint for the selected project.
  const payload = useMemo<SprintOverviewPayload | null>(() => {
    if (!selectedProjectId) return null;
    const sprintIds = [
      ...new Set([
        ...gitRuns.map((run) => run.sprint_id),
        ...jiraSnapshots.map((snapshot) => snapshot.sprint_id),
      ]),
    ];
    if (!sprintIds.length) return null;

    const rows: SprintOverviewRow[] = sprintIds.map((sprintId) => {
      const git = gitRuns.find((run) => run.sprint_id === sprintId);
      const jira = jiraSnapshots.find((snapshot) => snapshot.sprint_id === sprintId);
      const completion = git?.completion_percent ?? null;
      const isCompleted = completion !== null && completion >= 100;
      return {
        projectId: selectedProjectId,
        projectName,
        projectTeam,
        sprint: {
          id: sprintId,
          name: sprintLabel(sprintId),
          status: isCompleted ? "Completed" : "On Track",
          completion,
          capturedAt: git?.captured_at || jira?.captured_at || "",
        },
        activity: {
          commits: git ? (git.pagination?.total ?? git.commits.length) : 0,
          tasks: jira?.tickets.length ?? 0,
        },
        isCompleted,
        isOngoing: !isCompleted,
        displayStatus: isCompleted ? "Completed" : "In Progress",
      };
    });

    return {
      project: { id: selectedProjectId, name: projectName },
      rows,
      summary: {
        totalCommits: rows.reduce((total, row) => total + row.activity.commits, 0),
        totalTasks: rows.reduce((total, row) => total + row.activity.tasks, 0),
      },
    };
  }, [selectedProjectId, gitRuns, jiraSnapshots, projectName, projectTeam]);

  const liveTotals = useMemo(
    () => summarizeIngestionRuns(gitRuns, jiraSnapshots),
    [gitRuns, jiraSnapshots],
  );

  return { selectedProjectId, payload, liveTotals, isSyncing, syncError };
}
