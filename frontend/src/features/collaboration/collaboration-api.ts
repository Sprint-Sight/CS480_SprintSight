import { apiRequest } from "@/features/projects/components/projects-api";
import { fetchProjectGitRuns } from "@/features/artifacts/git-runs-api";
import type {
  IngestionState,
  PersistedGitMetrics,
  PersistedJiraSnapshot,
} from "@/features/ingestion/state";
import { aggregateProjectSprints } from "@/features/collaboration/aggregate-project-sprints";

type Course = { id: string };
type CourseProject = { id: string; project_name: string; team_name: string };
type ProjectDetails = {
  id: string;
  project_name: string;
  team_name: string;
  members: Array<{ id: string; full_name: string }>;
};
type JiraRun = {
  run_id: string;
  project_id: string;
  sprint_id: string;
  processing_status: "pending" | "completed" | "failed";
};

export type CollaborationProjectData = {
  projectLabel: string;
  memberNames: Map<string, string>;
  ingestion: ReturnType<typeof aggregateProjectSprints>;
};

export async function fetchCollaborationProjectData(
  projectId: string,
  cachedState: IngestionState,
): Promise<CollaborationProjectData> {
  const courses = await apiRequest<Course[]>("/courses");
  const projectGroups = await Promise.all(
    courses.map(async (course) => ({
      courseId: course.id,
      projects: await apiRequest<CourseProject[]>(`/courses/${encodeURIComponent(course.id)}/projects`),
    })),
  );
  const courseId = projectGroups.find(({ projects }) =>
    projects.some((project) => project.id === projectId),
  )?.courseId;
  if (!courseId) {
    throw new Error("The selected project is not available in your instructor scope.");
  }

  const [project, jiraRuns] = await Promise.all([
    apiRequest<ProjectDetails>(`/projects/${encodeURIComponent(projectId)}`),
    apiRequest<JiraRun[]>(`/jira-ingestion/runs/${encodeURIComponent(projectId)}`),
  ]);
  const cachedSprintIds = Object.values(cachedState.gitBySprint)
    .filter((run) => run.project_id === projectId)
    .map((run) => run.sprint_id);
  const knownSprintIds = [
    ...new Set([...cachedSprintIds, ...jiraRuns.map((run) => run.sprint_id)]),
  ];
  const gitRuns = await fetchProjectGitRuns<PersistedGitMetrics>(
    projectId,
    courseId,
    knownSprintIds,
  );
  const completedJiraRuns = jiraRuns.filter(
    (run) => run.project_id === projectId && run.processing_status === "completed",
  );
  const jiraSnapshots = await Promise.all(
    completedJiraRuns.map((run) =>
      apiRequest<PersistedJiraSnapshot>(
        `/jira-ingestion/runs/${encodeURIComponent(projectId)}/${encodeURIComponent(run.sprint_id)}/${encodeURIComponent(run.run_id)}/cleaned`,
      ),
    ),
  );

  const state: IngestionState = {
    ...cachedState,
    selectedProjectId: projectId,
    gitBySprint: Object.fromEntries(
      gitRuns.map((run) => [`${projectId}:${run.sprint_id}`, run]),
    ),
    jiraBySprint: Object.fromEntries(
      jiraSnapshots.map((snapshot, index) => [
        `${projectId}:${snapshot.sprint_id}:${completedJiraRuns[index].run_id}`,
        snapshot,
      ]),
    ),
  };
  return {
    projectLabel: `${project.team_name} - ${project.project_name}`,
    memberNames: new Map(project.members.map((member) => [member.id, member.full_name])),
    ingestion: aggregateProjectSprints(state, projectId),
  };
}
