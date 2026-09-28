"use client";

import { useEffect, useMemo, useState } from "react";

import { getProjectGitMetrics, readIngestionState } from "@/features/ingestion/state";
import { apiRequest } from "@/features/projects/components/projects-api";

type BackendProject = { id: string; project_name: string; team_name: string; course_code: string };
export type ProjectSprintRun = { id: string; name: string; commits: number; capturedAt: string };

export function useProjectSprintData(projectId: string) {
  const [project, setProject] = useState<BackendProject | null>(null);
  const [error, setError] = useState("");
  const [ingestionVersion, setIngestionVersion] = useState(0);
  const sprints = useMemo<ProjectSprintRun[]>(() => {
    void ingestionVersion;
    return getProjectGitMetrics(projectId).map((run) => ({ id: run.sprint_id, name: run.sprint_id, commits: run.pagination?.total ?? run.commits.length, capturedAt: run.captured_at }));
  }, [projectId, ingestionVersion]);

  useEffect(() => {
    async function loadProject() {
      setError("");
      try { setProject(await apiRequest<BackendProject>(`/projects/${projectId}`)); }
      catch (loadError) { setError(loadError instanceof Error ? loadError.message : "Failed to load project."); }
    }
    void loadProject();
  }, [projectId]);

  useEffect(() => {
    const refresh = () => setIngestionVersion((version) => version + 1);
    window.addEventListener("sprintsight-ingestion-updated", refresh);
    return () => window.removeEventListener("sprintsight-ingestion-updated", refresh);
  }, []);

  return { project, sprints, error };
}