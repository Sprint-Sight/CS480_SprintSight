import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft, CalendarDays, TrendingUp } from "lucide-react";

import { getProjectById } from "@/features/projects/data";
import type { ProjectStatus, SprintStatus } from "@/features/projects/types";

function getProjectStatusStyles(status: ProjectStatus) {
  if (status === "At Risk") {
    return "bg-rose-50 text-rose-600";
  }

  if (status === "Completed") {
    return "bg-slate-100 text-slate-600";
  }

  return "bg-emerald-50 text-emerald-600";
}

function getSprintStatusStyles(status: SprintStatus) {
  if (status === "Needs Attention") {
    return "bg-rose-50 text-rose-600";
  }

  if (status === "Completed") {
    return "bg-slate-100 text-slate-600";
  }

  return "bg-emerald-50 text-emerald-600";
}

export default function ProjectSprintsPage({ params }: { params: { projectId: string } }) {
  const project = getProjectById(params.projectId);

  if (!project) {
    notFound();
  }

  return (
    <div className="space-y-6 p-8">
      <div className="flex items-center justify-between gap-4">
        <div>
          <Link href="/projects" className="inline-flex items-center gap-1 text-sm font-medium text-slate-500 transition hover:text-slate-700">
            <ArrowLeft className="h-4 w-4" />
            Back to projects
          </Link>
          <h1 className="mt-2 text-3xl font-bold tracking-tight text-blue-950">{project.name}</h1>
          <p className="mt-1 text-sm text-slate-500">
            {project.teamName} - {project.module}
          </p>
        </div>

        <span className={`rounded-full px-3 py-1 text-xs font-semibold ${getProjectStatusStyles(project.status)}`}>{project.status}</span>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <p className="text-sm text-slate-500">Current score</p>
          <p className="mt-2 text-3xl font-semibold text-blue-900">{project.score}/100</p>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <p className="text-sm text-slate-500">Overall completion</p>
          <p className="mt-2 text-3xl font-semibold text-blue-900">{project.completion}%</p>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <p className="text-sm text-slate-500">Current sprint</p>
          <p className="mt-2 text-3xl font-semibold text-blue-900">{project.currentSprint}</p>
        </div>
      </div>

      <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <h2 className="text-xl font-semibold text-slate-900">Sprint-level details</h2>
        <p className="mt-1 text-sm text-slate-500">Review delivery quality and progress for each sprint.</p>

        <div className="mt-5 space-y-3">
          {project.sprints.map((sprint) => (
            <Link
              key={sprint.id}
              href={`/projects/${project.id}/sprints/${sprint.id}`}
              className="block rounded-xl border border-slate-200 p-4 transition hover:border-blue-200 hover:bg-blue-50/30"
            >
              <div className="flex items-center justify-between gap-3">
                <div>
                  <h3 className="text-lg font-semibold text-blue-950">{sprint.name}</h3>
                  <div className="mt-1 flex items-center gap-2 text-sm text-slate-500">
                    <CalendarDays className="h-4 w-4" />
                    {sprint.startDate} to {sprint.endDate}
                  </div>
                </div>

                <span className={`rounded-full px-3 py-1 text-xs font-semibold ${getSprintStatusStyles(sprint.status)}`}>{sprint.status}</span>
              </div>

              <div className="mt-4 flex items-center justify-between text-sm">
                <div className="flex items-center gap-1.5 font-semibold text-blue-900">
                  <TrendingUp className="h-4 w-4" />
                  {sprint.score}/100
                </div>
                <div className="text-slate-500">{sprint.completion}% complete</div>
              </div>

              <div className="mt-2 h-2 rounded-full bg-slate-200">
                <div className="h-full rounded-full bg-blue-700" style={{ width: `${sprint.completion}%` }} />
              </div>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
