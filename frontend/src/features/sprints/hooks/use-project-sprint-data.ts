"use client";

import { useEffect, useMemo, useState } from "react";

import { useIngestionScope } from "@/features/ingestion/hooks/use-ingestion-scope";
import { apiRequest, getErrorMessage } from "@/lib/api/client";
import { useIngestionSync } from "@/features/ingestion/hooks/use-ingestion-sync";

type BackendProject = { id: string; project_name: string; team_name: string; course_code: string };
export type ProjectSprintRun = { id: string; name: string; commits: number; capturedAt: string };

export function useProjectSprintData(projectId: string) {
  const [project, setProject] = useState<BackendProject | null>(null);
  const [error, setError] = useState("");
  const { scope } = useIngestionScope();
  // Reuse the scope's course when it owns this project; otherwise the hook resolves it.
  const scopeCourseId = scope.selectedProjectId === projectId ? scope.selectedCourseId || undefined : undefined;
  const { gitRuns, isSyncing, syncError } = useIngestionSync({ projectId, courseId: scopeCourseId });
  const sprints = useMemo<ProjectSprintRun[]>(
    () =>
      gitRuns.map((run) => ({
        id: run.sprint_id,
        name: run.sprint_id,
        commits: run.pagination?.total ?? run.commits.length,
        capturedAt: run.captured_at,
      })),
    [gitRuns],
  );

  useEffect(() => {
    async function loadProject() {
      setError("");
      try { setProject(await apiRequest<BackendProject>(`/projects/${projectId}`)); }
      catch (loadError) { setError(getErrorMessage(loadError, "Failed to load project.")); }
    }
    void loadProject();
  }, [projectId]);

  return { project, sprints, error, isSyncing, syncError };
}