export type ActiveAssessmentJob = { jobId: string; courseId: string; projectId: string; sprintId: string };

const STORAGE_KEY = "sprintsight-active-assessment-job";

export function saveActiveAssessmentJob(job: ActiveAssessmentJob) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(job));
}

export function clearActiveAssessmentJob() {
  localStorage.removeItem(STORAGE_KEY);
}

export function readActiveAssessmentJob(): ActiveAssessmentJob | null {
  try {
    const parsed = JSON.parse(localStorage.getItem(STORAGE_KEY) || "null") as Partial<ActiveAssessmentJob> | null;
    if (parsed && parsed.jobId && parsed.courseId && parsed.projectId && parsed.sprintId) return parsed as ActiveAssessmentJob;
  } catch {
    // ignore malformed storage
  }
  return null;
}
