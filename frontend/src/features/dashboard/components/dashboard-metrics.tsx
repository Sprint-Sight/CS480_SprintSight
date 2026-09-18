import { Activity, AlertTriangle, GitCommit, ListChecks } from "lucide-react";
import type { GitMetrics, JiraSnapshot } from "@/features/dashboard/types";

type DashboardMetricsProps = { gitMetrics: GitMetrics | null; jiraSnapshot: JiraSnapshot | null };

export function DashboardMetrics({ gitMetrics, jiraSnapshot }: DashboardMetricsProps) {
  const completedTickets = jiraSnapshot?.tickets.filter((ticket) => /done|closed|resolved/i.test(ticket.status || "")).length || 0;
  const metrics = [
    { title: "Commits", value: gitMetrics?.commits.length ?? "-", sub: gitMetrics ? `${gitMetrics.commit_frequency.toFixed(1)} commits/day` : "No Git run loaded", icon: GitCommit, color: "text-blue-500" },
    { title: "Code Churn", value: gitMetrics?.code_churn ?? "-", sub: "Lines changed in this sprint", icon: Activity, color: "text-indigo-500" },
    { title: "Completion", value: gitMetrics?.completion_percent == null ? "-" : `${Math.round(gitMetrics.completion_percent)}%`, sub: gitMetrics?.assigned_story_points == null ? "Story points unavailable" : `${gitMetrics.assigned_story_points} assigned story points`, icon: ListChecks, color: "text-emerald-500" },
    { title: "Jira Tickets", value: jiraSnapshot?.tickets.length ?? "-", sub: jiraSnapshot ? `${completedTickets} completed` : "No processed Jira run", icon: AlertTriangle, color: "text-rose-500" },
  ];
  return <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-4">{metrics.map((metric) => <div key={metric.title} className="flex flex-col justify-between rounded-xl border border-slate-100 bg-white p-6 shadow-sm"><div className="mb-4 flex items-start justify-between"><div><p className="text-sm font-medium text-slate-500">{metric.title}</p><h3 className="mt-1 text-3xl font-bold text-slate-900">{metric.value}</h3></div><div className={`rounded-lg bg-slate-50 p-2 ${metric.color}`}><metric.icon className="h-5 w-5" /></div></div><p className="text-xs font-medium text-slate-500">{metric.sub}</p></div>)}</div>;
}
