/// <reference types="vitest/globals" />
import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { apiRequest } from "@/lib/api/client";
import { useJiraRunDeletion } from "@/features/artifacts/hooks/use-jira-run-deletion";

vi.mock("@/lib/api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/client")>()),
  apiRequest: vi.fn(),
}));

const mockedApiRequest = vi.mocked(apiRequest);

const RUN = { project_id: "project-1", sprint_id: "Sprint 2", run_id: "run-9" };

describe("useJiraRunDeletion", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("calls the run DELETE endpoint only after confirmation, then notifies the container", async () => {
    mockedApiRequest.mockResolvedValue(null);
    const onDeleted = vi.fn().mockResolvedValue(undefined);
    const { result } = renderHook(() => useJiraRunDeletion(onDeleted));

    act(() => result.current.requestDelete(RUN));
    expect(result.current.pendingDelete).toEqual(RUN);
    expect(mockedApiRequest).not.toHaveBeenCalled();

    await act(async () => {
      await result.current.confirmDelete();
    });

    expect(mockedApiRequest).toHaveBeenCalledWith(
      "/jira-ingestion/runs/project-1/Sprint%202/run-9",
      { method: "DELETE" },
    );
    expect(onDeleted).toHaveBeenCalledWith(RUN);
    expect(result.current.pendingDelete).toBeNull();
  });

  it("does not call the endpoint when the pending delete is canceled", () => {
    const { result } = renderHook(() => useJiraRunDeletion(vi.fn()));

    act(() => result.current.requestDelete(RUN));
    act(() => result.current.cancelDelete());

    expect(result.current.pendingDelete).toBeNull();
    expect(mockedApiRequest).not.toHaveBeenCalled();
  });

  it("exposes the error and skips the reload when deletion fails", async () => {
    mockedApiRequest.mockRejectedValue(new Error("Jira run is locked."));
    const onDeleted = vi.fn();
    const { result } = renderHook(() => useJiraRunDeletion(onDeleted));

    act(() => result.current.requestDelete(RUN));
    await act(async () => {
      await result.current.confirmDelete();
    });

    await waitFor(() => expect(result.current.deleteError).toBe("Jira run is locked."));
    expect(onDeleted).not.toHaveBeenCalled();
    expect(result.current.isDeleting).toBe(false);
  });
});
