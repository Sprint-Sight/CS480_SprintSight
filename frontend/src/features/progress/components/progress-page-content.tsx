"use client";

import { useEffect, useState } from "react";
import { ProgressLiveSignals } from "@/features/progress/components/progress-live-signals";
import { useProgressData } from "@/features/progress/hooks/use-progress-data";

export default function ProgressPageContent() {
  const [role, setRole] = useState<string | null>(null);
  useEffect(() => setRole(sessionStorage.getItem("sprintsight-auth-role")), []);
  if (role === "student") return <StudentProgressUnavailable />;
  if (!role) return null;
  return <InstructorProgressPage />;
}

function InstructorProgressPage() {
  const { progressSignals } = useProgressData();
  return <div className="space-y-5 p-8"><div><h1 className="text-4xl font-bold tracking-tight text-blue-950">Comparative Progress</h1><p className="mt-1 text-sm text-slate-500">Track captured project activity across all sprints.</p></div>{progressSignals.hasData ? <ProgressLiveSignals gitCommits={progressSignals.gitCommits} codeChurn={progressSignals.codeChurn} jiraTickets={progressSignals.jiraTickets} /> : <section className="rounded-2xl border border-dashed border-slate-300 bg-white p-8 text-center"><h2 className="text-lg font-semibold text-slate-900">No progress data available</h2><p className="mt-2 text-sm text-slate-500">Sync Git or Jira data for the selected project to view real progress signals.</p></section>}</div>;
}

function StudentProgressUnavailable() {
  return <div className="space-y-5 p-8"><div><h1 className="text-4xl font-bold tracking-tight text-blue-950">Comparative Progress</h1><p className="mt-1 text-sm text-slate-500">Project-wide activity analytics are not available to students.</p></div><section className="rounded-2xl border border-dashed border-slate-300 bg-white p-8 text-center"><h2 className="text-lg font-semibold text-slate-900">Progress analytics unavailable</h2><p className="mt-2 text-sm text-slate-500">Your published assessment reports provide the available progress information.</p></section></div>;
}
