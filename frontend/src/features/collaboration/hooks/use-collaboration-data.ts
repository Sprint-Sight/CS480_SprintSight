"use client";

import { useEffect, useMemo, useState } from "react";

import { aggregateCollaborationMetrics } from "@/features/collaboration/aggregate-collaboration-metrics";
import type { aggregateProjectSprints } from "@/features/collaboration/aggregate-project-sprints";
import { fetchCollaborationProjectData } from "@/features/collaboration/collaboration-api";
import type { CollaborationDataset } from "@/features/collaboration/types";
import { readIngestionState } from "@/features/ingestion/state";

const emptyIngestion: ReturnType<typeof aggregateProjectSprints> = {
  git: undefined,
  jira: undefined,
  documents: 0,
};

export function useCollaborationData() {
  const [selectedProjectId, setSelectedProjectId] = useState(
    () => readIngestionState().selectedProjectId || "",
  );
  const [refreshVersion, setRefreshVersion] = useState(0);
  const [projectLabel, setProjectLabel] = useState("No project selected");
  const [memberNames, setMemberNames] = useState<Map<string, string>>(() => new Map());
  const [liveIngestion, setLiveIngestion] = useState<ReturnType<typeof aggregateProjectSprints>>(emptyIngestion);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const refresh = () => {
      const state = readIngestionState();
      setSelectedProjectId(state.selectedProjectId || "");
      setRefreshVersion((version) => version + 1);
    };
    window.addEventListener("sprintsight-ingestion-updated", refresh);
    return () => window.removeEventListener("sprintsight-ingestion-updated", refresh);
  }, []);

  useEffect(() => {
    let cancelled = false;
    if (!selectedProjectId) {
      setProjectLabel("No project selected");
      setMemberNames(new Map());
      setLiveIngestion(emptyIngestion);
      setError("");
      setIsLoading(false);
      return;
    }

    setIsLoading(true);
    setError("");
    setProjectLabel("Loading project...");
    setMemberNames(new Map());
    setLiveIngestion(emptyIngestion);
    void fetchCollaborationProjectData(selectedProjectId, readIngestionState())
      .then(({ projectLabel: label, memberNames: names, ingestion }) => {
        if (cancelled) return;
        setProjectLabel(label);
        setMemberNames(names);
        setLiveIngestion(ingestion);
      })
      .catch((loadError: unknown) => {
        if (cancelled) return;
        setLiveIngestion(emptyIngestion);
        setError(loadError instanceof Error ? loadError.message : "Unable to load Collaboration data.");
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [selectedProjectId, refreshVersion]);

  const metrics = useMemo(
    () => aggregateCollaborationMetrics(liveIngestion, memberNames),
    [liveIngestion, memberNames],
  );
  const collaborationData = useMemo<CollaborationDataset>(() => ({
    projectId: selectedProjectId,
    projectLabel,
    subtitle: metrics
      ? "Analytics derived from the selected project's captured Git and Jira data."
      : "No collaboration data is available for the selected project.",
    commitsByMember: metrics?.commitsByMember || [],
    unmatchedCommits: metrics?.unmatchedCommits || [],
    workloadDistribution: metrics?.workloadDistribution || [],
    participationHeatmap: metrics?.participationHeatmap || [],
    riskIndicators: metrics?.riskIndicators || [],
  }), [metrics, projectLabel, selectedProjectId]);

  return { selectedProjectId, collaborationData, liveIngestion, isLoading, error };
}
