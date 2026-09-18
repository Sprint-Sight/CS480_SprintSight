"use client";

import { useMemo } from "react";
import type { ReviewCriterion } from "@/features/review/types";

export function useReviewScoring(criteria: ReviewCriterion[], savedSnapshot: ReviewCriterion[], scoringEnabled: boolean, criterionScoring: Record<string, boolean>, aiOverallScore: number) {
  const overallScore = useMemo(() => { if (!scoringEnabled) return aiOverallScore; const scored = criteria.filter((item) => criterionScoring[item.id]); return scored.length ? Math.round(scored.reduce((sum, item) => sum + item.score, 0) / scored.length) : 0; }, [aiOverallScore, criteria, criterionScoring, scoringEnabled]);
  const hasUnsavedChanges = useMemo(() => JSON.stringify(criteria) !== JSON.stringify(savedSnapshot), [criteria, savedSnapshot]);
  return { overallScore, hasUnsavedChanges };
}
