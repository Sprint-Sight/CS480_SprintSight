import { apiRequest, getErrorMessage } from "@/lib/api/client";
import { fetchProjectGitRuns } from "@/features/artifacts/git-runs-api";
import type { JiraIngestionRun } from "@/features/artifacts/components/jira-ingestion-runs-table";
import type { PersistedGitMetrics, PersistedJiraSnapshot } from "@/features/ingestion/state";

type CourseSummary = { id: string };
type CourseProjectSummary = { id: string };

/** ProjectResponse has no course_id, so find the course that owns the project. */
export async function resolveProjectCourseId(projectId: string): Promise<string | null> {
  const courses = await apiRequest<CourseSummary[]>("/courses");
  for (const course of courses) {
    const projects = await apiRequest<CourseProjectSummary[]>(`/courses/${encodeURIComponent(course.id)}/projects`);
    if (projects.some((project) => project.id === projectId)) return course.id;
  }
  return null;
}

/** Latest completed, cleaned Jira snapshot for every sprint of the project. */
export async function fetchProjectJiraSnapshots(projectId: string): Promise<PersistedJiraSnapshot[]> {
  const runs = await apiRequest<JiraIngestionRun[]>(`/jira-ingestion/runs/${encodeURIComponent(projectId)}`);
  const latestBySprint = new Map<string, JiraIngestionRun>();
  runs
    .filter((run) => run.processing_status === "completed")
    .forEach((run) => {
      const current = latestBySprint.get(run.sprint_id);
      if (!current || run.captured_at.localeCompare(current.captured_at) > 0) latestBySprint.set(run.sprint_id, run);
    });

  return Promise.all(
    [...latestBySprint.values()].map((run) =>
      apiRequest<PersistedJiraSnapshot>(
        `/jira-ingestion/runs/${encodeURIComponent(run.project_id)}/${encodeURIComponent(run.sprint_id)}/${encodeURIComponent(run.run_id)}/cleaned`,
      ),
    ),
  );
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
  const [git, jira] = await Promise.allSettled([
    fetchProjectGitRuns<PersistedGitMetrics>(projectId, courseId, knownGitSprintIds),
    fetchProjectJiraSnapshots(projectId),
  ]);

  const errors: string[] = [];
  if (git.status === "rejected") errors.push(getErrorMessage(git.reason, "Could not load Git data."));
  if (jira.status === "rejected") errors.push(getErrorMessage(jira.reason, "Could not load Jira data."));

  return {
    gitRuns: git.status === "fulfilled" ? git.value : [],
    jiraSnapshots: jira.status === "fulfilled" ? jira.value : [],
    errors,
  };
}
