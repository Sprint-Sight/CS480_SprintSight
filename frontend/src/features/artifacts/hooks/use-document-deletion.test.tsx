/// <reference types="vitest/globals" />
import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { apiRequest } from "@/lib/api/client";
import { useDocumentDeletion } from "@/features/artifacts/hooks/use-document-deletion";

vi.mock("@/lib/api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/client")>()),
  apiRequest: vi.fn(),
}));

const mockedApiRequest = vi.mocked(apiRequest);

describe("useDocumentDeletion", () => {
  afterEach(() => {
    vi.clearAllMocks();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("stores a pending delete and calls the project-scoped DELETE endpoint only after confirmation", async () => {
    mockedApiRequest.mockResolvedValue(null);
    const onDeleted = vi.fn();
    const { result } = renderHook(() => useDocumentDeletion(onDeleted));

    act(() => {
      result.current.requestDelete("project-123", "document-456", "brief.pdf");
    });
    expect(result.current.pendingDelete).toEqual({
      projectId: "project-123",
      documentId: "document-456",
      filename: "brief.pdf",
    });
    expect(mockedApiRequest).not.toHaveBeenCalled();

    await act(async () => {
      await result.current.confirmDelete();
    });

    expect(result.current.pendingDelete).toBeNull();
    expect(mockedApiRequest).toHaveBeenCalledWith(
      "/projects/project-123/documents/document-456",
      { method: "DELETE" },
    );
    expect(onDeleted).toHaveBeenCalledWith("project-123", "document-456");
  });

  it("does not call the endpoint or remove the document when the pending delete is canceled", async () => {
    const onDeleted = vi.fn();
    const { result } = renderHook(() => useDocumentDeletion(onDeleted));

    act(() => {
      result.current.requestDelete("project-123", "document-456", "brief.pdf");
    });
    act(() => {
      result.current.cancelDelete();
    });

    expect(result.current.pendingDelete).toBeNull();
    expect(mockedApiRequest).not.toHaveBeenCalled();
    expect(onDeleted).not.toHaveBeenCalled();
  });

  it("keeps the document and exposes the error when deletion fails", async () => {
    mockedApiRequest.mockRejectedValue(new Error("Document storage is unavailable."));
    const onDeleted = vi.fn();
    const { result } = renderHook(() => useDocumentDeletion(onDeleted));

    await act(async () => {
      result.current.requestDelete("project-123", "document-456", "notes.pdf");
    });
    await act(async () => {
      await result.current.confirmDelete();
    });

    await waitFor(() => {
      expect(result.current.deleteErrors["document-456"]).toBe("Document storage is unavailable.");
    });
    expect(onDeleted).not.toHaveBeenCalled();
    expect(result.current.deletingDocumentIds.has("document-456")).toBe(false);
  });

  it("tracks the document as deleting until the endpoint succeeds", async () => {
    let resolveDelete: ((value: null) => void) | undefined;
    mockedApiRequest.mockImplementation(
      () => new Promise<null>((resolve) => {
        resolveDelete = resolve;
      }),
    );
    const { result } = renderHook(() => useDocumentDeletion(vi.fn()));

    let pendingDelete: Promise<void> | undefined;
    act(() => {
      result.current.requestDelete("project-123", "document-456", "notes.pdf");
    });
    act(() => {
      pendingDelete = result.current.confirmDelete();
    });
    await waitFor(() => expect(result.current.deletingDocumentIds.has("document-456")).toBe(true));

    await act(async () => {
      resolveDelete?.(null);
      await pendingDelete;
    });
    expect(result.current.deletingDocumentIds.has("document-456")).toBe(false);
  });
});
