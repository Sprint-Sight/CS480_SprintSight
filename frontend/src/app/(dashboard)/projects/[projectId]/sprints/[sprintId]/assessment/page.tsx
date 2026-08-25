import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft, ClipboardCheck, FileText, Sparkles, TrendingUp } from "lucide-react";

import { getSprintByProjectAndId } from "@/features/projects/data";

export default function SprintAssessmentEntryPage({
  params,
}: {
  params: { projectId: string; sprintId: string };
}) {
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
          Back to sprint timeline
        </Link>
        <h1 className="mt-2 text-3xl font-bold tracking-tight text-blue-950">
          {project.name} - {sprint.name} Assessment
        </h1>
        <p className="mt-1 text-sm text-slate-500">Entry point for sprint-level assessment reports and rubric insights.</p>
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
          <p className="text-sm text-slate-500">Assessment status</p>
          <p className="mt-2 text-3xl font-semibold text-blue-900">{sprint.status}</p>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <p className="text-sm text-slate-500">Completion</p>
          <p className="mt-2 text-3xl font-semibold text-blue-900">{sprint.completion}%</p>
        </div>
      </div>

      <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <h2 className="text-xl font-semibold text-slate-900">Assessment actions</h2>
        <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-3">
          <Link
            href="/assessment-report"
            className="rounded-xl border border-slate-200 bg-slate-50 p-4 transition hover:border-blue-200 hover:bg-blue-50/40"
          >
            <FileText className="h-5 w-5 text-blue-700" />
            <p className="mt-2 font-semibold text-slate-900">Open Assessment Report</p>
            <p className="mt-1 text-sm text-slate-500">View generated rubric grading and feedback.</p>
          </Link>

          <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
            <ClipboardCheck className="h-5 w-5 text-blue-700" />
            <p className="mt-2 font-semibold text-slate-900">Review Checklist</p>
            <p className="mt-1 text-sm text-slate-500">Validate evidence quality before final grading.</p>
          </div>

          <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
            <Sparkles className="h-5 w-5 text-blue-700" />
            <p className="mt-2 font-semibold text-slate-900">Insights Summary</p>
            <p className="mt-1 text-sm text-slate-500">Quick highlights for team coaching decisions.</p>
          </div>
        </div>
      </div>
    </div>
  );
}
