import { renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useContributionsData } from "@/features/contributions/hooks/use-contributions-data";

const PROJECT_ID = "11111111-1111-4111-8111-111111111111";

const scopeState = { selectedProjectId: PROJECT_ID, selectedSprintId: "sprint-2" };
const scopeProjects = {
  data: [
    {
      course: { id: "course-1" },
      projects: [{ id: PROJECT_ID, team_name: "Team Falcon", project_name: "Sprint Tracker" }],
    },
  ] as unknown,
};
const useScopeProjects = vi.fn((enabled?: boolean) => {
  void enabled;
  return scopeProjects;
});

vi.mock("@/features/ingestion/hooks/use-ingestion-scope", () => ({
  useIngestionScope: () => ({
    scope: { ...scopeState, selectedCourseId: "course-1" },
    updateScope: vi.fn(),
  }),
}));
vi.mock("@/features/ingestion/hooks/use-ingestion-sync", () => ({
  useIngestionSync: () => ({ gitRuns: [], jiraSnapshots: [], isSyncing: false, syncError: "" }),
}));
vi.mock("@/features/projects/hooks/use-course-projects", () => ({
  useScopeProjects: (enabled?: boolean) => useScopeProjects(enabled),
}));
vi.mock("@/lib/auth/session", () => ({
  useSession: () => ({ token: "t", user: { role: "instructor" } }),
}));

describe("useContributionsData labels", () => {
  beforeEach(() => {
    scopeState.selectedProjectId = PROJECT_ID;
    scopeState.selectedSprintId = "sprint-2";
    scopeProjects.data = [
      {
        course: { id: "course-1" },
        projects: [{ id: PROJECT_ID, team_name: "Team Falcon", project_name: "Sprint Tracker" }],
      },
    ];
  });

  it("uses the selected project's team and project names, not placeholders or the UUID", () => {
    const { result } = renderHook(() => useContributionsData());

    expect(result.current.dataset.teamLabel).toBe("Team Falcon");
    expect(result.current.dataset.projectLabel).toBe("Sprint Tracker");
    expect(result.current.dataset.sprintLabel).toBe("Sprint 2");
    expect(result.current.dataset.projectLabel).not.toContain(PROJECT_ID);
  });

  it("falls back to an em dash when the project is not in the cached list", () => {
    scopeProjects.data = [];
    const { result } = renderHook(() => useContributionsData());

    expect(result.current.dataset.teamLabel).toBe("—");
    expect(result.current.dataset.projectLabel).toBe("—");
  });

  it("falls back to an em dash when no sprint is selected", () => {
    scopeState.selectedSprintId = "";
    const { result } = renderHook(() => useContributionsData());

    expect(result.current.dataset.sprintLabel).toBe("—");
  });
});
