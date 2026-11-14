import type { RunFilters } from "@/features/insights/types";

export const insightsKeys = {
  all: ["insights"] as const,
  myCourses: () => [...insightsKeys.all, "my-courses"] as const,
  runsRoot: () => [...insightsKeys.all, "runs"] as const,
  runs: (filters: RunFilters) => [...insightsKeys.runsRoot(), filters] as const,
  report: (id: string) => [...insightsKeys.all, "report", id] as const,
  evidence: (id: string) => [...insightsKeys.report(id), "evidence"] as const,
  reveal: (id: string) => [...insightsKeys.report(id), "reveal"] as const,
  trace: (id: string) => [...insightsKeys.report(id), "trace"] as const,
  judgeStatus: (id: string) => [...insightsKeys.report(id), "judge-status"] as const,
  health: () => [...insightsKeys.all, "health"] as const,
  config: () => [...insightsKeys.all, "config"] as const,
  overrideStats: () => [...insightsKeys.all, "override-stats"] as const,
};
