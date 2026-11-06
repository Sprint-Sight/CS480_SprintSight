"use client";

import { useEffect, useMemo, useState } from "react";

import { useScopeProjects, useStudentProjects } from "@/features/projects/hooks/use-course-projects";
import { readScope, subscribeScope } from "@/features/ingestion/scope-store";
import { getErrorMessage } from "@/lib/api/client";

export type ArtifactProjectOption = {
  id: string;
  courseId?: string;
  jiraProjectKey?: string | null;
  label: string;
};

export function useArtifactProjectScope(role: "student" | "instructor" | null) {
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const instructorScope = useScopeProjects(role === "instructor");
  const studentScope = useStudentProjects(role === "student");

  const projectOptions = useMemo<ArtifactProjectOption[]>(() => {
    if (role === "student") {
      return (studentScope.data ?? []).map((project) => ({
        id: project.id,
        label: `${project.team_name} - ${project.project_name}`,
      }));
    }
    if (role !== "instructor") return [];
    return (instructorScope.data ?? []).flatMap(({ course, projects }) => projects.map((project) => ({
      id: project.id,
      courseId: course.id,
      jiraProjectKey: project.jira_project_key,
      label: `${project.team_name} - ${project.project_name}`,
    })));
  }, [role, instructorScope.data, studentScope.data]);

  useEffect(() => {
    if (role === "student") {
      setSelectedProjectId((current) => (projectOptions.some((project) => project.id === current) ? current : projectOptions[0]?.id || ""));
      return;
    }
    if (role !== "instructor") return;
    const savedProjectId = readScope().selectedProjectId;
    setSelectedProjectId(projectOptions.some((project) => project.id === savedProjectId)
      ? savedProjectId
      : projectOptions[0]?.id || "");
  }, [role, projectOptions]);

  useEffect(() => {
    if (role !== "instructor") return;
    const refreshSelectedProject = () => {
      setSelectedProjectId(readScope().selectedProjectId);
    };
    refreshSelectedProject();
    return subscribeScope(refreshSelectedProject);
  }, [role]);

  const activeQuery = role === "student" ? studentScope : instructorScope;
  const isLoadingProjects = role ? activeQuery.isPending : true;
  const projectLoadError = activeQuery.error ? getErrorMessage(activeQuery.error, "Could not load backend projects.") : "";

  return { projectOptions, selectedProjectId, isLoadingProjects, projectLoadError };
}
