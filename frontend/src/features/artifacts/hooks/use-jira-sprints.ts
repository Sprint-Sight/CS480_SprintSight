"use client";

import { useCallback, useState } from "react";

import { fetchJiraSprints, type JiraSprint } from "@/features/artifacts/jira-api";

export function useJiraSprints() {
  const [sprints, setSprints] = useState<JiraSprint[]>([]);

  const clearSprints = useCallback(() => setSprints([]), []);

  const loadSprints = useCallback(async (projectId: string, signal?: AbortSignal) => {
    const result = await fetchJiraSprints(projectId, signal);
    const next = Array.isArray(result) ? result : [];
    if (!signal?.aborted) setSprints(next);
    return next;
  }, []);

  return { sprints, loadSprints, clearSprints };
}
