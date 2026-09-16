"use client";

import { useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";

import { CommitActivityChart } from "@/features/dashboard/components/commit-activity-chart";
import { DashboardHeader } from "@/features/dashboard/components/dashboard-header";
import { DashboardMetrics } from "@/features/dashboard/components/dashboard-metrics";
import { JiraWorkList } from "@/features/dashboard/components/jira-work-list";
import { RecentGitEvidence } from "@/features/dashboard/components/recent-git-evidence";
import { useDashboardData } from "@/features/dashboard/hooks/use-dashboard-data";

export default function DashboardPageContent() {
  const router = useRouter();
  const dashboard = useDashboardData(router);

  if (!dashboard.mounted) return null;

  return (
    <div className="mx-auto min-h-screen max-w-7xl space-y-8 bg-slate-50 p-8">
      <DashboardHeader
        role={dashboard.role}
        fullName={dashboard.fullName}
      />
      {dashboard.isLoading && <div className="flex items-center gap-2 text-sm text-slate-500"><Loader2 className="h-4 w-4 animate-spin" /> Loading ingested project data...</div>}
      {dashboard.loadError && <p className="text-sm text-rose-600">{dashboard.loadError}</p>}
      <DashboardMetrics gitMetrics={dashboard.gitMetrics} jiraSnapshot={dashboard.jiraSnapshot} />
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2"><CommitActivityChart commits={dashboard.gitMetrics?.commits || []} /></div>
        <JiraWorkList jiraSnapshot={dashboard.jiraSnapshot} isLoading={dashboard.isLoading} />
      </div>
      <RecentGitEvidence commits={dashboard.gitMetrics?.commits || []} isLoading={dashboard.isLoading} />
    </div>
  );
}
