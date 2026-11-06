"use client";

import { useEffect, useMemo, useState } from "react";

import { getProjectIngestion, readIngestionState } from "@/features/ingestion/state";
import { useIngestionSync } from "@/features/ingestion/hooks/use-ingestion-sync";
import type { ContributionDataset } from "@/features/contributions/types";
import { useSession } from "@/lib/auth/session";

export function useContributionsData() {
  const [selectedProjectId, setSelectedProjectId] = useState(() => readIngestionState().selectedProjectId || "");
  const [selectedCourseId, setSelectedCourseId] = useState(() => readIngestionState().selectedCourseId || "");
  const [ingestionVersion, setIngestionVersion] = useState(0);
  // Ingestion run endpoints are faculty-only, so students never trigger the sync.
  const canSync = useSession()?.user?.role === "instructor";
  const { isSyncing, syncError } = useIngestionSync({ projectId: selectedProjectId, courseId: selectedCourseId, enabled: canSync });
  const dataset = useMemo<ContributionDataset>(() => ({ projectId: selectedProjectId, teamLabel: "No team data", projectLabel: selectedProjectId || "No project selected", sprintLabel: readIngestionState().selectedSprintId || "No sprint selected", members: [] }), [selectedProjectId]);
  const liveIngestion = useMemo(() => { void ingestionVersion; return getProjectIngestion(selectedProjectId); }, [selectedProjectId, ingestionVersion]);

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

  return { dataset, liveIngestion, isSyncing, syncError };
}
