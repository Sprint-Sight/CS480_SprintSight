import type { ProjectStatus } from "@/features/projects/types";

export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/api/v1";

export function getAuthToken() {
  if (typeof window === "undefined") return null;
  return (
    sessionStorage.getItem("sprintsight-access-token") ??
    localStorage.getItem("sprintsight-access-token")
  );
}

export function isUuid(value: string | undefined | null) {
  return Boolean(
    value && /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value)
  );
}

export async function apiRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getAuthToken();
  if (!token) {
    throw new Error("You are not signed in. Please log in again.");
  }

  const requestHeaders = new Headers(options.headers);
  requestHeaders.set("Authorization", `Bearer ${token}`);
  if (!(options.body instanceof FormData) && !requestHeaders.has("Content-Type")) {
    requestHeaders.set("Content-Type", "application/json");
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    cache: options.method && options.method !== "GET" ? options.cache : "no-store",
    headers: requestHeaders,
  });

  if (response.status === 204) {
    return null as T;
  }

  const text = await response.text();
  let payload: unknown = null;
  try {
    payload = text ? JSON.parse(text) : null;
  } catch {
    payload = text || null;
  }

  if (!response.ok) {
    const errorPayload = payload as { detail?: unknown; message?: unknown; error?: { message?: unknown } } | null;
    const detail = errorPayload?.detail ?? errorPayload?.message ?? errorPayload?.error?.message ?? "Request failed.";
    if (response.status === 401 && typeof window !== "undefined") {
      sessionStorage.removeItem("sprintsight-access-token");
      localStorage.removeItem("sprintsight-access-token");
      window.location.href = "/login";
    }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }

  return payload as T;
}

export function getDefaultJiraEmail() {
  if (typeof window === "undefined") return "instructor@sprintsight.dev";
  return sessionStorage.getItem("sprintsight-auth-email") || "instructor@sprintsight.dev";
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
