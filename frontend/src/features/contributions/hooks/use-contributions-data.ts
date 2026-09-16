"use client";

import { useEffect, useMemo, useState } from "react";

import { getContributionDataset, getContributionProjectOptions } from "@/features/contributions/data";
import { getProjectIngestion, readIngestionState } from "@/features/ingestion/state";

export function useContributionsData() {
  const projectOptions = useMemo(() => getContributionProjectOptions(), []);
  const [selectedProjectId, setSelectedProjectId] = useState(() => readIngestionState().selectedProjectId || projectOptions[0]?.id || "");
  const [ingestionVersion, setIngestionVersion] = useState(0);
  const dataset = useMemo(() => getContributionDataset(selectedProjectId), [selectedProjectId]);
  const liveIngestion = useMemo(() => { void ingestionVersion; return getProjectIngestion(selectedProjectId); }, [selectedProjectId, ingestionVersion]);

  useEffect(() => {
    const refresh = () => setIngestionVersion((version) => version + 1);
    window.addEventListener("sprintsight-ingestion-updated", refresh);
    return () => window.removeEventListener("sprintsight-ingestion-updated", refresh);
  }, []);

  return { projectOptions, selectedProjectId, setSelectedProjectId, dataset, liveIngestion };
}
