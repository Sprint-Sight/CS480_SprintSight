import type { QueryClient } from "@tanstack/react-query";

import { apiRequest } from "@/lib/api/client";
import { getStudentProjects } from "@/features/student/student-project-api";

export const PROJECTS_CACHE_STALE_MS = 60_000;

export type Course = {
  id: string;
  code: string;
  name: string;
  section: string;
  term: string;
  year: number;
};

export type CourseProject = {
  id: string;
  team_name: string;
  project_name: string;
  jira_project_key: string | null;
  members: unknown[];
};

export type CourseProjectGroup = { course: Course; projects: CourseProject[] };

export const projectQueryKeys = {
  courses: ["courses"] as const,
  courseProjects: (courseId: string) => ["courses", courseId, "projects"] as const,
  scope: ["scope-projects"] as const,
  student: ["student-projects"] as const,
};

export function coursesQueryOptions() {
  return {
    queryKey: projectQueryKeys.courses,
    queryFn: () => apiRequest<Course[]>("/courses"),
    staleTime: PROJECTS_CACHE_STALE_MS,
  };
}

export function courseProjectsQueryOptions(courseId: string) {
  return {
    queryKey: projectQueryKeys.courseProjects(courseId),
    queryFn: () => apiRequest<CourseProject[]>(`/courses/${encodeURIComponent(courseId)}/projects`),
    staleTime: PROJECTS_CACHE_STALE_MS,
  };
}

/** Every course for the instructor, each paired with its projects. Built on the per-course cache entries. */
export function scopeProjectsQueryOptions(queryClient: QueryClient) {
  return {
    queryKey: projectQueryKeys.scope,
    queryFn: async (): Promise<CourseProjectGroup[]> => {
      const courses = await queryClient.fetchQuery(coursesQueryOptions());
      return Promise.all(
        courses.map(async (course) => ({
          course,
          projects: await queryClient.fetchQuery(courseProjectsQueryOptions(course.id)),
        })),
      );
    },
    staleTime: PROJECTS_CACHE_STALE_MS,
  };
}

export function studentProjectsQueryOptions() {
  return {
    queryKey: projectQueryKeys.student,
    queryFn: getStudentProjects,
    staleTime: PROJECTS_CACHE_STALE_MS,
  };
}

/** Call after any course or project create, update, or delete. */
export function invalidateProjectCaches(queryClient: QueryClient) {
  return Promise.all([
    queryClient.invalidateQueries({ queryKey: projectQueryKeys.courses }),
    queryClient.invalidateQueries({ queryKey: projectQueryKeys.scope }),
    queryClient.invalidateQueries({ queryKey: projectQueryKeys.student }),
  ]);
}
