import { renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { useSprintOverviewData } from "@/features/sprints/hooks/use-sprint-overview-data";

const PROJECT_ID = "11111111-1111-4111-8111-111111111111";

vi.mock("@/features/ingestion/hooks/use-ingestion-scope", () => ({
  useIngestionScope: () => ({
    scope: {
      selectedProjectId: PROJECT_ID,
      selectedCourseId: "course-1",
      selectedSprintId: "sprint-1",
    },
    updateScope: vi.fn(),
  }),
}));

vi.mock("@/features/ingestion/hooks/use-ingestion-sync", () => ({
  useIngestionSync: () => ({
    gitRuns: [
      {
        project_id: PROJECT_ID,
        course_id: "course-1",
        sprint_id: "sprint-3",
        captured_at: "2026-11-01T00:00:00Z",
        completion_percent: 40,
        code_churn: 10,
        commits: [],
        pagination: { limit: null, offset: null, total: 4, has_more: false },
      },
    ],
    jiraSnapshots: [],
    isSyncing: false,
    syncError: "",
  }),
}));

vi.mock("@/features/projects/hooks/use-course-projects", () => ({
  useScopeProjects: () => ({ data: [] }),
}));

describe("useSprintOverviewData", () => {
  it("labels sprint rows 'Sprint N', matching the scope bar", () => {
    const { result } = renderHook(() => useSprintOverviewData());

    expect(result.current.payload?.rows.map((row) => row.sprint.name)).toEqual(["Sprint 3"]);
    // The ID itself is unchanged, so links and lookups keep working.
    expect(result.current.payload?.rows[0].sprint.id).toBe("sprint-3");
  });
});
