"use client";

import { useState } from "react";

import { apiRequest } from "@/features/projects/components/projects-api";

export function useDocumentDeletion(onDeleted: (projectId: string, documentId: string) => void) {
  const [deletingDocumentIds, setDeletingDocumentIds] = useState<Set<string>>(() => new Set());
  const [deleteErrors, setDeleteErrors] = useState<Record<string, string>>({});

  async function deleteDocument(projectId: string, documentId: string, filename: string) {
    if (!window.confirm(`Delete "${filename}"? This action cannot be undone.`)) return;
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
        [documentId]: error instanceof Error ? error.message : "Failed to delete document.",
      }));
    } finally {
      setDeletingDocumentIds((current) => {
        const next = new Set(current);
        next.delete(documentId);
        return next;
      });
    }
  }

  return { deleteDocument, deletingDocumentIds, deleteErrors };
}
