"use client";

import { useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";

import { CommitActivityChart } from "@/features/dashboard/components/commit-activity-chart";
import { DashboardHeader } from "@/features/dashboard/components/dashboard-header";
import { DashboardMetrics } from "@/features/dashboard/components/dashboard-metrics";
import { JiraWorkList } from "@/features/dashboard/components/jira-work-list";
import { RecentGitEvidence } from "@/features/dashboard/components/recent-git-evidence";
import { StudentDashboardSummary } from "@/features/dashboard/components/student-dashboard-summary";
import { useDashboardData } from "@/features/dashboard/hooks/use-dashboard-data";
import { useStudentProjectContext } from "@/features/student/hooks/use-student-project-context";

export default function DashboardPageContent() {
  const router = useRouter();
  const dashboard = useDashboardData(router);
  const studentContext = useStudentProjectContext(dashboard.role === "student");

  if (!dashboard.mounted) return null;

  if (dashboard.role === "student") {
    return (
      <div className="mx-auto w-full min-w-0 max-w-7xl space-y-6 bg-slate-50 p-4 sm:space-y-8 sm:p-6 lg:p-8">
        <DashboardHeader role={dashboard.role} fullName={dashboard.fullName} />
        <StudentDashboardSummary
          project={studentContext.project}
          report={studentContext.report}
          isLoading={studentContext.isLoading}
          error={studentContext.error}
        />
      </div>
    );
  }

  return (
    <div className="mx-auto w-full min-w-0 max-w-7xl space-y-6 bg-slate-50 p-4 sm:space-y-8 sm:p-6 lg:p-8">
      <DashboardHeader
        role={dashboard.role}
        fullName={dashboard.fullName}
      />
      {dashboard.isLoading && <div className="flex items-center gap-2 text-sm text-slate-500"><Loader2 className="h-4 w-4 animate-spin" /> Loading ingested project data...</div>}
      {dashboard.loadError && <p className="text-sm text-rose-600">{dashboard.loadError}</p>}
      <DashboardMetrics gitMetrics={dashboard.gitMetrics} jiraSnapshot={dashboard.jiraSnapshot} />
      <div className="grid min-w-0 grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="min-w-0 lg:col-span-2"><CommitActivityChart commits={dashboard.gitMetrics?.commits || []} /></div>
        <JiraWorkList jiraSnapshot={dashboard.jiraSnapshot} isLoading={dashboard.isLoading} />
      </div>
      <RecentGitEvidence commits={dashboard.gitMetrics?.commits || []} isLoading={dashboard.isLoading} />
    </div>
  );
}
