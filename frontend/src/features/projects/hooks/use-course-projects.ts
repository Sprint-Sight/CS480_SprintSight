"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";

import {
  courseProjectsQueryOptions,
  coursesQueryOptions,
  scopeProjectsQueryOptions,
  studentProjectsQueryOptions,
} from "@/features/projects/course-projects-api";

export function useCourses(enabled = true) {
  return useQuery({ ...coursesQueryOptions(), enabled });
}

export function useCourseProjects(courseId: string | null | undefined) {
  return useQuery({
    ...courseProjectsQueryOptions(courseId ?? ""),
    enabled: Boolean(courseId),
  });
}

export function useScopeProjects(enabled = true) {
  const queryClient = useQueryClient();
  return useQuery({ ...scopeProjectsQueryOptions(queryClient), enabled });
}

export function useStudentProjects(enabled = true) {
  return useQuery({ ...studentProjectsQueryOptions(), enabled });
}
