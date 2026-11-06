"use client";

import { useState } from "react";

import { apiRequest, getErrorMessage } from "@/lib/api/client";

export type PendingDocumentDelete = {
  projectId: string;
  documentId: string;
  filename: string;
};

export function useDocumentDeletion(onDeleted: (projectId: string, documentId: string) => void) {
  const [deletingDocumentIds, setDeletingDocumentIds] = useState<Set<string>>(() => new Set());
  const [deleteErrors, setDeleteErrors] = useState<Record<string, string>>({});
  const [pendingDelete, setPendingDelete] = useState<PendingDocumentDelete | null>(null);

  function requestDelete(projectId: string, documentId: string, filename: string) {
    setPendingDelete({ projectId, documentId, filename });
  }

  function cancelDelete() {
    setPendingDelete(null);
  }

  async function confirmDelete() {
    if (!pendingDelete) return;
    const { projectId, documentId } = pendingDelete;
    setPendingDelete(null);
    await deleteDocument(projectId, documentId);
  }

  async function deleteDocument(projectId: string, documentId: string) {
    if (deletingDocumentIds.has(documentId)) return;

    setDeletingDocumentIds((current) => new Set(current).add(documentId));
    setDeleteErrors((current) => {
      const next = { ...current };
      delete next[documentId];
      return next;
    });

    try {
      await apiRequest<null>(`/projects/${projectId}/documents/${documentId}`, { method: "DELETE" });
      onDeleted(projectId, documentId);
    } catch (error) {
      setDeleteErrors((current) => ({
        ...current,
        [documentId]: getErrorMessage(error, "Failed to delete document."),
      }));
    } finally {
      setDeletingDocumentIds((current) => {
        const next = new Set(current);
        next.delete(documentId);
        return next;
      });
    }
  }

  return { requestDelete, cancelDelete, confirmDelete, pendingDelete, deletingDocumentIds, deleteErrors };
}
