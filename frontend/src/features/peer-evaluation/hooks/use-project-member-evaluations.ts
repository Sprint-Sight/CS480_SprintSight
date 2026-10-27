"use client";

import { useEffect, useState } from "react";
import {
  getMemberEvaluations,
  type MemberPeerEvaluationDetail,
} from "@/features/peer-evaluation/peer-evaluation-api";

export function useProjectMemberEvaluations(projectId: string, memberIds: string[]) {
  const memberIdsKey = memberIds.join(",");
  const [members, setMembers] = useState<MemberPeerEvaluationDetail[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const ids = memberIdsKey ? memberIdsKey.split(",") : [];
    if (!projectId || ids.length === 0) {
      setMembers([]);
      setError(null);
      setIsLoading(false);
      return;
    }

    let cancelled = false;
    setMembers([]);
    setError(null);
    setIsLoading(true);

    Promise.all(ids.map((memberId) => getMemberEvaluations(projectId, memberId)))
      .then((details) => {
        if (!cancelled) setMembers(details);
      })
      .catch((cause: unknown) => {
        if (cancelled) return;
        setMembers([]);
        setError(
          cause instanceof Error
            ? cause.message
            : "Failed to load project member evaluations.",
        );
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [projectId, memberIdsKey]);

  return { members, isLoading, error };
}
