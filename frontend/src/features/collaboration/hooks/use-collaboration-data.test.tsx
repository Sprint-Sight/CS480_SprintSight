import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useCollaborationData } from "@/features/collaboration/hooks/use-collaboration-data";
import { fetchCollaborationProjectData } from "@/features/collaboration/collaboration-api";
import { readIngestionState } from "@/features/ingestion/state";

vi.mock("@/features/collaboration/collaboration-api", () => ({
  fetchCollaborationProjectData: vi.fn(),
}));
vi.mock("@/features/ingestion/state", () => ({
  readIngestionState: vi.fn(),
}));

const emptyData = {
  projectLabel: "Team - Project",
  memberNames: new Map<string, string>(),
  ingestion: { git: undefined, jira: undefined, documents: 0 },
};

describe("useCollaborationData", () => {
  beforeEach(() => {
    vi.mocked(readIngestionState).mockReturnValue({
      selectedProjectId: "project-1",
      selectedCourseId: "course-1",
      gitBySprint: {},
      jiraBySprint: {},
      documentCounts: {},
    });
    vi.mocked(fetchCollaborationProjectData).mockReset();
  });

  it("loads fresh data for the currently scoped project and handles an empty result", async () => {
    vi.mocked(fetchCollaborationProjectData).mockResolvedValue(emptyData);
    const { result } = renderHook(() => useCollaborationData());

    await waitFor(() => expect(fetchCollaborationProjectData).toHaveBeenCalledWith(
      "project-1",
      expect.objectContaining({ selectedProjectId: "project-1" }),
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
    const { result } = renderHook(() => useCollaborationData());

    await waitFor(() => expect(result.current.isLoading).toBe(true));
    act(() => rejectRequest(new Error("Unable to load project data.")));
    await waitFor(() => expect(result.current.error).toBe("Unable to load project data."));
    expect(result.current.isLoading).toBe(false);
  });
});
