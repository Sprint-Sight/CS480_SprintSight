import type { IngestionRunIndex, PersistedGitMetrics, PersistedJiraSnapshot } from "@/features/ingestion/types";
import type { ProjectIngestionFetchResult } from "@/features/ingestion/ingestion-api";
import { fetchProjectIngestion } from "@/features/ingestion/ingestion-api";

export const INGESTION_STALE_MS = 60_000;

export const ingestionQueryKeys = {
  project: (projectId: string) => ["ingestion", projectId] as const,
};

export function projectIngestionQueryOptions(projectId: string, courseId: string) {
  return {
    queryKey: [...ingestionQueryKeys.project(projectId), courseId] as const,
    queryFn: async (): Promise<ProjectIngestionFetchResult> => {
      const result = await fetchProjectIngestion(projectId, courseId, []);
      if (result.errors.length > 0 && result.gitRuns.length === 0 && result.jiraSnapshots.length === 0) {
        throw new Error(result.errors.join(" "));
      }
      return result;
    },
    staleTime: INGESTION_STALE_MS,
  };
}

export type IngestionTotals = {
  hasData: boolean;
  gitCommits: number;
  codeChurn: number;
  jiraTickets: number;
};

/** Totals across a project's loaded runs, shared by the sprint, contribution, and progress pages. */
export function summarizeIngestionRuns(
  gitRuns: PersistedGitMetrics[],
  jiraSnapshots: PersistedJiraSnapshot[],
): IngestionTotals {
  return {
    hasData: gitRuns.length > 0 || jiraSnapshots.length > 0,
    gitCommits: gitRuns.reduce((total, run) => total + (run.pagination?.total ?? run.commits.length), 0),
    codeChurn: gitRuns.reduce((total, run) => total + run.code_churn, 0),
    jiraTickets: jiraSnapshots.reduce((total, snapshot) => total + snapshot.tickets.length, 0),
  };
}

export function indexIngestionRuns(
  result: Pick<ProjectIngestionFetchResult, "gitRuns" | "jiraSnapshots"> | undefined,
): IngestionRunIndex {
  const gitBySprint: Record<string, PersistedGitMetrics> = {};
  const jiraBySprint: Record<string, PersistedJiraSnapshot> = {};
  result?.gitRuns.forEach((run) => {
    gitBySprint[`${run.project_id}:${run.sprint_id}`] = run;
  });
  result?.jiraSnapshots.forEach((snapshot) => {
    jiraBySprint[`${snapshot.project_id}:${snapshot.sprint_id}`] = snapshot;
  });
  return { gitBySprint, jiraBySprint };
}
