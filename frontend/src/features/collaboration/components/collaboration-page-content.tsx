"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import {
  getCollaborationDataset,
  getCollaborationProjectOptions,
  getContributionDataset,
} from "@/features/collaboration/data";
import type { HeatmapRow, MemberCommitMetric, WorkloadSlice } from "@/features/collaboration/types";
import { getProjectIngestion, readIngestionState } from "@/features/ingestion/state";
import type { CollaborationDataset, TeamRiskIndicator } from "@/features/collaboration/types";

function heatColor(score: number) {
  if (score <= 3) return "bg-sky-100 text-sky-700";
  if (score <= 7) return "bg-sky-300 text-sky-900";
  if (score <= 10) return "bg-[#2F6690] text-white";
  return "bg-[#1E3A8A] text-white";
}

export default function CollaborationPageContent() {
  const fallbackProjectOptions = useMemo(() => getCollaborationProjectOptions(), []);
  const projectOptions = useMemo(() => {
    const persistedProjectId = readIngestionState().selectedProjectId;
    if (!persistedProjectId || fallbackProjectOptions.some((option) => option.id === persistedProjectId)) return fallbackProjectOptions;
    return [{ id: persistedProjectId, label: "Live backend project" }, ...fallbackProjectOptions];
  }, [fallbackProjectOptions]);
  const [selectedProjectId, setSelectedProjectId] = useState(() => readIngestionState().selectedProjectId || projectOptions[0]?.id || "");
  const [role, setRole] = useState<"student" | "instructor" | null>(null);
  const [ingestionVersion, setIngestionVersion] = useState(0);

  // Load datasets for the selected project
  const collaborationData = useMemo(() => getCollaborationDataset(selectedProjectId), [selectedProjectId]);
  const contributionData = useMemo(() => getContributionDataset(selectedProjectId), [selectedProjectId]);

  const liveIngestion = useMemo(() => {
    void ingestionVersion;
    return getProjectIngestion(selectedProjectId);
  }, [selectedProjectId, ingestionVersion]);

  const liveCollaborationData = useMemo(() => {
    if (!liveIngestion.git && !liveIngestion.jira) return null;

    const commitsByAuthor = new Map<string, number>();
    for (const commit of liveIngestion.git?.commits || []) {
      const author = commit.author || "Unknown author";
      commitsByAuthor.set(author, (commitsByAuthor.get(author) || 0) + 1);
    }
    const commitsByMember: MemberCommitMetric[] = Array.from(commitsByAuthor.entries())
      .map(([member, commits]) => ({ member, commits }))
      .sort((left, right) => right.commits - left.commits);

    const ticketCounts = new Map<string, number>();
    for (const ticket of liveIngestion.jira?.tickets || []) {
      const owner = ticket.assignee || ticket.status || "Unassigned";
      ticketCounts.set(owner, (ticketCounts.get(owner) || 0) + 1);
    }
    const totalTickets = Array.from(ticketCounts.values()).reduce((sum, value) => sum + value, 0) || 1;
    const palette = ["#1E3A8A", "#2F6690", "#3E87B8", "#7CB9E8", "#A7D8F5"];
    const workloadDistribution: WorkloadSlice[] = Array.from(ticketCounts.entries()).map(([name, value], index) => ({
      name,
      value: Math.round((value / totalTickets) * 100),
      color: palette[index % palette.length],
    }));

    const timestamps = (liveIngestion.git?.commits || []).map((commit) => new Date(commit.timestamp).getTime()).filter(Number.isFinite);
    const firstTimestamp = timestamps.length ? Math.min(...timestamps) : Date.now();
    const heatmapByMember = new Map<string, [number, number, number, number]>();
    for (const commit of liveIngestion.git?.commits || []) {
      const author = commit.author || "Unknown author";
      const week = Math.min(3, Math.max(0, Math.floor((new Date(commit.timestamp).getTime() - firstTimestamp) / (7 * 24 * 60 * 60 * 1000))));
      const values = heatmapByMember.get(author) || [0, 0, 0, 0];
      values[week] += 1;
      heatmapByMember.set(author, values);
    }
    const participationHeatmap: HeatmapRow[] = Array.from(heatmapByMember.entries()).map(([member, values]) => ({
      member,
      week1: values[0],
      week2: values[1],
      week3: values[2],
      week4: values[3],
    }));

    const totalCommits = commitsByMember.reduce((sum, item) => sum + item.commits, 0);
    const balanceScore = commitsByMember.length
      ? Math.round((1 - (Math.max(...commitsByMember.map((item) => item.commits)) - Math.min(...commitsByMember.map((item) => item.commits))) / Math.max(1, totalCommits)) * 100)
      : 0;
    const liveRisk: TeamRiskIndicator = {
      team: "Current project",
      risk: balanceScore >= 70 ? "Low" : balanceScore >= 45 ? "Medium" : "High",
      summary: `${commitsByMember.length} Git authors across ${totalCommits} commits`,
      balanceScore,
    };

    return { commitsByMember, workloadDistribution, participationHeatmap, riskIndicators: [liveRisk] } satisfies Pick<CollaborationDataset, "commitsByMember" | "workloadDistribution" | "participationHeatmap" | "riskIndicators">;
  }, [liveIngestion]);

  const displayedCollaborationData = liveCollaborationData
    ? { ...collaborationData, ...liveCollaborationData }
    : collaborationData;

  useEffect(() => {
    const savedRole = sessionStorage.getItem("sprintsight-auth-role") as "student" | "instructor" | null;
    setRole(savedRole ?? "student");
  }, []);

  useEffect(() => {
    const refresh = () => {
      setSelectedProjectId(readIngestionState().selectedProjectId || "");
      setIngestionVersion((version) => version + 1);
    };
    window.addEventListener("sprintsight-ingestion-updated", refresh);
    return () => window.removeEventListener("sprintsight-ingestion-updated", refresh);
  }, []);

  return (
    <div className="space-y-6 p-8">
      {/* Header & Global Controls */}
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-4xl font-bold tracking-tight text-blue-950">Team Collaboration Analytics</h1>
          <p className="mt-1 text-sm text-slate-500">
            {collaborationData.subtitle} • {contributionData.sprintLabel}
          </p>
        </div>

        <div className="w-full max-w-sm">
          <label className="mb-1 block text-xs font-semibold uppercase tracking-wider text-slate-500">
            Project Context
          </label>
          <select
            value={selectedProjectId}
            onChange={(event) => setSelectedProjectId(event.target.value)}
            className="h-11 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm text-slate-700 outline-none ring-blue-100 transition focus:border-blue-300 focus:ring-2"
          >
            {projectOptions.map((project) => (
              <option key={project.id} value={project.id}>
                {project.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {(liveIngestion.git || liveIngestion.jira) && (
        <section className="rounded-2xl border border-blue-200 bg-blue-50/50 p-4">
          <h2 className="text-lg font-semibold text-blue-950">Live Project Signals</h2>
          <p className="mt-1 text-sm text-slate-700">
            {liveIngestion.git?.pagination?.total ?? liveIngestion.git?.commits.length ?? 0} Git commits, {liveIngestion.jira?.tickets.length ?? 0} Jira tickets, and {liveIngestion.documents} documents are available for this project.
          </p>
        </section>
      )}

      {/* Section 1: Macro Team Collaboration Charts */}
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
          <h2 className="text-sm font-semibold text-blue-950">Commits by Member</h2>
          <div className="mt-3 h-[240px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={displayedCollaborationData.commitsByMember}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
                <XAxis dataKey="member" axisLine={false} tickLine={false} tick={{ fill: "#64748b", fontSize: 12 }} />
                <YAxis axisLine={false} tickLine={false} tick={{ fill: "#64748b", fontSize: 12 }} />
                <Tooltip cursor={{ fill: "rgba(30, 58, 138, 0.06)" }} />
                <Bar dataKey="commits" radius={[6, 6, 0, 0]} fill="#2F5B85" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </section>

        <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
          <h2 className="text-sm font-semibold text-blue-950">Workload Distribution</h2>
          <div className="mt-3 h-[240px]">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={displayedCollaborationData.workloadDistribution}
                  dataKey="value"
                  nameKey="name"
                  innerRadius={48}
                  outerRadius={84}
                  paddingAngle={2}
                >
                  {displayedCollaborationData.workloadDistribution.map((slice) => (
                    <Cell key={slice.name} fill={slice.color} />
                  ))}
                </Pie>
                <Tooltip formatter={(value: number) => `${value}%`} />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <div className="flex flex-wrap gap-3 text-xs text-slate-600">
            {displayedCollaborationData.workloadDistribution.map((slice) => (
              <span key={slice.name} className="inline-flex items-center gap-1.5">
                <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: slice.color }} />
                {slice.name}
              </span>
            ))}
          </div>
        </section>
      </div>

      {/* Section 2: Team Participation Heatmap */}
      <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
        <h2 className="text-sm font-semibold text-blue-950">Team Participation Heatmap</h2>
        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[720px] border-separate border-spacing-y-2 text-sm">
            <thead>
              <tr className="text-left text-xs uppercase tracking-wide text-slate-500">
                <th className="px-2 py-1">Member</th>
                <th className="px-2 py-1 text-center">Week 1</th>
                <th className="px-2 py-1 text-center">Week 2</th>
                <th className="px-2 py-1 text-center">Week 3</th>
                <th className="px-2 py-1 text-center">Week 4</th>
              </tr>
            </thead>
            <tbody>
              {displayedCollaborationData.participationHeatmap.map((row) => (
                <tr key={row.member}>
                  <td className="px-2 py-2 font-medium text-slate-800">{row.member}</td>
                  <td className="px-1 py-1">
                    <div className={`rounded-md py-2 text-center text-xs font-semibold ${heatColor(row.week1)}`}>
                      {row.week1}
                    </div>
                  </td>
                  <td className="px-1 py-1">
                    <div className={`rounded-md py-2 text-center text-xs font-semibold ${heatColor(row.week2)}`}>
                      {row.week2}
                    </div>
                  </td>
                  <td className="px-1 py-1">
                    <div className={`rounded-md py-2 text-center text-xs font-semibold ${heatColor(row.week3)}`}>
                      {row.week3}
                    </div>
                  </td>
                  <td className="px-1 py-1">
                    <div className={`rounded-md py-2 text-center text-xs font-semibold ${heatColor(row.week4)}`}>
                      {row.week4}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="mt-2 flex items-center gap-3 text-xs text-slate-500">
          <span>Activity Level:</span>
          <span className="inline-flex items-center gap-1">
            <span className="h-2.5 w-2.5 rounded bg-sky-100" />
            Low
          </span>
          <span className="inline-flex items-center gap-1">
            <span className="h-2.5 w-2.5 rounded bg-sky-300" />
            Medium
          </span>
          <span className="inline-flex items-center gap-1">
            <span className="h-2.5 w-2.5 rounded bg-[#1E3A8A]" />
            High
          </span>
        </div>
      </section>

    </div>
  );
}