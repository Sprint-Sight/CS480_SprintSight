"use client";

import { useEffect, useState } from "react";

import { readIngestionState } from "@/features/ingestion/state";
import { apiRequest } from "@/features/projects/components/projects-api";

export type ArtifactProjectOption = {
  id: string;
  courseId: string;
  jiraProjectKey?: string | null;
  label: string;
};

type Course = { id: string };
type Project = { id: string; team_name: string; project_name: string; jira_project_key: string | null };

export function useArtifactProjectScope(role: "student" | "instructor" | null) {
  const [projectOptions, setProjectOptions] = useState<ArtifactProjectOption[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState(() => readIngestionState().selectedProjectId || "");
  const [isLoadingProjects, setIsLoadingProjects] = useState(false);
  const [projectLoadError, setProjectLoadError] = useState("");

  useEffect(() => {
    const refreshScope = () => setSelectedProjectId(readIngestionState().selectedProjectId || "");
    window.addEventListener("sprintsight-ingestion-updated", refreshScope);
    return () => window.removeEventListener("sprintsight-ingestion-updated", refreshScope);
  }, []);

  useEffect(() => {
    if (role !== "instructor") return;
    async function loadProjects() {
      setIsLoadingProjects(true);
      setProjectLoadError("");
      try {
        const courses = await apiRequest<Course[]>("/courses");
        const groups = await Promise.all(courses.map(async (course) => ({
          courseId: course.id,
          projects: await apiRequest<Project[]>(`/courses/${course.id}/projects`),
        })));
        setProjectOptions(groups.flatMap(({ courseId, projects }) => projects.map((project) => ({
          id: project.id,
          courseId,
          jiraProjectKey: project.jira_project_key,
          label: `${project.team_name} - ${project.project_name}`,
        }))));
      } catch (error) {
        setProjectOptions([]);
        setProjectLoadError(error instanceof Error ? error.message : "Could not load backend projects.");
      } finally {
        setIsLoadingProjects(false);
      }
    }
    void loadProjects();
  }, [role]);

  return { projectOptions, selectedProjectId, isLoadingProjects, projectLoadError };
}