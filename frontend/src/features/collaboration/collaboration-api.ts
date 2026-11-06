import type { QueryClient } from "@tanstack/react-query";

import { apiRequest } from "@/lib/api/client";
import { scopeProjectsQueryOptions } from "@/features/projects/course-projects-api";
import { indexIngestionRuns, projectIngestionQueryOptions } from "@/features/ingestion/ingestion-query";
import { aggregateProjectSprints } from "@/features/collaboration/aggregate-project-sprints";

type ProjectDetails = {
  id: string;
  project_name: string;
  team_name: string;
  members: Array<{ id: string; full_name: string }>;
};

export type CollaborationProjectData = {
  projectLabel: string;
  memberNames: Map<string, string>;
  ingestion: ReturnType<typeof aggregateProjectSprints>;
};

export async function fetchCollaborationProjectData(
  projectId: string,
  queryClient: QueryClient,
): Promise<CollaborationProjectData> {
  const projectGroups = await queryClient.fetchQuery(scopeProjectsQueryOptions(queryClient));
  const courseId = projectGroups.find(({ projects }) =>
    projects.some((project) => project.id === projectId),
  )?.course.id;
  if (!courseId) {
    throw new Error("The selected project is not available in your instructor scope.");
  }

  const [project, ingestion] = await Promise.all([
    apiRequest<ProjectDetails>(`/projects/${encodeURIComponent(projectId)}`),
    queryClient.fetchQuery(projectIngestionQueryOptions(projectId, courseId)),
  ]);
  return {
    projectLabel: `${project.team_name} - ${project.project_name}`,
    memberNames: new Map(project.members.map((member) => [member.id, member.full_name])),
    ingestion: aggregateProjectSprints(indexIngestionRuns(ingestion), projectId),
  };
}
