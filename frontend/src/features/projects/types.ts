export type ProjectStatus = "Active" | "At Risk" | "Completed";

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
  status: ProjectStatus;
  score: number;
  completion: number;
  module: string;
  sprints: { name: string }[];
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
  score: number;
  completion: number;
  startDate: string;
  endDate: string;
};

export type StudentProject = {
  id: string;
  name: string;
  teamName: string;
  module: string;
  status: ProjectStatus;
  score: number;
  completion: number;
  members: string[];
  currentSprint: string;
  sprints: ProjectSprint[];
};
