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
    author_email?: string | null;
    student_id?: string | null;
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
    student_id?: string | null;
    status: string | null;
    issue_type: string | null;
    story_points: number | null;
    sprint_id: string | null;
  }>;
};

/** Runs keyed by `${projectId}:${sprintId}`, built from query results. */
export type IngestionRunIndex = {
  gitBySprint: Record<string, PersistedGitMetrics>;
  jiraBySprint: Record<string, PersistedJiraSnapshot>;
};
