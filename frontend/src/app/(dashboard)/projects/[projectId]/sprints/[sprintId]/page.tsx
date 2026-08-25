import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft, CalendarDays, FileCheck2, TrendingUp } from "lucide-react";

import { getSprintByProjectAndId } from "@/features/projects/data";
import type { SprintStatus } from "@/features/projects/types";

function getSprintStatusStyles(status: SprintStatus) {
  if (status === "Needs Attention") {
    return "bg-rose-50 text-rose-600";
  }

  if (status === "Completed") {
    return "bg-slate-100 text-slate-600";
  }

  return "bg-emerald-50 text-emerald-600";
}

export default function SprintDetailsPage({ params }: { params: { projectId: string; sprintId: string } }) {
  const payload = getSprintByProjectAndId(params.projectId, params.sprintId);

  if (!payload) {
    notFound();
  }

  const { project, sprint } = payload;

  return (
    <div className="space-y-6 p-8">
      <div>
        <Link
          href={`/projects/${project.id}/sprints`}
          className="inline-flex items-center gap-1 text-sm font-medium text-slate-500 transition hover:text-slate-700"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to {project.name} sprints
        </Link>

        <h1 className="mt-2 text-3xl font-bold tracking-tight text-blue-950">
          {project.name} - {sprint.name}
        </h1>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <p className="text-sm text-slate-500">Sprint score</p>
          <p className="mt-2 flex items-center gap-2 text-3xl font-semibold text-blue-900">
            <TrendingUp className="h-6 w-6" />
            {sprint.score}/100
          </p>
        </div>

        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <p className="text-sm text-slate-500">Sprint completion</p>
          <p className="mt-2 text-3xl font-semibold text-blue-900">{sprint.completion}%</p>
        </div>

        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <p className="text-sm text-slate-500">Sprint status</p>
          <span className={`mt-3 inline-flex rounded-full px-3 py-1 text-sm font-semibold ${getSprintStatusStyles(sprint.status)}`}>
            {sprint.status}
          </span>
        </div>
      </div>

      <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <h2 className="text-xl font-semibold text-slate-900">Sprint summary</h2>

        <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-2">
          <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
            <div className="flex items-center gap-2 text-slate-700">
              <CalendarDays className="h-4 w-4" />
              Timeline
            </div>
            <p className="mt-1 text-sm text-slate-600">
              {sprint.startDate} to {sprint.endDate}
            </p>
          </div>

          <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
            <div className="flex items-center gap-2 text-slate-700">
              <FileCheck2 className="h-4 w-4" />
              Team
            </div>
            <p className="mt-1 text-sm text-slate-600">{project.teamName}</p>
          </div>
        </div>

        <div className="mt-5">
          <div className="mb-2 flex items-center justify-between text-sm text-slate-600">
            <span>Progress</span>
            <span>{sprint.completion}%</span>
          </div>
          <div className="h-2 rounded-full bg-slate-200">
            <div className="h-full rounded-full bg-blue-700" style={{ width: `${sprint.completion}%` }} />
          </div>
        </div>
      </div>
    </div>
  );
}
