"use client";

import { ProgressLiveSignals } from "@/features/progress/components/progress-live-signals";
import { useProgressData } from "@/features/progress/hooks/use-progress-data";

export default function ProgressPageContent() {
  const { role, liveIngestion } = useProgressData();
  const live = Boolean(liveIngestion.git || liveIngestion.jira);
  return <div className="space-y-5 p-8"><div><h1 className="text-4xl font-bold tracking-tight text-blue-950">Comparative Progress</h1><p className="mt-1 text-sm text-slate-500">Track captured project activity across sprints.</p></div>{live ? <ProgressLiveSignals gitCommits={liveIngestion.git?.pagination?.total ?? liveIngestion.git?.commits.length ?? 0} codeChurn={liveIngestion.git?.code_churn ?? 0} jiraTickets={liveIngestion.jira?.tickets.length ?? 0} /> : <section className="rounded-2xl border border-dashed border-slate-300 bg-white p-8 text-center"><h2 className="text-lg font-semibold text-slate-900">No progress data available</h2><p className="mt-2 text-sm text-slate-500">Sync Git or Jira data for the selected project to view real progress signals.</p></section>}</div>;
}
