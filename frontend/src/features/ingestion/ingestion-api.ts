import type { QueryClient } from "@tanstack/react-query";

import { apiRequest, getErrorMessage } from "@/lib/api/client";
import { fetchProjectGitRuns } from "@/features/artifacts/git-runs-api";
import type { JiraIngestionRun } from "@/features/artifacts/components/jira-ingestion-runs-table";
import { scopeProjectsQueryOptions } from "@/features/projects/course-projects-api";
import type { PersistedGitMetrics, PersistedJiraSnapshot } from "@/features/ingestion/types";

/** ProjectResponse has no course_id, so find the course that owns the project in the shared cache. */
export async function resolveProjectCourseId(
  projectId: string,
  queryClient: QueryClient,
): Promise<string | null> {
  const groups = await queryClient.fetchQuery(scopeProjectsQueryOptions(queryClient));
  return (
    groups.find(({ projects }) => projects.some((project) => project.id === projectId))?.course
      .id ?? null
  );
}

export function fetchProjectJiraRuns(projectId: string): Promise<JiraIngestionRun[]> {
  return apiRequest<JiraIngestionRun[]>(`/jira-ingestion/runs/${encodeURIComponent(projectId)}`);
}

/** Latest completed, cleaned Jira snapshot for every sprint in the given runs. */
export async function fetchJiraSnapshotsForRuns(
  runs: JiraIngestionRun[],
): Promise<PersistedJiraSnapshot[]> {
  const latestBySprint = new Map<string, JiraIngestionRun>();
  runs
    .filter((run) => run.processing_status === "completed")
    .forEach((run) => {
      const current = latestBySprint.get(run.sprint_id);
      if (!current || run.captured_at.localeCompare(current.captured_at) > 0)
        latestBySprint.set(run.sprint_id, run);
    });

  return Promise.all(
    [...latestBySprint.values()].map((run) =>
      apiRequest<PersistedJiraSnapshot>(
        `/jira-ingestion/runs/${encodeURIComponent(run.project_id)}/${encodeURIComponent(run.sprint_id)}/${encodeURIComponent(run.run_id)}/cleaned`,
      ),
    ),
  );
}

/** Latest completed, cleaned Jira snapshot for every sprint of the project. */
export async function fetchProjectJiraSnapshots(
  projectId: string,
): Promise<PersistedJiraSnapshot[]> {
  return fetchJiraSnapshotsForRuns(await fetchProjectJiraRuns(projectId));
}

export type ProjectIngestionFetchResult = {
  gitRuns: PersistedGitMetrics[];
  jiraSnapshots: PersistedJiraSnapshot[];
  errors: string[];
};

/** Loads Git and Jira runs independently so one failing source does not hide the other. */
export async function fetchProjectIngestion(
  projectId: string,
  courseId: string,
  knownGitSprintIds: string[],
): Promise<ProjectIngestionFetchResult> {
  // The Git loader can only probe sprint-1, sprint-2, ... until the first gap, so load the
  // Jira run list first and pass every sprint it names. A project synced only at sprint-4,
  // or with sprint-2 skipped, then still finds its Git runs.
  const jiraRuns = await fetchProjectJiraRuns(projectId).then(
    (runs) => ({ ok: true as const, runs }),
    (error: unknown) => ({ ok: false as const, error }),
  );
  const sprintIds = [
    ...new Set([
      ...knownGitSprintIds,
      ...(jiraRuns.ok ? jiraRuns.runs.map((run) => run.sprint_id) : []),
    ]),
  ];

  const [git, jira] = await Promise.allSettled([
    fetchProjectGitRuns<PersistedGitMetrics>(projectId, courseId, sprintIds),
    jiraRuns.ok ? fetchJiraSnapshotsForRuns(jiraRuns.runs) : Promise.reject(jiraRuns.error),
  ]);

  const errors: string[] = [];
  if (git.status === "rejected")
    errors.push(getErrorMessage(git.reason, "Could not load Git data."));
  if (jira.status === "rejected")
    errors.push(getErrorMessage(jira.reason, "Could not load Jira data."));

  return {
    gitRuns: git.status === "fulfilled" ? git.value : [],
    jiraSnapshots: jira.status === "fulfilled" ? jira.value : [],
    errors,
  };
}
