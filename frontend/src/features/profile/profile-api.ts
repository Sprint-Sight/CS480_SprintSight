import type { QueryClient } from "@tanstack/react-query";

import {
  courseProjectsQueryOptions,
  coursesQueryOptions,
} from "@/features/projects/course-projects-api";

export type TeachingSummary = {
  activeSectionsCount: number;
  teamsMonitoredCount: number;
};

/** Courses and their projects visible to an instructor/admin (GET /courses is faculty-only). */
export async function getTeachingSummary(queryClient: QueryClient): Promise<TeachingSummary> {
  const courses = await queryClient.fetchQuery(coursesQueryOptions());
  const projectLists = await Promise.all(
    courses.map((course) =>
      queryClient.fetchQuery(courseProjectsQueryOptions(course.id)).catch(() => []),
    ),
  );
  return {
    activeSectionsCount: courses.length,
    teamsMonitoredCount: projectLists.reduce((total, projects) => total + projects.length, 0),
  };
}
