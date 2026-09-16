"use client";

import { CollaborationCharts } from "@/features/collaboration/components/collaboration-charts";
import { CollaborationHeader } from "@/features/collaboration/components/collaboration-header";
import { CollaborationHeatmap } from "@/features/collaboration/components/collaboration-heatmap";
import { useCollaborationData } from "@/features/collaboration/hooks/use-collaboration-data";

export default function CollaborationPageContent() {
  const { projectOptions, selectedProjectId, setSelectedProjectId, collaborationData, liveIngestion } = useCollaborationData();
  return <div className="space-y-6 p-8"><CollaborationHeader data={collaborationData} projectOptions={projectOptions} selectedProjectId={selectedProjectId} onProjectChange={setSelectedProjectId} />{(liveIngestion.git || liveIngestion.jira) && <section className="rounded-2xl border border-blue-200 bg-blue-50/50 p-4"><h2 className="text-lg font-semibold text-blue-950">Live Project Signals</h2><p className="mt-1 text-sm text-slate-700">{liveIngestion.git?.pagination?.total ?? liveIngestion.git?.commits.length ?? 0} Git commits, {liveIngestion.jira?.tickets.length ?? 0} Jira tickets, and {liveIngestion.documents} documents are available for this project.</p></section>}<CollaborationCharts commitsByMember={collaborationData.commitsByMember} workloadDistribution={collaborationData.workloadDistribution} /><CollaborationHeatmap rows={collaborationData.participationHeatmap} /></div>;
}
