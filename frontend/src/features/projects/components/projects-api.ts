import type { ProjectStatus } from "@/features/projects/types";
import { getSessionUser } from "@/lib/auth/session";

export function isUuid(value: string | undefined | null) {
  return Boolean(
    value && /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value)
  );
}

/** Signed-in user's email as the default shared Jira account; empty when unknown. */
export function getDefaultJiraEmail() {
  return getSessionUser()?.email ?? "";
}

export type ProjectFormValues = {
  project_name: string;
  team_name: string;
  description: string;
  github_repo_url: string;
  local_repo_path: string;
  jira_domain: string;
  jira_project_key: string;
};

export function toProjectPayload(form: ProjectFormValues, jiraEmail: string, memberIds: string[] = []) {
  const optionalFields = {
    description: form.description.trim() || undefined,
    github_repo_url: form.github_repo_url.trim() || undefined,
    local_repo_path: form.local_repo_path.trim() || undefined,
    jira_domain: form.jira_domain.trim() || undefined,
    jira_project_key: form.jira_project_key.trim() || undefined,
  };

  return {
    project_name: form.project_name.trim(),
    team_name: form.team_name.trim(),
    jira_email: jiraEmail.trim() || getDefaultJiraEmail(),
    ...optionalFields,
    member_ids: memberIds,
  };
}

export function getStatusStyles(status: ProjectStatus) {
  if (status === "At Risk") return "bg-rose-50 text-rose-600 border-rose-200";
  if (status === "Completed") return "bg-slate-100 text-slate-600 border-slate-200";
  return "bg-emerald-50 text-emerald-600 border-emerald-200";
}
