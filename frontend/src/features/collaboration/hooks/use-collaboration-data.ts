"use client";

import { useEffect, useMemo, useState } from "react";

import type { CollaborationDataset, HeatmapRow, MemberCommitMetric, WorkloadSlice } from "@/features/collaboration/types";
import { getProjectIngestion, readIngestionState } from "@/features/ingestion/state";

type LiveCollaboration = Pick<CollaborationDataset, "commitsByMember" | "workloadDistribution" | "participationHeatmap" | "riskIndicators">;

export function useCollaborationData() {
  const [selectedProjectId, setSelectedProjectId] = useState(() => readIngestionState().selectedProjectId || "");
  const [selectedSprintId, setSelectedSprintId] = useState(() => readIngestionState().selectedSprintId || "sprint-1");
  const [ingestionVersion, setIngestionVersion] = useState(0);
  const [role, setRole] = useState<"student" | "instructor" | null>(null);

  const liveIngestion = useMemo(() => {
    void ingestionVersion;
    const jiraSnapshots = Object.values(readIngestionState().jiraBySprint)
      .filter((snapshot) => snapshot.project_id === selectedProjectId)
      .sort((left, right) => right.captured_at.localeCompare(left.captured_at));
    const selectedSprintHasJira = jiraSnapshots.some(
      (snapshot) => snapshot.sprint_id === selectedSprintId,
    );
    const sprintId = selectedSprintHasJira
      ? selectedSprintId
      : jiraSnapshots[0]?.sprint_id || selectedSprintId;
    return getProjectIngestion(selectedProjectId, sprintId);
  }, [selectedProjectId, selectedSprintId, ingestionVersion]);

  const liveCollaborationData = useMemo<LiveCollaboration | null>(() => {
    if (!liveIngestion.git && !liveIngestion.jira) return null;
    const metricsByAuthor = new Map<string, MemberCommitMetric>();
    for (const commit of liveIngestion.git?.commits || []) {
      const author = commit.author || "Unknown author";
      const metric = metricsByAuthor.get(author) || { member: author, commits: 0, linesChanged: 0 };
      metric.commits += 1;
      metric.linesChanged += commit.lines_added + commit.lines_deleted;
      metricsByAuthor.set(author, metric);
    }
    const commitsByMember = Array.from(metricsByAuthor.values()).sort((left, right) => right.commits - left.commits);
    const ticketCounts = new Map<string, number>();
    for (const ticket of liveIngestion.jira?.tickets || []) {
      const owner = ticket.assignee || "Unassigned";
      ticketCounts.set(owner, (ticketCounts.get(owner) || 0) + 1);
    }
    const totalTickets = Array.from(ticketCounts.values()).reduce((sum, value) => sum + value, 0) || 1;
    const palette = ["#1E3A8A", "#2F6690", "#3E87B8", "#7CB9E8", "#A7D8F5"];
    const workloadDistribution: WorkloadSlice[] = Array.from(ticketCounts.entries()).map(([name, value], index) => ({ name, value: Math.round((value / totalTickets) * 100), color: palette[index % palette.length] }));
    const timestamps = (liveIngestion.git?.commits || []).map((commit) => new Date(commit.timestamp).getTime()).filter(Number.isFinite);
    const firstTimestamp = timestamps.length ? Math.min(...timestamps) : Date.now();
    const heatmapByMember = new Map<string, [number, number, number, number]>();
    for (const commit of liveIngestion.git?.commits || []) {
      const values = heatmapByMember.get(commit.author || "Unknown author") || [0, 0, 0, 0];
      const week = Math.min(3, Math.max(0, Math.floor((new Date(commit.timestamp).getTime() - firstTimestamp) / (7 * 24 * 60 * 60 * 1000))));
      values[week] += 1;
      heatmapByMember.set(commit.author || "Unknown author", values);
    }
    const participationHeatmap: HeatmapRow[] = Array.from(heatmapByMember.entries()).map(([member, values]) => ({ member, week1: values[0], week2: values[1], week3: values[2], week4: values[3] }));
    const totalCommits = commitsByMember.reduce((sum, item) => sum + item.commits, 0);
    const balanceScore = commitsByMember.length ? Math.round((1 - (Math.max(...commitsByMember.map((item) => item.commits)) - Math.min(...commitsByMember.map((item) => item.commits))) / Math.max(1, totalCommits)) * 100) : 0;
    return { commitsByMember, workloadDistribution, participationHeatmap, riskIndicators: [{ team: "Selected project", risk: balanceScore >= 70 ? "Low" : balanceScore >= 45 ? "Medium" : "High", summary: `${commitsByMember.length} Git authors across ${totalCommits} commits`, balanceScore }] };
  }, [liveIngestion]);
  const collaborationData = useMemo<CollaborationDataset>(() => ({ projectId: selectedProjectId, projectLabel: selectedProjectId || "No project selected", subtitle: liveCollaborationData ? "Analytics derived from captured Git and Jira data." : "No collaboration data is available for the selected project.", commitsByMember: liveCollaborationData?.commitsByMember || [], workloadDistribution: liveCollaborationData?.workloadDistribution || [], participationHeatmap: liveCollaborationData?.participationHeatmap || [], riskIndicators: liveCollaborationData?.riskIndicators || [] }), [liveCollaborationData, selectedProjectId]);

  useEffect(() => setRole((sessionStorage.getItem("sprintsight-auth-role") as "student" | "instructor" | null) ?? "student"), []);
  useEffect(() => {
    const refresh = () => {
      const state = readIngestionState();
      setSelectedProjectId(state.selectedProjectId || "");
      setSelectedSprintId(state.selectedSprintId || "sprint-1");
      setIngestionVersion((version) => version + 1);
    };
    window.addEventListener("sprintsight-ingestion-updated", refresh);
    return () => window.removeEventListener("sprintsight-ingestion-updated", refresh);
  }, []);

  return { role, selectedProjectId, selectedSprintId, setSelectedProjectId, collaborationData, liveIngestion };
}
