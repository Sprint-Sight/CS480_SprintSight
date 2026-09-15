"use client";

import Link from "next/link";
import { CalendarDays, CheckCircle2, CircleDotDashed, FileText, GitCommitHorizontal, ListChecks } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { getProjectsForSprintOverview, getSprintOverviewPayload } from "@/features/sprints/data";
import { getProjectIngestion, readIngestionState } from "@/features/ingestion/state";
import type { SprintOverviewPayload } from "@/features/sprints/types";

function formatDate(dateValue: string) {
  const formatted = new Date(`${dateValue}T00:00:00`).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });

  return formatted;
}

export default function SprintOverviewPageContent() {
  const projectOptions = useMemo(() => getProjectsForSprintOverview(), []);
  const [selectedProjectId, setSelectedProjectId] = useState(() => readIngestionState().selectedProjectId || projectOptions[0]?.id || "");
  const [ingestionVersion, setIngestionVersion] = useState(0);

  useEffect(() => {
    const refresh = () => setSelectedProjectId(readIngestionState().selectedProjectId || projectOptions[0]?.id || "");
    window.addEventListener("sprintsight-ingestion-updated", refresh);
    return () => window.removeEventListener("sprintsight-ingestion-updated", refresh);
  }, [projectOptions]);

  const liveIngestion = useMemo(() => {
    void ingestionVersion;
    return getProjectIngestion(selectedProjectId);
  }, [selectedProjectId, ingestionVersion]);

  useEffect(() => {
    const refresh = () => setIngestionVersion((version) => version + 1);
    window.addEventListener("sprintsight-ingestion-updated", refresh);
    return () => window.removeEventListener("sprintsight-ingestion-updated", refresh);
  }, []);

  const payload = useMemo(() => {
    if (!selectedProjectId) {
      return null;
    }

    const fixturePayload = getSprintOverviewPayload(selectedProjectId);
    if (fixturePayload) return fixturePayload;

    const state = readIngestionState();
    const gitRuns = Object.values(state.gitBySprint).filter((run) => run.project_id === selectedProjectId);
    const jiraRuns = Object.values(state.jiraBySprint).filter((run) => run.project_id === selectedProjectId);
    const sprintIds = [...new Set([...gitRuns.map((run) => run.sprint_id), ...jiraRuns.map((run) => run.sprint_id)])];
    if (sprintIds.length === 0) return null;

    const rows: SprintOverviewPayload["rows"] = sprintIds.map((sprintId) => {
      const git = gitRuns.find((run) => run.sprint_id === sprintId);
      const jira = jiraRuns.find((run) => run.sprint_id === sprintId);
      const capturedAt = git?.captured_at || jira?.captured_at || new Date().toISOString();
      const completion = git?.completion_percent || 0;
      return {
        projectId: selectedProjectId,
        projectName: "Project",
        projectTeam: "Selected project",
        sprint: {
          id: sprintId,
          name: sprintId,
          status: completion >= 100 ? "Completed" : "On Track",
          score: 0,
          completion,
          startDate: capturedAt.slice(0, 10),
          endDate: capturedAt.slice(0, 10),
        },
        activity: {
          commits: git?.pagination?.total ?? git?.commits.length ?? 0,
          tasks: jira?.tickets.length ?? 0,
          documents: state.documentCounts[selectedProjectId] || 0,
        },
        isCompleted: completion >= 100,
        isOngoing: completion < 100,
        displayStatus: completion >= 100 ? "Completed" : "In Progress",
      };
    });
    const totalCommits = rows.reduce((total, row) => total + row.activity.commits, 0);
    const totalTasks = rows.reduce((total, row) => total + row.activity.tasks, 0);
    const totalDocuments = state.documentCounts[selectedProjectId] || 0;
    return {
      project: {
        id: selectedProjectId,
        name: "Project",
        teamName: "Selected project",
        module: "",
        status: "Active",
        score: 0,
        completion: rows.at(-1)?.sprint.completion || 0,
        members: [],
        currentSprint: rows.at(-1)?.sprint.name || "",
        sprints: rows.map((row) => row.sprint),
      },
      rows,
      summary: { totalCommits, totalTasks, totalDocuments, averageScore: 0 },
    } satisfies SprintOverviewPayload;
  }, [selectedProjectId]);

  if (!payload) {
    return (
      <div className="p-8">
        <h1 className="text-3xl font-bold text-blue-950">Sprint Overview</h1>
        <p className="mt-2 text-sm text-slate-500">No project found for sprint overview.</p>
      </div>
    );
  }

  return (
    <div className="space-y-5 p-8">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-4xl font-bold tracking-tight text-blue-950">Sprint Overview</h1>
          <p className="mt-1 text-base text-slate-500">
            Track sprint progress and milestones for <span className="font-semibold text-slate-700">{payload.project.name}</span>
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
        <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
          <p className="text-xs text-slate-500">Total Commits</p>
          <p className="mt-1 text-4xl font-bold text-blue-900">{payload.summary.totalCommits}</p>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
          <p className="text-xs text-slate-500">Jira Tasks Completed</p>
          <p className="mt-1 text-4xl font-bold text-blue-900">{payload.summary.totalTasks}</p>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
          <p className="text-xs text-slate-500">Documents Uploaded</p>
          <p className="mt-1 text-4xl font-bold text-blue-900">{payload.summary.totalDocuments}</p>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
          <p className="text-xs text-slate-500">Avg Sprint Score</p>
          <p className="mt-1 text-4xl font-bold text-blue-900">{payload.summary.averageScore}</p>
        </div>
      </div>

      {(liveIngestion.git || liveIngestion.jira) && (
        <section className="rounded-2xl border border-blue-200 bg-blue-50/50 p-4">
          <h2 className="text-lg font-semibold text-blue-950">Live Ingestion Summary</h2>
          <div className="mt-3 grid grid-cols-1 gap-3 text-sm md:grid-cols-3">
            <p className="text-slate-700">Git commits: <strong>{liveIngestion.git?.pagination?.total ?? liveIngestion.git?.commits.length ?? 0}</strong></p>
            <p className="text-slate-700">Git churn: <strong>{liveIngestion.git?.code_churn ?? 0}</strong></p>
            <p className="text-slate-700">Jira tickets: <strong>{liveIngestion.jira?.tickets.length ?? 0}</strong></p>
          </div>
        </section>
      )}

      <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm md:p-6">
        <h2 className="text-2xl font-semibold text-blue-950">Sprint Timeline</h2>

        <div className="mt-5 space-y-4">
          {payload.rows.map((row) => (
            <article key={row.sprint.id} className="relative pl-10">
              <span className="absolute left-3 top-0 h-full w-px bg-slate-200" aria-hidden="true" />
              <span
                className={`absolute left-0 top-3 inline-flex h-6 w-6 items-center justify-center rounded-full border-4 border-white ${
                  row.isCompleted ? "bg-emerald-500" : "bg-blue-500"
                }`}
                aria-hidden="true"
              />

              <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <div className="flex items-center gap-2">
                      <h3 className="text-xl font-semibold text-blue-950">{row.sprint.name}</h3>
                      <span
                        className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold ${
                          row.isCompleted ? "bg-emerald-50 text-emerald-600" : "bg-blue-50 text-blue-600"
                        }`}
                      >
                        {row.isCompleted ? <CheckCircle2 className="h-3.5 w-3.5" /> : <CircleDotDashed className="h-3.5 w-3.5" />}
                        {row.displayStatus}
                      </span>
                    </div>

                    <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-slate-600">
                      <span className="inline-flex items-center gap-1">
                        <GitCommitHorizontal className="h-4 w-4" />
                        {row.activity.commits} commits
                      </span>
                      <span className="inline-flex items-center gap-1">
                        <ListChecks className="h-4 w-4" />
                        {row.activity.tasks} tasks
                      </span>
                      <span className="inline-flex items-center gap-1">
                        <FileText className="h-4 w-4" />
                        {row.activity.documents} docs
                      </span>
                    </div>
                  </div>

                  <div className="text-right text-xs text-slate-500">
                    {formatDate(row.sprint.startDate)} - {formatDate(row.sprint.endDate)}
                  </div>
                </div>

                <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
                  <div className="inline-flex items-center gap-1 text-sm font-semibold text-blue-900">
                    <CalendarDays className="h-4 w-4" />
                    Score {row.sprint.score}/100 | {row.sprint.completion}% complete
                  </div>
                  <Link
                    href={`/assessment-report?projectId=${encodeURIComponent(row.projectId)}&sprintId=${encodeURIComponent(row.sprint.id)}`}
                    className="inline-flex items-center rounded-lg border border-blue-200 bg-white px-3 py-1.5 text-xs font-semibold text-blue-700 transition hover:bg-blue-50"
                  >
                    Open Assessment Report
                  </Link>
                </div>
              </div>
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}