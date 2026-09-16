export const INGESTION_STORAGE_KEY = "sprintsight-ingestion-state-v1";

export type PersistedGitMetrics = {
  course_id: string;
  project_id: string;
  sprint_id: string;
  head_sha: string | null;
  captured_at: string;
  commit_frequency: number;
  code_churn: number;
  pr_turnaround_hours: number | null;
  assigned_story_points: number | null;
  completion_percent: number | null;
  commits: Array<{
    sha: string;
    author: string;
    message: string;
    timestamp: string;
    lines_added: number;
    lines_deleted: number;
    files_changed: unknown[];
  }>;
  pagination?: {
    limit: number | null;
    offset: number | null;
    total: number;
    has_more: boolean;
  };
};

export type PersistedJiraSnapshot = {
  normalization_version: string;
  source: string;
  jira_project_key: string;
  course_id: string;
  project_id: string;
  sprint_id: string;
  captured_at: string;
  tickets: Array<{
    ticket_id: string;
    summary: string;
    assignee: string | null;
    status: string | null;
    issue_type: string | null;
    story_points: number | null;
    sprint_id: string | null;
  }>;
};

export type IngestionState = {
  selectedProjectId?: string;
  selectedCourseId?: string;
  gitBySprint: Record<string, PersistedGitMetrics>;
  jiraBySprint: Record<string, PersistedJiraSnapshot>;
  documentCounts: Record<string, number>;
};

const emptyState = (): IngestionState => ({
  gitBySprint: {},
  jiraBySprint: {},
  documentCounts: {},
});

export function readIngestionState(): IngestionState {
  if (typeof window === "undefined") return emptyState();
  try {
    const parsed = JSON.parse(localStorage.getItem(INGESTION_STORAGE_KEY) || "null") as Partial<IngestionState> | null;
    return {
      ...emptyState(),
      ...parsed,
      gitBySprint: parsed?.gitBySprint || {},
      jiraBySprint: parsed?.jiraBySprint || {},
      documentCounts: parsed?.documentCounts || {},
    };
  } catch {
    return emptyState();
  }
}

export function writeIngestionState(patch: Partial<IngestionState>) {
  if (typeof window === "undefined") return;
  const next = { ...readIngestionState(), ...patch };
  localStorage.setItem(INGESTION_STORAGE_KEY, JSON.stringify(next));
  window.dispatchEvent(new CustomEvent("sprintsight-ingestion-updated"));
}

export function saveGitMetrics(metrics: PersistedGitMetrics) {
  const state = readIngestionState();
  writeIngestionState({
    selectedProjectId: metrics.project_id,
    selectedCourseId: metrics.course_id,
    gitBySprint: { ...state.gitBySprint, [`${metrics.project_id}:${metrics.sprint_id}`]: metrics },
  });
}

export function getProjectGitMetrics(projectId: string): PersistedGitMetrics[] {
  return Object.values(readIngestionState().gitBySprint)
    .filter((metrics) => metrics.project_id === projectId)
    .sort((first, second) => first.sprint_id.localeCompare(second.sprint_id, undefined, { numeric: true }));
}

export function saveJiraSnapshot(snapshot: PersistedJiraSnapshot) {
  const state = readIngestionState();
  writeIngestionState({
    selectedProjectId: snapshot.project_id,
    selectedCourseId: snapshot.course_id,
    jiraBySprint: { ...state.jiraBySprint, [`${snapshot.project_id}:${snapshot.sprint_id}`]: snapshot },
  });
}

export function saveDocumentCount(projectId: string, count: number) {
  const state = readIngestionState();
  writeIngestionState({ documentCounts: { ...state.documentCounts, [projectId]: count } });
}

export function getProjectIngestion(projectId: string, sprintId?: string) {
  const state = readIngestionState();
  const git = sprintId
    ? state.gitBySprint[`${projectId}:${sprintId}`]
    : Object.values(state.gitBySprint).find((item) => item.project_id === projectId);
  const jira = sprintId
    ? state.jiraBySprint[`${projectId}:${sprintId}`]
    : Object.values(state.jiraBySprint).find((item) => item.project_id === projectId);
  return { git, jira, documents: state.documentCounts[projectId] || 0 };
}