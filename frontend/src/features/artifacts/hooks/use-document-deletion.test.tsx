/// <reference types="vitest/globals" />
import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { apiRequest } from "@/features/projects/components/projects-api";
import { useDocumentDeletion } from "@/features/artifacts/hooks/use-document-deletion";

vi.mock("@/features/projects/components/projects-api", () => ({
  apiRequest: vi.fn(),
}));

const mockedApiRequest = vi.mocked(apiRequest);

describe("useDocumentDeletion", () => {
  afterEach(() => {
    vi.clearAllMocks();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("asks for confirmation and calls the project-scoped DELETE endpoint", async () => {
    vi.stubGlobal("confirm", vi.fn(() => true));
    mockedApiRequest.mockResolvedValue(null);
    const onDeleted = vi.fn();
    const { result } = renderHook(() => useDocumentDeletion(onDeleted));

    await act(async () => {
      await result.current.deleteDocument("project-123", "document-456", "brief.pdf");
    });

    expect(window.confirm).toHaveBeenCalledWith('Delete "brief.pdf"? This action cannot be undone.');
    expect(mockedApiRequest).toHaveBeenCalledWith(
      "/projects/project-123/documents/document-456",
      { method: "DELETE" },
    );
    expect(onDeleted).toHaveBeenCalledWith("project-123", "document-456");
  });

  it("does not call the endpoint or remove the document when confirmation is canceled", async () => {
    vi.stubGlobal("confirm", vi.fn(() => false));
    const onDeleted = vi.fn();
    const { result } = renderHook(() => useDocumentDeletion(onDeleted));

    await act(async () => {
      await result.current.deleteDocument("project-123", "document-456", "brief.pdf");
    });

    expect(mockedApiRequest).not.toHaveBeenCalled();
    expect(onDeleted).not.toHaveBeenCalled();
  });

  it("keeps the document and exposes the error when deletion fails", async () => {
    vi.stubGlobal("confirm", vi.fn(() => true));
    mockedApiRequest.mockRejectedValue(new Error("Document storage is unavailable."));
    const onDeleted = vi.fn();
    const { result } = renderHook(() => useDocumentDeletion(onDeleted));

    await act(async () => {
      await result.current.deleteDocument("project-123", "document-456", "brief.pdf");
    });

    await waitFor(() => {
      expect(result.current.deleteErrors["document-456"]).toBe("Document storage is unavailable.");
    });
    expect(onDeleted).not.toHaveBeenCalled();
    expect(result.current.deletingDocumentIds.has("document-456")).toBe(false);
  });

  it("tracks the document as deleting until the endpoint succeeds", async () => {
    vi.stubGlobal("confirm", vi.fn(() => true));
    let resolveDelete: ((value: null) => void) | undefined;
    mockedApiRequest.mockImplementation(
      () => new Promise<null>((resolve) => {
        resolveDelete = resolve;
      }),
    );
    const { result } = renderHook(() => useDocumentDeletion(vi.fn()));

    let pendingDelete: Promise<void> | undefined;
    act(() => {
      pendingDelete = result.current.deleteDocument("project-123", "document-456", "brief.pdf");
    });
    await waitFor(() => expect(result.current.deletingDocumentIds.has("document-456")).toBe(true));

    await act(async () => {
      resolveDelete?.(null);
      await pendingDelete;
    });
    expect(result.current.deletingDocumentIds.has("document-456")).toBe(false);
  });
});
