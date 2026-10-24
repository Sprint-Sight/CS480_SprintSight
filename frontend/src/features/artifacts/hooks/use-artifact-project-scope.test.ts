/// <reference types="vitest/globals" />
import { renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { getStudentProjects, apiRequest, readIngestionState } = vi.hoisted(() => ({
  getStudentProjects: vi.fn(),
  apiRequest: vi.fn(),
  readIngestionState: vi.fn(),
}));

vi.mock("@/features/student/student-project-api", () => ({ getStudentProjects }));
vi.mock("@/features/projects/components/projects-api", () => ({ apiRequest }));
vi.mock("@/features/ingestion/state", () => ({ readIngestionState }));

import { useArtifactProjectScope } from "@/features/artifacts/hooks/use-artifact-project-scope";

describe("useArtifactProjectScope", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    readIngestionState.mockReturnValue({
      selectedProjectId: "unrelated-browser-project",
      selectedSprintId: "sprint-9",
    });
  });

  it("selects the student's project from the authorized student-project API", async () => {
    getStudentProjects.mockResolvedValue([
      {
        id: "student-project-id",
        project_name: "SprintSight",
        team_name: "Team A",
        description: null,
        course_code: "CS480",
      },
    ]);

    const { result } = renderHook(() => useArtifactProjectScope("student"));

    await waitFor(() => expect(result.current.isLoadingProjects).toBe(false));
    expect(result.current.selectedProjectId).toBe("student-project-id");
    expect(result.current.projectOptions).toEqual([
      { id: "student-project-id", label: "Team A - SprintSight" },
    ]);
    expect(apiRequest).not.toHaveBeenCalled();
    expect(readIngestionState).not.toHaveBeenCalled();
  });

  it("does not select a project if loading the student's authorized projects fails", async () => {
    getStudentProjects.mockRejectedValue(new Error("Project lookup failed"));

    const { result } = renderHook(() => useArtifactProjectScope("student"));

    await waitFor(() => expect(result.current.isLoadingProjects).toBe(false));
    expect(result.current.selectedProjectId).toBe("");
    expect(result.current.projectLoadError).toBe("Project lookup failed");
  });
});
