import { apiRequest } from "@/lib/api/client";
import type {
  Evidence,
  InsightsConfig,
  InsightsCourse,
  InsightsHealth,
  JudgeStatusView,
  LabelDraft,
  OverrideStats,
  Reveal,
  RunFilters,
  RunsPage,
  SaveLabelsResult,
  TraceView,
} from "@/features/insights/types";

// The backend returns lists (never maps keyed by dimension/prompt names), so a blind
// deep snake->camel conversion is safe: only keys change, values are untouched.
const camelKey = (key: string) => key.replace(/_([a-z0-9])/g, (_m, c: string) => c.toUpperCase());
export function camelize<T>(value: unknown): T {
  if (Array.isArray(value)) return value.map((item) => camelize(item)) as T;
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>).map(([k, v]) => [camelKey(k), camelize(v)]),
    ) as T;
  }
  return value as T;
}

const get = async <T>(path: string) => camelize<T>(await apiRequest<unknown>(path));
const enc = encodeURIComponent;

export const fetchMyCourses = () => get<InsightsCourse[]>("/insights/my-courses");

export function fetchRuns(filters: RunFilters) {
  const params = new URLSearchParams({
    label_status: filters.labelStatus,
    page: String(filters.page),
    page_size: String(filters.pageSize),
  });
  if (filters.courseId) params.set("course_id", filters.courseId);
  if (filters.sprintId) params.set("sprint_id", filters.sprintId);
  if (filters.model) params.set("model", filters.model);
  return get<RunsPage>(`/insights/runs?${params.toString()}`);
}

export const fetchEvidence = (reportId: string) =>
  get<Evidence>(`/insights/reports/${enc(reportId)}/evidence`);
export const fetchReveal = (reportId: string) =>
  get<Reveal>(`/insights/reports/${enc(reportId)}/reveal`);
export const fetchTrace = (reportId: string) =>
  get<TraceView>(`/insights/reports/${enc(reportId)}/trace`);
export const fetchJudgeStatus = (reportId: string) =>
  get<JudgeStatusView>(`/insights/reports/${enc(reportId)}/judge-status`);
export const fetchInsightsHealth = () => get<InsightsHealth>("/insights/health");
export const fetchInsightsConfig = () => get<InsightsConfig>("/insights/config");
export const fetchOverrideStats = () => get<OverrideStats>("/insights/override-stats");

export async function saveLabels(reportId: string, labels: LabelDraft[]) {
  const body = JSON.stringify({
    labels: labels.map((l) => ({
      dimension: l.dimension,
      score: l.score,
      reason: l.reason ?? null,
    })),
  });
  return camelize<SaveLabelsResult>(
    await apiRequest<unknown>(`/insights/reports/${enc(reportId)}/labels`, { method: "PUT", body }),
  );
}
