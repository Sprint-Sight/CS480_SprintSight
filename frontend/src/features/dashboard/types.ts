export type DashboardRole = "student" | "instructor" | "admin";

export type DashboardProject = {
  id: string;
  courseId: string;
  label: string;
};

export type GitMetrics = {
  sprint_id: string;
  commit_frequency: number;
  code_churn: number;
  assigned_story_points: number | null;
  completion_percent: number | null;
  commits: DashboardCommit[];
};

export type DashboardCommit = {
  sha: string;
  author: string;
  message: string;
  timestamp: string;
  lines_added: number;
  lines_deleted: number;
};

export type JiraRun = {
  run_id: string;
  sprint_id: string;
  processing_status: string;
  captured_at: string;
  project_id: string;
};

export type JiraTicket = {
  ticket_id: string;
  summary: string;
  status: string | null;
  status_category?: string | null;
  assignee: string | null;
  story_points: number | null;
  created_at?: string | null;
};

export type JiraSnapshot = {
  tickets: JiraTicket[];
};

