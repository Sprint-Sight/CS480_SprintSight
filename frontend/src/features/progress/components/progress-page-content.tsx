"use client";

import { PROGRESS_DATA } from "@/features/progress/data";
import { ProgressLiveSignals } from "@/features/progress/components/progress-live-signals";
import { ProgressMetricCard } from "@/features/progress/components/progress-metric-card";
import { ProgressRegressionAlerts } from "@/features/progress/components/progress-regression-alerts";
import { ProgressTeamComparison } from "@/features/progress/components/progress-team-comparison";
import { ProgressTrendChart } from "@/features/progress/components/progress-trend-chart";
import { useProgressData } from "@/features/progress/hooks/use-progress-data";

export default function ProgressPageContent() {
  const { role, liveIngestion } = useProgressData();
  const latest = PROGRESS_DATA.latestScores;
  const deltas = PROGRESS_DATA.scoreDeltas;
  const live = Boolean(liveIngestion.git || liveIngestion.jira);
  return <div className="space-y-5 p-8"><div><h1 className="text-4xl font-bold tracking-tight text-blue-950">Comparative Progress</h1><p className="mt-1 text-sm text-slate-500">Track performance trends across multiple sprints and identify improvements or regressions</p></div><div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-5"><ProgressMetricCard label="Requirements" score={latest.requirements} delta={deltas.requirements} /><ProgressMetricCard label="Code Quality" score={latest.codeQuality} delta={deltas.codeQuality} /><ProgressMetricCard label="Testing" score={latest.testing} delta={deltas.testing} /><ProgressMetricCard label="Documentation" score={latest.documentation} delta={deltas.documentation} /><ProgressMetricCard label="Collaboration" score={latest.collaboration} delta={deltas.collaboration} /></div>{live && <ProgressLiveSignals gitCommits={liveIngestion.git?.pagination?.total ?? liveIngestion.git?.commits.length ?? 0} codeChurn={liveIngestion.git?.code_churn ?? 0} jiraTickets={liveIngestion.jira?.tickets.length ?? 0} />}<ProgressTrendChart data={PROGRESS_DATA.categoryTrend} />{role === "instructor" && <><ProgressTeamComparison data={PROGRESS_DATA.teamComparison} /><ProgressRegressionAlerts alerts={PROGRESS_DATA.regressionAlerts} /></>}</div>;
}
