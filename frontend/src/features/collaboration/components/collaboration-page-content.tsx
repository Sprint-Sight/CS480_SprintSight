"use client";

import { useEffect, useState } from "react";
import { CollaborationCharts } from "@/features/collaboration/components/collaboration-charts";
import { CollaborationHeader } from "@/features/collaboration/components/collaboration-header";
import { CollaborationHeatmap } from "@/features/collaboration/components/collaboration-heatmap";
import { useCollaborationData } from "@/features/collaboration/hooks/use-collaboration-data";
import type { CollaborationMetric } from "@/features/collaboration/types";

export default function CollaborationPageContent() {
  const [role, setRole] = useState<string | null>(null);
  useEffect(() => setRole(sessionStorage.getItem("sprintsight-auth-role")), []);
  if (role === "student") return <StudentCollaborationUnavailable />;
  if (!role) return null;
  return <InstructorCollaborationPage />;
}

function InstructorCollaborationPage() {
  const { collaborationData, liveIngestion, isLoading, error, selectedProjectId } = useCollaborationData();
  const [comparisonMetric, setComparisonMetric] = useState<CollaborationMetric>("commits");
  return (
    <div className="space-y-6 p-8">
      <CollaborationHeader data={collaborationData} />
      {isLoading && <p role="status" className="text-sm text-slate-600">Loading project collaboration data...</p>}
      {error && <p role="alert" className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">{error}</p>}
      {!isLoading && !error && !selectedProjectId && (
        <p role="status" className="rounded-xl border border-dashed border-slate-300 bg-white p-6 text-center text-sm text-slate-600">
          Select a project from the shared scope bar to view its collaboration data.
        </p>
      )}
      {!isLoading && !error && selectedProjectId && !liveIngestion.git && !liveIngestion.jira && (
        <p role="status" className="rounded-xl border border-dashed border-slate-300 bg-white p-6 text-center text-sm text-slate-600">
          No captured Git commits or processed Jira tickets are available for this project.
        </p>
      )}
      {(liveIngestion.git || liveIngestion.jira) && (
        <section className="rounded-2xl border border-blue-200 bg-blue-50/50 p-4">
          <h2 className="text-lg font-semibold text-blue-950">Live Project Signals</h2>
          <p className="mt-1 text-sm text-slate-700">
            {liveIngestion.git?.commits.length ?? 0} unique Git commits, {liveIngestion.jira?.tickets.length ?? 0} unique Jira tickets, and {liveIngestion.documents} documents are available for this project.
          </p>
        </section>
      )}
      <CollaborationCharts
        commitsByMember={collaborationData.commitsByMember}
        workloadDistribution={collaborationData.workloadDistribution}
        comparisonMetric={comparisonMetric}
        onComparisonMetricChange={setComparisonMetric}
      />
      <CollaborationHeatmap rows={collaborationData.participationHeatmap} />
    </div>
  );
}

function StudentCollaborationUnavailable() {
  return <div className="space-y-6 p-8"><div><h1 className="text-4xl font-bold tracking-tight text-blue-950">Collaboration</h1><p className="mt-1 text-sm text-slate-500">Individual Git and Jira activity is not available in the student view.</p></div><section className="rounded-2xl border border-dashed border-slate-300 bg-white p-8 text-center"><h2 className="text-lg font-semibold text-slate-900">Collaboration analytics unavailable</h2><p className="mt-2 text-sm text-slate-500">Review your published assessment report for instructor feedback.</p></section></div>;
}
