"use client";

import { useEffect, useMemo, useState } from "react";

import { getProjectIngestion, readIngestionState } from "@/features/ingestion/state";
import { useIngestionSync } from "@/features/ingestion/hooks/use-ingestion-sync";
import type { SprintOverviewPayload } from "@/features/sprints/types";

export function useSprintOverviewData() {
  const [selectedProjectId, setSelectedProjectId] = useState(() => readIngestionState().selectedProjectId || "");
  const [selectedCourseId, setSelectedCourseId] = useState(() => readIngestionState().selectedCourseId || "");
  const [ingestionVersion, setIngestionVersion] = useState(0);
  const { isSyncing, syncError } = useIngestionSync({ projectId: selectedProjectId, courseId: selectedCourseId });
  const liveIngestion = useMemo(() => { void ingestionVersion; return getProjectIngestion(selectedProjectId); }, [selectedProjectId, ingestionVersion]);
  // This page intentionally aggregates every captured sprint for the selected project.
  const payload = useMemo<SprintOverviewPayload | null>(() => {
    void ingestionVersion; // re-read the store after a background sync
    if (!selectedProjectId) return null;
    const state = readIngestionState();
    const gitRuns = Object.values(state.gitBySprint).filter((run) => run.project_id === selectedProjectId);
    const jiraRuns = Object.values(state.jiraBySprint).filter((run) => run.project_id === selectedProjectId);
    const sprintIds = [...new Set([...gitRuns.map((run) => run.sprint_id), ...jiraRuns.map((run) => run.sprint_id)])];
    if (!sprintIds.length) return null;
    const rows: SprintOverviewPayload["rows"] = sprintIds.map((sprintId) => {
      const git = gitRuns.find((run) => run.sprint_id === sprintId); const jira = jiraRuns.find((run) => run.sprint_id === sprintId); const capturedAt = git?.captured_at || jira?.captured_at || new Date().toISOString(); const completion = git?.completion_percent || 0;
      return { projectId: selectedProjectId, projectName: "Project", projectTeam: "Selected project", sprint: { id: sprintId, name: sprintId, status: completion >= 100 ? "Completed" : "On Track", score: 0, completion, startDate: capturedAt.slice(0, 10), endDate: capturedAt.slice(0, 10) }, activity: { commits: git?.pagination?.total ?? git?.commits.length ?? 0, tasks: jira?.tickets.length ?? 0, documents: state.documentCounts[selectedProjectId] || 0 }, isCompleted: completion >= 100, isOngoing: completion < 100, displayStatus: completion >= 100 ? "Completed" : "In Progress" };
    });
    return { project: { id: selectedProjectId, name: "Project", teamName: "Selected project", module: "", status: "Active", score: 0, completion: rows.at(-1)?.sprint.completion || 0, members: [], currentSprint: rows.at(-1)?.sprint.name || "", sprints: rows.map((row) => row.sprint) }, rows, summary: { totalCommits: rows.reduce((total, row) => total + row.activity.commits, 0), totalTasks: rows.reduce((total, row) => total + row.activity.tasks, 0), totalDocuments: state.documentCounts[selectedProjectId] || 0 } } satisfies SprintOverviewPayload;
  }, [selectedProjectId, ingestionVersion]);
  useEffect(() => { const refresh = () => { const state = readIngestionState(); setSelectedProjectId(state.selectedProjectId || ""); setSelectedCourseId(state.selectedCourseId || ""); setIngestionVersion((version) => version + 1); }; window.addEventListener("sprintsight-ingestion-updated", refresh); return () => window.removeEventListener("sprintsight-ingestion-updated", refresh); }, []);
  return { selectedProjectId, payload, liveIngestion, isSyncing, syncError };
}
