"use client";

import { ContributionsHeader } from "@/features/contributions/components/contributions-header";
import { ContributionsLiveSummary } from "@/features/contributions/components/contributions-live-summary";
import { useContributionsData } from "@/features/contributions/hooks/use-contributions-data";

export default function ContributionsPageContent() {
  const { projectOptions, selectedProjectId, setSelectedProjectId, dataset, liveIngestion } = useContributionsData();
  const hasLiveData = Boolean(liveIngestion.git || liveIngestion.jira);
  return <div className="space-y-5 p-8"><ContributionsHeader dataset={dataset} projectOptions={projectOptions} selectedProjectId={selectedProjectId} onProjectChange={setSelectedProjectId} />{hasLiveData && <ContributionsLiveSummary gitCommits={liveIngestion.git?.pagination?.total ?? liveIngestion.git?.commits.length ?? 0} jiraTickets={liveIngestion.jira?.tickets.length ?? 0} documents={liveIngestion.documents} />}<p className="text-sm text-slate-500">Individual student scoring is unavailable until the backend returns contributor identity mappings.</p></div>;
}
