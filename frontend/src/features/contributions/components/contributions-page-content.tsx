"use client";

import { useEffect, useMemo, useState } from "react";

import { getContributionDataset, getContributionProjectOptions } from "@/features/contributions/data";
import { getProjectIngestion, readIngestionState } from "@/features/ingestion/state";

export default function ContributionsPageContent() {
  const projectOptions = useMemo(() => getContributionProjectOptions(), []);
  const [selectedProjectId, setSelectedProjectId] = useState(() => readIngestionState().selectedProjectId || projectOptions[0]?.id || "");
  const [ingestionVersion, setIngestionVersion] = useState(0);

  useEffect(() => {
    const refresh = () => setIngestionVersion((version) => version + 1);
    window.addEventListener("sprintsight-ingestion-updated", refresh);
    return () => window.removeEventListener("sprintsight-ingestion-updated", refresh);
  }, []);

  const dataset = useMemo(() => getContributionDataset(selectedProjectId), [selectedProjectId]);
  const liveIngestion = useMemo(() => {
    void ingestionVersion;
    return getProjectIngestion(selectedProjectId);
  }, [selectedProjectId, ingestionVersion]);

  return (
    <div className="space-y-5 p-8">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-4xl font-bold tracking-tight text-blue-950">Team Contribution Analysis</h1>
          <p className="mt-1 text-sm text-slate-500">
            {dataset.teamLabel} - {dataset.projectLabel} - {dataset.sprintLabel} aggregate contribution signals
          </p>
        </div>

        <div className="w-full max-w-sm">
          <label className="mb-1 block text-xs font-semibold uppercase tracking-wider text-slate-500">Project context</label>
          <select
            value={selectedProjectId}
            onChange={(event) => setSelectedProjectId(event.target.value)}
            className="h-11 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm text-slate-700 outline-none ring-blue-100 transition focus:border-blue-300 focus:ring-2"
          >
            {projectOptions.map((project) => (
              <option key={project.id} value={project.id}>
                {project.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {(liveIngestion.git || liveIngestion.jira) && (
        <section className="rounded-2xl border border-blue-200 bg-blue-50/50 p-4">
          <h2 className="text-lg font-semibold text-blue-950">Live Ingestion Totals</h2>
          <p className="mt-1 text-sm text-slate-700">
            {liveIngestion.git?.pagination?.total ?? liveIngestion.git?.commits.length ?? 0} commits, {liveIngestion.jira?.tickets.length ?? 0} Jira tickets, and {liveIngestion.documents} documents loaded for this project.
          </p>
          <p className="mt-1 text-xs text-slate-500">Per-student contribution attribution requires backend contributor IDs.</p>
        </section>
      )}

      <p className="text-sm text-slate-500">Individual student scoring is unavailable until the backend returns contributor identity mappings.</p>
    </div>
  );
}
