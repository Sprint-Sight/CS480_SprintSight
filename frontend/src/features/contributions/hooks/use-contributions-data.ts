"use client";

import { useEffect, useMemo, useState } from "react";

import { getProjectIngestion, readIngestionState } from "@/features/ingestion/state";
import type { ContributionDataset } from "@/features/contributions/types";

export function useContributionsData() {
  const [selectedProjectId, setSelectedProjectId] = useState(() => readIngestionState().selectedProjectId || "");
  const [ingestionVersion, setIngestionVersion] = useState(0);
  const dataset = useMemo<ContributionDataset>(() => ({ projectId: selectedProjectId, teamLabel: "No team data", projectLabel: selectedProjectId || "No project selected", sprintLabel: readIngestionState().selectedSprintId || "No sprint selected", members: [] }), [selectedProjectId]);
  const liveIngestion = useMemo(() => { void ingestionVersion; return getProjectIngestion(selectedProjectId); }, [selectedProjectId, ingestionVersion]);

  useEffect(() => {
    const refresh = () => {
      setSelectedProjectId(readIngestionState().selectedProjectId || "");
      setIngestionVersion((version) => version + 1);
    };
    window.addEventListener("sprintsight-ingestion-updated", refresh);
    return () => window.removeEventListener("sprintsight-ingestion-updated", refresh);
  }, []);

  return { dataset, liveIngestion };
}
