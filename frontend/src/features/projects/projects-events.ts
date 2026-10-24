export const PROJECTS_UPDATED_EVENT = "sprintsight-projects-updated";

export function notifyProjectsUpdated() {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent(PROJECTS_UPDATED_EVENT));
}
