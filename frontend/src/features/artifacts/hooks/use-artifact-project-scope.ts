"use client";

import { useEffect, useState } from "react";

import { readIngestionState } from "@/features/ingestion/state";
import { apiRequest } from "@/features/projects/components/projects-api";
import { PROJECTS_UPDATED_EVENT } from "@/features/projects/projects-events";
import { getStudentProjects } from "@/features/student/student-project-api";

export type ArtifactProjectOption = {
  id: string;
  courseId?: string;
  jiraProjectKey?: string | null;
  label: string;
};

type Course = { id: string };
type Project = { id: string; team_name: string; project_name: string; jira_project_key: string | null };

export function useArtifactProjectScope(role: "student" | "instructor" | null) {
  const [projectOptions, setProjectOptions] = useState<ArtifactProjectOption[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [isLoadingProjects, setIsLoadingProjects] = useState(true);
  const [projectLoadError, setProjectLoadError] = useState("");

  useEffect(() => {
    if (role !== "instructor") return;
    const refreshSelectedProject = () => {
      setSelectedProjectId(readIngestionState().selectedProjectId || "");
    };
    refreshSelectedProject();
    window.addEventListener("sprintsight-ingestion-updated", refreshSelectedProject);
    return () => window.removeEventListener("sprintsight-ingestion-updated", refreshSelectedProject);
  }, [role]);

  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    if (!role) return;
    const refresh = () => { if (document.visibilityState !== "hidden") setRefreshKey((key) => key + 1); };
    window.addEventListener("focus", refresh);
    document.addEventListener("visibilitychange", refresh);
    window.addEventListener(PROJECTS_UPDATED_EVENT, refresh);
    return () => {
      window.removeEventListener("focus", refresh);
      document.removeEventListener("visibilitychange", refresh);
      window.removeEventListener(PROJECTS_UPDATED_EVENT, refresh);
    };
  }, [role]);

  useEffect(() => {
    if (!role) return;
    let cancelled = false;
    async function loadProjects() {
      if (refreshKey === 0) setIsLoadingProjects(true);
      setProjectLoadError("");
      try {
        if (role === "student") {
          const projects = await getStudentProjects();
          if (cancelled) return;
          const options = projects.map((project) => ({
            id: project.id,
            label: `${project.team_name} - ${project.project_name}`,
          }));
          setProjectOptions(options);
          setSelectedProjectId((current) => (options.some((project) => project.id === current) ? current : options[0]?.id || ""));
          return;
        }

        const courses = await apiRequest<Course[]>("/courses");
        const groups = await Promise.all(courses.map(async (course) => ({
          courseId: course.id,
          projects: await apiRequest<Project[]>(`/courses/${course.id}/projects`),
        })));
        if (cancelled) return;
        const options = groups.flatMap(({ courseId, projects }) => projects.map((project) => ({
          id: project.id,
          courseId,
          jiraProjectKey: project.jira_project_key,
          label: `${project.team_name} - ${project.project_name}`,
        })));
        setProjectOptions(options);
        const persisted = readIngestionState();
        const savedProjectId = persisted.selectedProjectId || "";
        setSelectedProjectId(options.some((project) => project.id === savedProjectId)
          ? savedProjectId
          : options[0]?.id || "");
      } catch (error) {
        if (cancelled) return;
        setProjectOptions([]);
        if (role === "student") setSelectedProjectId("");
        setProjectLoadError(error instanceof Error ? error.message : "Could not load backend projects.");
      } finally {
        if (!cancelled) setIsLoadingProjects(false);
      }
    }
    void loadProjects();
    return () => { cancelled = true; };
  }, [role, refreshKey]);

  return { projectOptions, selectedProjectId, isLoadingProjects, projectLoadError };
}