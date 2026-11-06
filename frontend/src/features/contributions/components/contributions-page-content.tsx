"use client";

import { ContributionsHeader } from "@/features/contributions/components/contributions-header";
import { ContributionsLiveSummary } from "@/features/contributions/components/contributions-live-summary";
import { useContributionsData } from "@/features/contributions/hooks/use-contributions-data";

export default function ContributionsPageContent() {
  const { dataset, liveTotals, isSyncing, syncError } = useContributionsData();
  const hasLiveData = liveTotals.hasData;
  return <div className="space-y-5 p-8"><ContributionsHeader dataset={dataset} />{isSyncing && !hasLiveData && <p role="status" className="text-sm text-slate-500">Loading captured activity...</p>}{syncError && <p role="alert" className="text-sm text-rose-600">{syncError}</p>}{hasLiveData && <ContributionsLiveSummary gitCommits={liveTotals.gitCommits} jiraTickets={liveTotals.jiraTickets} />}<p className="text-sm text-slate-500">Individual student scoring is unavailable until the backend returns contributor identity mappings.</p></div>;
}
