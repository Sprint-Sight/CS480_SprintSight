"use client";

import { useEffect, useMemo, useState } from "react";

import { getProjectIngestion, readIngestionState } from "@/features/ingestion/state";

export function useProgressData() {
  const [role, setRole] = useState<"student" | "instructor" | null>(null);
  const [selectedProjectId, setSelectedProjectId] = useState(() => readIngestionState().selectedProjectId || "");
  const [ingestionVersion, setIngestionVersion] = useState(0);
  const liveIngestion = useMemo(() => { void ingestionVersion; return getProjectIngestion(selectedProjectId); }, [selectedProjectId, ingestionVersion]);

  useEffect(() => setRole((sessionStorage.getItem("sprintsight-auth-role") as "student" | "instructor" | null) ?? "student"), []);
  useEffect(() => {
    const refresh = () => { setSelectedProjectId(readIngestionState().selectedProjectId || ""); setIngestionVersion((version) => version + 1); };
    window.addEventListener("sprintsight-ingestion-updated", refresh);
    return () => window.removeEventListener("sprintsight-ingestion-updated", refresh);
  }, []);

  return { role, liveIngestion };
}
