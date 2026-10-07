"use client";

import { useEffect, useMemo, useState } from "react";

import { readIngestionState } from "@/features/ingestion/state";

export function useProgressData() {
  const [role, setRole] = useState<"student" | "instructor" | null>(null);
  const [selectedProjectId, setSelectedProjectId] = useState(() => readIngestionState().selectedProjectId || "");
  const [selectedCourseId, setSelectedCourseId] = useState(() => readIngestionState().selectedCourseId || "");
  const [ingestionVersion, setIngestionVersion] = useState(0);
  const progressSignals = useMemo(() => {
    void ingestionVersion;
    const state = readIngestionState();
    const belongsToSelectedScope = (item: { project_id: string; course_id: string }) => item.project_id === selectedProjectId && (!selectedCourseId || item.course_id === selectedCourseId);
    const gitRuns = Object.values(state.gitBySprint).filter(belongsToSelectedScope);
    const jiraRuns = Object.values(state.jiraBySprint).filter(belongsToSelectedScope);
    return {
      hasData: gitRuns.length > 0 || jiraRuns.length > 0,
      gitCommits: gitRuns.reduce((total, run) => total + (run.pagination?.total ?? run.commits.length), 0),
      codeChurn: gitRuns.reduce((total, run) => total + run.code_churn, 0),
      jiraTickets: jiraRuns.reduce((total, run) => total + run.tickets.length, 0),
    };
  }, [selectedCourseId, selectedProjectId, ingestionVersion]);

  useEffect(() => setRole((sessionStorage.getItem("sprintsight-auth-role") as "student" | "instructor" | null) ?? "student"), []);
  useEffect(() => {
    const refresh = () => {
      const state = readIngestionState();
      setSelectedProjectId(state.selectedProjectId || "");
      setSelectedCourseId(state.selectedCourseId || "");
      setIngestionVersion((version) => version + 1);
    };
    window.addEventListener("sprintsight-ingestion-updated", refresh);
    return () => window.removeEventListener("sprintsight-ingestion-updated", refresh);
  }, []);

  return { role, progressSignals };
}
