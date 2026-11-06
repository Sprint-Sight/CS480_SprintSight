import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useCollaborationData } from "@/features/collaboration/hooks/use-collaboration-data";
import { fetchCollaborationProjectData } from "@/features/collaboration/collaboration-api";
import { readScope, subscribeScope } from "@/features/ingestion/scope-store";
import { createTestWrapper } from "@/test-utils";

vi.mock("@/features/collaboration/collaboration-api", () => ({
  fetchCollaborationProjectData: vi.fn(),
}));
vi.mock("@/features/ingestion/scope-store", () => ({
  readScope: vi.fn(),
  subscribeScope: vi.fn(() => () => undefined),
}));

const emptyData = {
  projectLabel: "Team - Project",
  memberNames: new Map<string, string>(),
  ingestion: { git: undefined, jira: undefined },
};

describe("useCollaborationData", () => {
  beforeEach(() => {
    vi.mocked(readScope).mockReturnValue({
      selectedProjectId: "project-1",
      selectedCourseId: "course-1",
      selectedSprintId: "sprint-1",
    });
    vi.mocked(fetchCollaborationProjectData).mockReset();
  });

  it("loads fresh data for the currently scoped project and handles an empty result", async () => {
    vi.mocked(fetchCollaborationProjectData).mockResolvedValue(emptyData);
    const { result } = renderHook(() => useCollaborationData(), { wrapper: createTestWrapper() });

    await waitFor(() => expect(fetchCollaborationProjectData).toHaveBeenCalledWith(
      "project-1",
      expect.anything(),
    ));
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.collaborationData.projectLabel).toBe("Team - Project");
    expect(result.current.collaborationData.commitsByMember).toEqual([]);
    expect(result.current.collaborationData.workloadDistribution).toEqual([]);
  });

  it("shows loading state and surfaces fetch failures", async () => {
    let rejectRequest: (error: Error) => void = () => undefined;
    vi.mocked(fetchCollaborationProjectData).mockReturnValue(
      new Promise((_, reject) => {
        rejectRequest = reject;
      }),
    );
    const { result } = renderHook(() => useCollaborationData(), { wrapper: createTestWrapper() });

    await waitFor(() => expect(result.current.isLoading).toBe(true));
    act(() => rejectRequest(new Error("Unable to load project data.")));
    await waitFor(() => expect(result.current.error).toBe("Unable to load project data."));
    expect(result.current.isLoading).toBe(false);
  });
});
