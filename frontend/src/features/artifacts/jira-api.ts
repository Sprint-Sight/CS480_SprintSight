import { apiRequest } from "@/lib/api/client";
import type { JiraIngestionRun } from "@/features/artifacts/types";

export type JiraSprint = {
  id: string | number;
  name: string | null;
  state: string | null;
  start_date: string | null;
  end_date: string | null;
};

export type JiraRunIdentity = Pick<JiraIngestionRun, "project_id" | "sprint_id" | "run_id">;

export function fetchJiraRuns(projectId: string, signal?: AbortSignal) {
  return apiRequest<JiraIngestionRun[]>(`/jira-ingestion/runs/${projectId}`, { signal });
}

export function fetchJiraSprints(projectId: string, signal?: AbortSignal) {
  return apiRequest<JiraSprint[]>(`/jira-ingestion/sprints/${projectId}`, { signal });
}

export function deleteJiraRun(run: JiraRunIdentity) {
  return apiRequest<null>(
    `/jira-ingestion/runs/${run.project_id}/${encodeURIComponent(run.sprint_id)}/${run.run_id}`,
    { method: "DELETE" },
  );
}
