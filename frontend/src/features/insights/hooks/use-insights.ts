"use client";

import { useEffect, useRef } from "react";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  fetchEvidence,
  fetchInsightsConfig,
  fetchInsightsHealth,
  fetchJudgeStatus,
  fetchMyCourses,
  fetchOverrideStats,
  fetchReveal,
  fetchRuns,
  fetchTrace,
  saveLabels,
} from "@/features/insights/insights-api";
import { insightsKeys } from "@/features/insights/query-keys";
import type { JudgeStatus, LabelDraft, RunFilters, RunsPage } from "@/features/insights/types";

const OPEN: JudgeStatus[] = ["pending", "unknown"];
export const JUDGE_POLL_MS = 10_000;

export function judgeStatusRefetchInterval(status: JudgeStatus | undefined): number | false {
  return status && OPEN.includes(status) ? JUDGE_POLL_MS : false;
}

const isConflict = (error: unknown) => (error as { status?: number } | null)?.status === 409;

export function useMyCourses() {
  return useQuery({ queryKey: insightsKeys.myCourses(), queryFn: fetchMyCourses });
}

export function useRuns(filters: RunFilters) {
  return useQuery({
    queryKey: insightsKeys.runs(filters),
    queryFn: () => fetchRuns(filters),
    placeholderData: keepPreviousData,
    refetchInterval: (query) =>
      (query.state.data as RunsPage | undefined)?.items.some((i) => OPEN.includes(i.judgeStatus))
        ? JUDGE_POLL_MS
        : false,
  });
}

export function useEvidence(reportId: string) {
  return useQuery({
    queryKey: insightsKeys.evidence(reportId),
    queryFn: () => fetchEvidence(reportId),
    staleTime: 0,
  });
}

export function useSaveLabels(reportId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (labels: LabelDraft[]) => saveLabels(reportId, labels),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: insightsKeys.evidence(reportId) });
      void queryClient.invalidateQueries({ queryKey: insightsKeys.runsRoot() });
      void queryClient.invalidateQueries({ queryKey: insightsKeys.myCourses() });
    },
  });
}

export function useReveal(reportId: string, enabled: boolean) {
  return useQuery({
    queryKey: insightsKeys.reveal(reportId),
    queryFn: () => fetchReveal(reportId),
    enabled,
    retry: (count, error) => !isConflict(error) && count < 1,
  });
}

export function useTrace(reportId: string, enabled: boolean) {
  return useQuery({
    queryKey: insightsKeys.trace(reportId),
    queryFn: () => fetchTrace(reportId),
    enabled,
    retry: (count, error) => !isConflict(error) && count < 1,
  });
}

export function useJudgeStatus(reportId: string) {
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: insightsKeys.judgeStatus(reportId),
    queryFn: () => fetchJudgeStatus(reportId),
    refetchInterval: (q) => judgeStatusRefetchInterval(q.state.data?.judgeStatus),
  });
  const previous = useRef<JudgeStatus | undefined>(undefined);
  const current = query.data?.judgeStatus;
  useEffect(() => {
    if (previous.current && previous.current !== current && current === "complete") {
      void queryClient.invalidateQueries({ queryKey: insightsKeys.reveal(reportId) });
      void queryClient.invalidateQueries({ queryKey: insightsKeys.runsRoot() });
    }
    previous.current = current;
  }, [current, queryClient, reportId]);
  return query;
}

export function useInsightsHealth() {
  return useQuery({
    queryKey: insightsKeys.health(),
    queryFn: fetchInsightsHealth,
    refetchInterval: 30_000,
  });
}

/** The deployment's mode never changes while the page is open, so it is fetched once. */
export function useInsightsConfig() {
  return useQuery({
    queryKey: insightsKeys.config(),
    queryFn: fetchInsightsConfig,
    staleTime: Infinity,
  });
}

export function useOverrideStats() {
  return useQuery({ queryKey: insightsKeys.overrideStats(), queryFn: fetchOverrideStats });
}
