export type SprintStatus = "On Track" | "Needs Attention" | "Completed";

export type Course = {
  id: string;
  code: string;
  name: string;
  section: string;
  year: number;
  term: string;
};

export type ProjectMember = {
  id: string;
  email: string;
  full_name: string;
};

export type Project = {
  id: string;
  project_name: string;
  team_name: string;
  description?: string;
  module: string;
  members: ProjectMember[];
  jira_project_key?: string;
  jira_email?: string;
  jira_domain?: string;
  jira_api_token?: string;
  github_repo_url?: string;
  local_repo_path?: string;
};

export type ProjectSprint = {
  id: string;
  name: string;
  status: SprintStatus;
  /** Null when the ingestion run does not report completion. */
  completion: number | null;
  /** ISO timestamp of when the sprint's Git/Jira data was captured. */
  capturedAt: string;
};

