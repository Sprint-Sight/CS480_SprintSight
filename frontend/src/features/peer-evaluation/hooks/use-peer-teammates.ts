"use client";

import { useEffect, useMemo, useState } from "react";
import { getCurrentUserId, type PeerTeammate } from "@/features/peer-evaluation/peer-evaluation-api";
import type { StudentProject } from "@/features/student/student-project-api";

export function usePeerTeammates(project: StudentProject | null) {
  const [currentUserId, setCurrentUserId] = useState<string | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    getCurrentUserId()
      .then((id) => {
        if (!cancelled) setCurrentUserId(id);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Could not load your profile.");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const teammates = useMemo<PeerTeammate[]>(() => {
    if (!project?.members || !currentUserId) return [];
    return project.members
      .filter((member) => member.id !== currentUserId)
      .map((member) => ({ id: member.id, name: member.full_name || member.email }));
  }, [project, currentUserId]);

  return { currentUserId, teammates, isReady: currentUserId !== null, error };
}
