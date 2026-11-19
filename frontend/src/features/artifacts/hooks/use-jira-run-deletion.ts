"use client";

import { useState } from "react";

import { getErrorMessage } from "@/lib/api/client";
import { deleteJiraRun, type JiraRunIdentity } from "@/features/artifacts/jira-api";

export function useJiraRunDeletion(onDeleted: (run: JiraRunIdentity) => Promise<void>) {
  const [pendingDelete, setPendingDelete] = useState<JiraRunIdentity | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState("");

  function requestDelete(run: JiraRunIdentity) {
    setDeleteError("");
    setPendingDelete(run);
  }

  function cancelDelete() {
    setPendingDelete(null);
  }

  async function confirmDelete() {
    const run = pendingDelete;
    if (!run) return;
    setPendingDelete(null);
    setIsDeleting(true);
    setDeleteError("");
    try {
      await deleteJiraRun(run);
      await onDeleted(run);
    } catch (error) {
      setDeleteError(getErrorMessage(error, "Failed to delete Jira run."));
    } finally {
      setIsDeleting(false);
    }
  }

  return { pendingDelete, requestDelete, cancelDelete, confirmDelete, isDeleting, deleteError };
}
